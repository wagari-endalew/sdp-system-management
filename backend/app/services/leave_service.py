import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveRequest, LeaveRequestHistory, LeaveStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.leave_request import LeaveCreate
from app.services import notification_service, user_service


async def _add_history(db: AsyncSession, leave_id: uuid.UUID, actor_id, action: str, reason: str | None = None):
    db.add(LeaveRequestHistory(leave_id=leave_id, actor_id=actor_id, action=action, reason=reason))
    await db.flush()


async def _notify_hr(db: AsyncSession, title: str, message: str, link: str) -> None:
    result = await db.execute(
        select(User).where(User.role == UserRole.HUMAN_RESOURCE, User.status == UserStatus.ACTIVE)
    )
    for hr_user in result.scalars().all():
        await notification_service.notify(db, user_id=hr_user.id, title=title, message=message, link=link)


async def _notify_super_admins(db: AsyncSession, title: str, message: str, link: str) -> None:
    result = await db.execute(
        select(User).where(User.role == UserRole.SUPER_ADMIN, User.status == UserStatus.ACTIVE)
    )
    for admin in result.scalars().all():
        await notification_service.notify(db, user_id=admin.id, title=title, message=message, link=link)


async def create_leave(db: AsyncSession, requester: User, payload: LeaveCreate) -> LeaveRequest:
    """
    Employees: goes to their Team Leader as before.
    Any other role (Team Leader, Director, Technical Committee, Super Admin)
    requesting their own leave: goes straight to Human Resource, since they
    have no Team Leader over them in the normal sense.
    Human Resource requesting their own leave: goes to Super Admin, since HR
    approving its own leave request would be self-approval.
    """
    end_date = payload.start_date + timedelta(days=payload.days - 1)
    is_employee = requester.role == UserRole.EMPLOYEE
    is_hr = requester.role == UserRole.HUMAN_RESOURCE

    initial_status = LeaveStatus.SUBMITTED if is_employee else LeaveStatus.PENDING_HR

    leave = LeaveRequest(
        employee_id=requester.id,
        leave_type=payload.leave_type,
        days=payload.days,
        start_date=payload.start_date,
        end_date=end_date,
        reason=payload.reason,
        status=initial_status,
        prepared_signature=payload.prepared_signature,
        extra_fields=payload.extra_fields,
    )
    db.add(leave)
    await db.flush()
    await _add_history(db, leave.id, requester.id, "submitted")

    if is_employee:
        if requester.team_leader_id:
            await notification_service.notify(
                db,
                user_id=requester.team_leader_id,
                title="New leave request",
                message=f"{requester.full_name} requested {payload.days} day(s) of leave.",
                link=f"/leave-requests/{leave.id}",
            )
    elif is_hr:
        await _notify_super_admins(
            db,
            "New leave request (from Human Resource)",
            f"{requester.full_name} (Human Resource) requested {payload.days} day(s) of leave.",
            f"/leave-requests/{leave.id}",
        )
    else:
        await _notify_hr(
            db,
            "New leave request",
            f"{requester.full_name} ({requester.role.value.replace('_',' ').title()}) requested {payload.days} day(s) of leave.",
            f"/leave-requests/{leave.id}",
        )
    await db.refresh(leave)
    return leave


async def list_leaves(db: AsyncSession, current_user: User) -> list[LeaveRequest]:
    scope = await user_service.visible_employee_ids_for(db, current_user)
    stmt = select(LeaveRequest).order_by(LeaveRequest.created_at.desc())
    if scope is not None:
        stmt = stmt.where(LeaveRequest.employee_id.in_(scope))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_leave_or_404(db: AsyncSession, leave_id: uuid.UUID) -> LeaveRequest:
    leave = await db.get(LeaveRequest, leave_id)
    if not leave:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave request not found")
    return leave


async def _get_leave_locked_or_404(db: AsyncSession, leave_id: uuid.UUID) -> LeaveRequest:
    """Row-locking fetch — see performance_plan_service._get_plan_locked_or_404
    for why: prevents two concurrent decisions on the same leave request from
    both reading the old status before either writes the new one."""
    stmt = select(LeaveRequest).where(LeaveRequest.id == leave_id).with_for_update()
    leave = (await db.execute(stmt)).scalar_one_or_none()
    if not leave:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave request not found")
    return leave


async def assert_can_view(db: AsyncSession, current_user: User, leave: LeaveRequest) -> None:
    scope = await user_service.visible_employee_ids_for(db, current_user)
    if scope is not None and leave.employee_id not in scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot access this record")


