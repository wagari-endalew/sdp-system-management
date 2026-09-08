import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.performance_plan import (
    PerformancePlan,
    PerformancePlanHistory,
    PlanStatus,
)
from app.models.user import User, UserRole
from app.schemas.performance_plan import PlanCreate, PlanUpdate
from app.services import notification_service, user_service


async def _add_history(db: AsyncSession, plan_id: uuid.UUID, actor_id, action: str, reason: str | None = None):
    db.add(PerformancePlanHistory(plan_id=plan_id, actor_id=actor_id, action=action, reason=reason))
    await db.flush()


SELF_REVIEW_ROLES = {UserRole.SUPER_ADMIN, UserRole.TECHNICAL_COMMITTEE, UserRole.DIRECTOR, UserRole.HUMAN_RESOURCE}


async def create_plan(db: AsyncSession, employee: User, payload: PlanCreate) -> PerformancePlan:
    # A Team Leader has nobody below them who could review their own plan, so
    # their self-assessment skips straight to Director review instead of
    # sitting in SUBMITTED (Team-Leader-review) status forever.
    is_self_review_leader = employee.role == UserRole.TEAM_LEADER
    # Director, HR, Technical Committee, and Super Admin have nobody above
    # them in this org chart at all — they prepare, approve, and download
    # their own record themselves (see self_decide below).
    is_self_certifying = employee.role in SELF_REVIEW_ROLES
    initial_status = PlanStatus.ESCALATED if is_self_review_leader else PlanStatus.SUBMITTED

    plan = PerformancePlan(
        employee_id=employee.id,
        period=payload.period,
        title=payload.title,
        goals=payload.goals,
        notes=payload.notes,
        status=initial_status,
        prepared_signature=payload.prepared_signature,
        extra_fields=payload.extra_fields,
    )
    db.add(plan)
    await db.flush()
    await _add_history(db, plan.id, employee.id, "submitted")

    if is_self_certifying:
        await _add_history(db, plan.id, employee.id, "self_certification",
                            f"{employee.role.value.replace('_',' ').title()} self-prepares and self-approves — no external reviewer in this org chart")
    elif is_self_review_leader:
        await _add_history(db, plan.id, employee.id, "escalated_to_director", "Self-assessment routed directly to Director")
        if employee.director_id:
            await notification_service.notify(
                db,
                user_id=employee.director_id,
                title="New performance self-assessment submitted",
                message=f"{employee.full_name} (Team Leader) submitted a self-assessment for your review.",
                link=f"/performance-plans/{plan.id}",
            )
    elif employee.team_leader_id:
        await notification_service.notify(
            db,
            user_id=employee.team_leader_id,
            title="New performance plan submitted",
            message=f"{employee.full_name} submitted a performance plan for review.",
            link=f"/performance-plans/{plan.id}",
        )
    await db.refresh(plan)
    return plan


async def list_plans(db: AsyncSession, current_user: User) -> list[PerformancePlan]:
    scope = await user_service.visible_employee_ids_for(db, current_user)
    stmt = select(PerformancePlan).order_by(PerformancePlan.created_at.desc())
    if scope is not None:
        stmt = stmt.where(PerformancePlan.employee_id.in_(scope))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_plan_or_404(db: AsyncSession, plan_id: uuid.UUID) -> PerformancePlan:
    plan = await db.get(PerformancePlan, plan_id)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Performance plan not found")
    return plan


async def _get_plan_locked_or_404(db: AsyncSession, plan_id: uuid.UUID) -> PerformancePlan:
    """Row-locking fetch for any function that reads .status and then writes
    based on it. Under Postgres this takes a real row lock (SELECT ... FOR
    UPDATE) so two concurrent decisions on the same plan can't both pass the
    status check before either commits. SQLite (used in tests) has no
    row-level locking and silently ignores the clause, which is fine since
    SQLite already serializes writes at the connection level."""
    stmt = select(PerformancePlan).where(PerformancePlan.id == plan_id).with_for_update()
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Performance plan not found")
    return plan


async def assert_can_view(db: AsyncSession, current_user: User, plan: PerformancePlan) -> None:
    scope = await user_service.visible_employee_ids_for(db, current_user)
    if scope is not None and plan.employee_id not in scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot access this record")


