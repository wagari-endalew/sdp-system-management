import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.schemas.performance_plan import (
    PlanComment,
    PlanCreate,
    PlanDecision,
    PlanEscalate,
    PlanHistoryItem,
    PlanPublic,
    PlanReject,
    PlanUpdate,
)
from app.services import pdf_service, performance_plan_service

router = APIRouter(prefix="/performance-plans", tags=["Performance Plans"])


@router.post("", response_model=PlanPublic, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = await performance_plan_service.create_plan(db, current_user, payload)
    await db.commit()
    return plan


@router.get("", response_model=list[PlanPublic])
async def list_plans(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await performance_plan_service.list_plans(db, current_user)


@router.get("/{plan_id}", response_model=PlanPublic)
async def get_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = await performance_plan_service.get_plan_or_404(db, plan_id)
    await performance_plan_service.assert_can_view(db, current_user, plan)
    return plan


@router.get("/{plan_id}/history", response_model=list[PlanHistoryItem])
async def get_plan_history(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = await performance_plan_service.get_plan_or_404(db, plan_id)
    await performance_plan_service.assert_can_view(db, current_user, plan)
    return await performance_plan_service.get_history(db, plan_id)


@router.put("/{plan_id}", response_model=PlanPublic)
async def edit_and_resubmit_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = await performance_plan_service.update_plan(db, current_user, plan_id, payload)
    await db.commit()
    return plan


@router.post("/{plan_id}/approve", response_model=PlanPublic)
async def approve_plan(
    plan_id: uuid.UUID,
    payload: PlanDecision | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.TEAM_LEADER)),
):
    plan = await performance_plan_service.team_leader_decide(
        db, current_user, plan_id, approve=True,
        reason=payload.reason if payload else None,
        signature=payload.signature if payload else None,
    )
    await db.commit()
    return plan


@router.post("/{plan_id}/reject", response_model=PlanPublic)
async def reject_plan(
    plan_id: uuid.UUID,
    payload: PlanReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.TEAM_LEADER)),
):
    plan = await performance_plan_service.team_leader_decide(
        db, current_user, plan_id, approve=False, reason=payload.reason, signature=payload.signature
    )
    await db.commit()
    return plan


@router.post("/{plan_id}/escalate", response_model=PlanPublic)
async def escalate_plan(
    plan_id: uuid.UUID,
    payload: PlanEscalate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.TEAM_LEADER)),
):
    plan = await performance_plan_service.team_leader_escalate(db, current_user, plan_id, payload.reason)
    await db.commit()
    return plan


@router.post("/{plan_id}/director-approve", response_model=PlanPublic)
async def director_approve_plan(
    plan_id: uuid.UUID,
    payload: PlanDecision | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    plan = await performance_plan_service.director_decide(
        db, current_user, plan_id, approve=True,
        reason=payload.reason if payload else None,
        signature=payload.signature if payload else None,
    )
    await db.commit()
    return plan


@router.post("/{plan_id}/director-reject", response_model=PlanPublic)
async def director_reject_plan(
    plan_id: uuid.UUID,
    payload: PlanReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    plan = await performance_plan_service.director_decide(
        db, current_user, plan_id, approve=False, reason=payload.reason, signature=payload.signature
    )
    await db.commit()
    return plan


@router.post("/{plan_id}/self-approve", response_model=PlanPublic)
async def self_approve_plan(
    plan_id: uuid.UUID,
    payload: PlanDecision | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = await performance_plan_service.self_decide(
        db, current_user, plan_id, approve=True,
        reason=payload.reason if payload else None,
        signature=payload.signature if payload else None,
    )
    await db.commit()
    return plan


@router.post("/{plan_id}/self-reject", response_model=PlanPublic)
async def self_reject_plan(
    plan_id: uuid.UUID,
    payload: PlanReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = await performance_plan_service.self_decide(
        db, current_user, plan_id, approve=False, reason=payload.reason, signature=payload.signature
    )
    await db.commit()
    return plan


@router.post("/{plan_id}/comment", response_model=PlanPublic)
async def comment_on_plan(
    plan_id: uuid.UUID,
    payload: PlanComment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.TECHNICAL_COMMITTEE)),
):
    plan = await performance_plan_service.add_technical_committee_comment(db, current_user, plan_id, payload.comment)
    await db.commit()
    return plan


@router.get("/{plan_id}/download")
async def download_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = await performance_plan_service.get_plan_or_404(db, plan_id)
    await performance_plan_service.assert_can_view(db, current_user, plan)

    employee = await db.get(User, plan.employee_id)
    if not employee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")
    decider = await db.get(User, plan.decided_by) if plan.decided_by else None
    path = pdf_service.generate_performance_plan_pdf(
        plan, employee, decider.full_name if decider else None, plan.technical_committee_comment
    )
    return FileResponse(path, filename=os.path.basename(path), media_type="application/pdf")