async def team_leader_decide(
    db: AsyncSession, team_leader: User, leave_id: uuid.UUID, approve: bool, reason: str | None, signature: str | None = None
) -> LeaveRequest:
    leave = await _get_leave_locked_or_404(db, leave_id)
    if not await user_service.is_direct_report(db, team_leader, leave.employee_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not a member of your team")
    if leave.status != LeaveStatus.SUBMITTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leave request is not awaiting Team Leader review")

    leave.status = LeaveStatus.APPROVED if approve else LeaveStatus.REJECTED
    leave.decided_by = team_leader.id
    leave.decision_reason = reason
    leave.decided_signature = signature
    leave.decided_at = datetime.now(timezone.utc)
    await _add_history(db, leave.id, team_leader.id, "approved" if approve else "rejected", reason)
    await db.flush()

    await notification_service.notify(
        db,
        user_id=leave.employee_id,
        title=f"Leave request {'approved' if approve else 'rejected'}",
        message=reason or f"Your leave request was {'approved' if approve else 'rejected'}.",
        link=f"/leave-requests/{leave.id}",
    )
    if approve:
        employee = await db.get(User, leave.employee_id)
        await _notify_hr(
            db,
            "Leave approved — available for records",
            f"{employee.full_name if employee else 'An employee'}'s leave request was approved by their Team Leader.",
            f"/leave-requests/{leave.id}",
        )
    await db.refresh(leave)
    return leave


async def team_leader_escalate(db: AsyncSession, team_leader: User, leave_id: uuid.UUID, reason: str) -> LeaveRequest:
    leave = await _get_leave_locked_or_404(db, leave_id)
    if not await user_service.is_direct_report(db, team_leader, leave.employee_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not a member of your team")
    if leave.status != LeaveStatus.SUBMITTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leave request is not awaiting Team Leader review")

    leave.status = LeaveStatus.ESCALATED
    await _add_history(db, leave.id, team_leader.id, "escalated_to_director", reason)
    await db.flush()

    if team_leader.director_id:
        await notification_service.notify(
            db,
            user_id=team_leader.director_id,
            title="Leave request escalated",
            message=f"{team_leader.full_name} escalated a leave request for your decision.",
            link=f"/leave-requests/{leave.id}",
        )
    await db.refresh(leave)
    return leave


async def director_decide(
    db: AsyncSession, director: User, leave_id: uuid.UUID, approve: bool, reason: str | None, signature: str | None = None
) -> LeaveRequest:
    leave = await _get_leave_locked_or_404(db, leave_id)
    if not await user_service.director_covers_employee(db, director, leave.employee_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This escalation is outside your department")
    if leave.status != LeaveStatus.ESCALATED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leave request is not awaiting Director review")

    leave.status = LeaveStatus.DIRECTOR_APPROVED if approve else LeaveStatus.DIRECTOR_REJECTED
    leave.decided_by = director.id
    leave.decision_reason = reason
    leave.decided_signature = signature
    leave.decided_at = datetime.now(timezone.utc)
    await _add_history(db, leave.id, director.id, "director_approved" if approve else "director_rejected", reason)
    await db.flush()

    await notification_service.notify(
        db,
        user_id=leave.employee_id,
        title=f"Leave request {'approved' if approve else 'rejected'} by Director",
        message=reason or "Your escalated leave request has been decided by the Director.",
        link=f"/leave-requests/{leave.id}",
    )
    await db.refresh(leave)
    return leave


async def human_resource_decide(
    db: AsyncSession, actor: User, leave_id: uuid.UUID, approve: bool, reason: str | None, signature: str | None = None
) -> LeaveRequest:
    leave = await _get_leave_locked_or_404(db, leave_id)
    if leave.status != LeaveStatus.PENDING_HR:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leave request is not awaiting Human Resource review")

    requester = await db.get(User, leave.employee_id)
    requester_is_hr = bool(requester and requester.role == UserRole.HUMAN_RESOURCE)

    if requester_is_hr and actor.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "A Human Resource member's own leave request must be decided by a Super Admin",
        )
    if not requester_is_hr and actor.role not in (UserRole.HUMAN_RESOURCE, UserRole.SUPER_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This request is not assigned to your role")

    leave.status = LeaveStatus.HR_APPROVED if approve else LeaveStatus.HR_REJECTED
    leave.decided_by = actor.id
    leave.decision_reason = reason
    leave.decided_signature = signature
    leave.decided_at = datetime.now(timezone.utc)
    await _add_history(db, leave.id, actor.id, "hr_approved" if approve else "hr_rejected", reason)
    await db.flush()

    await notification_service.notify(
        db,
        user_id=leave.employee_id,
        title=f"Leave request {'approved' if approve else 'rejected'}",
        message=reason or f"Your leave request was {'approved' if approve else 'rejected'}.",
        link=f"/leave-requests/{leave.id}",
    )
    await db.refresh(leave)
    return leave


async def get_history(db: AsyncSession, leave_id: uuid.UUID) -> list[LeaveRequestHistory]:
    result = await db.execute(
        select(LeaveRequestHistory)
        .where(LeaveRequestHistory.leave_id == leave_id)
        .order_by(LeaveRequestHistory.created_at.asc())
    )
    return list(result.scalars().all())