async def update_plan(db: AsyncSession, current_user: User, plan_id: uuid.UUID, payload: PlanUpdate) -> PerformancePlan:
    plan = await _get_plan_locked_or_404(db, plan_id)
    if plan.employee_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own plan")
    if plan.status not in (PlanStatus.REJECTED, PlanStatus.DIRECTOR_REJECTED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only rejected plans can be edited and resubmitted")

    if payload.title is not None:
        plan.title = payload.title
    if payload.goals is not None:
        plan.goals = payload.goals
    if payload.notes is not None:
        plan.notes = payload.notes
    # Team Leaders review-skip straight to Director (see create_plan) — keep
    # a resubmission on the same track rather than sending it to a
    # non-existent "team leader of the team leader" reviewer.
    plan.status = PlanStatus.ESCALATED if current_user.role == UserRole.TEAM_LEADER else PlanStatus.SUBMITTED
    plan.decision_reason = None
    await _add_history(db, plan.id, current_user.id, "resubmitted")
    await db.flush()
    await db.refresh(plan)
    return plan


async def team_leader_decide(
    db: AsyncSession, team_leader: User, plan_id: uuid.UUID, approve: bool, reason: str | None, signature: str | None = None
) -> PerformancePlan:
    plan = await _get_plan_locked_or_404(db, plan_id)
    if not await user_service.is_direct_report(db, team_leader, plan.employee_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not a member of your team")
    if plan.status != PlanStatus.SUBMITTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plan is not awaiting Team Leader review")

    plan.status = PlanStatus.APPROVED if approve else PlanStatus.REJECTED
    plan.decided_by = team_leader.id
    plan.decision_reason = reason
    plan.decided_signature = signature
    plan.decided_at = datetime.now(timezone.utc)
    await _add_history(db, plan.id, team_leader.id, "approved" if approve else "rejected", reason)
    await db.flush()

    await notification_service.notify(
        db,
        user_id=plan.employee_id,
        title=f"Performance plan {'approved' if approve else 'rejected'}",
        message=reason or f"Your performance plan was {'approved' if approve else 'rejected'} by your Team Leader.",
        link=f"/performance-plans/{plan.id}",
    )
    await db.refresh(plan)
    return plan


async def team_leader_escalate(db: AsyncSession, team_leader: User, plan_id: uuid.UUID, reason: str) -> PerformancePlan:
    plan = await _get_plan_locked_or_404(db, plan_id)
    if not await user_service.is_direct_report(db, team_leader, plan.employee_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not a member of your team")
    if plan.status != PlanStatus.SUBMITTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plan is not awaiting Team Leader review")

    plan.status = PlanStatus.ESCALATED
    await _add_history(db, plan.id, team_leader.id, "escalated_to_director", reason)
    await db.flush()

    if team_leader.director_id:
        await notification_service.notify(
            db,
            user_id=team_leader.director_id,
            title="Performance plan escalated",
            message=f"{team_leader.full_name} escalated a performance plan for your decision.",
            link=f"/performance-plans/{plan.id}",
        )
    await db.refresh(plan)
    return plan


async def director_decide(
    db: AsyncSession, director: User, plan_id: uuid.UUID, approve: bool, reason: str | None, signature: str | None = None
) -> PerformancePlan:
    plan = await _get_plan_locked_or_404(db, plan_id)
    covers = await user_service.director_covers_employee(db, director, plan.employee_id)
    if not covers:
        covers = await user_service.director_covers_team_leader_self_review(db, director, plan.employee_id)
    if not covers:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This escalation is outside your department")
    if plan.status != PlanStatus.ESCALATED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plan is not awaiting Director review")

    plan.status = PlanStatus.DIRECTOR_APPROVED if approve else PlanStatus.DIRECTOR_REJECTED
    plan.decided_by = director.id
    plan.decision_reason = reason
    plan.decided_signature = signature
    plan.decided_at = datetime.now(timezone.utc)
    await _add_history(db, plan.id, director.id, "director_approved" if approve else "director_rejected", reason)
    await db.flush()

    await notification_service.notify(
        db,
        user_id=plan.employee_id,
        title=f"Performance plan {'approved' if approve else 'rejected'} by Director",
        message=reason or "Your escalated performance plan has been decided by the Director.",
        link=f"/performance-plans/{plan.id}",
    )
    await db.refresh(plan)
    return plan


async def self_decide(
    db: AsyncSession, actor: User, plan_id: uuid.UUID, approve: bool, reason: str | None, signature: str | None = None
) -> PerformancePlan:
    """Director, HR, Technical Committee, and Super Admin have nobody above
    them in this org chart to review their own performance plan — they
    prepare it and decide on it themselves. Restricted to those four roles
    and to the plan's own owner; everyone else still goes through the normal
    Team-Leader / Director chain."""
    plan = await _get_plan_locked_or_404(db, plan_id)
    if plan.employee_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only self-certify your own plan")
    if actor.role not in SELF_REVIEW_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Self-certification is only available to Director, HR, Technical Committee, and Super Admin",
        )
    if plan.status != PlanStatus.SUBMITTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plan is not awaiting a decision")

    plan.status = PlanStatus.APPROVED if approve else PlanStatus.REJECTED
    plan.decided_by = actor.id
    plan.decision_reason = reason
    plan.decided_signature = signature
    plan.decided_at = datetime.now(timezone.utc)
    await _add_history(db, plan.id, actor.id, "self_approved" if approve else "self_rejected", reason)
    await db.flush()
    await db.refresh(plan)
    return plan


async def add_technical_committee_comment(
    db: AsyncSession, member: User, plan_id: uuid.UUID, comment: str
) -> PerformancePlan:
    plan = await get_plan_or_404(db, plan_id)
    plan.technical_committee_comment = comment
    await _add_history(db, plan.id, member.id, "technical_committee_comment", comment)
    await db.flush()
    await db.refresh(plan)
    return plan


async def get_history(db: AsyncSession, plan_id: uuid.UUID) -> list[PerformancePlanHistory]:
    result = await db.execute(
        select(PerformancePlanHistory)
        .where(PerformancePlanHistory.plan_id == plan_id)
        .order_by(PerformancePlanHistory.created_at.asc())
    )
    return list(result.scalars().all())
