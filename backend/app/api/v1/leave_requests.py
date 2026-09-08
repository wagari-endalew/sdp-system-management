import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.schemas.leave_request import LeaveCreate, LeaveDecision, LeaveEscalate, LeavePublic, LeaveReject
from app.services import pdf_service, leave_service

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])


@router.post("", response_model=LeavePublic, status_code=status.HTTP_201_CREATED)
async def create_leave(
    payload: LeaveCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    leave = await leave_service.create_leave(db, current_user, payload)
    await db.commit()
    return leave


@router.get("", response_model=list[LeavePublic])
async def list_leaves(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await leave_service.list_leaves(db, current_user)


@router.get("/{leave_id}", response_model=LeavePublic)
async def get_leave(leave_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    leave = await leave_service.get_leave_or_404(db, leave_id)
    await leave_service.assert_can_view(db, current_user, leave)
    return leave


@router.get("/{leave_id}/history")
async def get_leave_history(leave_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    leave = await leave_service.get_leave_or_404(db, leave_id)
    await leave_service.assert_can_view(db, current_user, leave)
    return await leave_service.get_history(db, leave_id)


@router.post("/{leave_id}/approve", response_model=LeavePublic)
async def approve_leave(
    leave_id: uuid.UUID,
    payload: LeaveDecision | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.TEAM_LEADER)),
):
    leave = await leave_service.team_leader_decide(
        db, current_user, leave_id, approve=True,
        reason=payload.reason if payload else None,
        signature=payload.signature if payload else None,
    )
    await db.commit()
    return leave


@router.post("/{leave_id}/reject", response_model=LeavePublic)
async def reject_leave(
    leave_id: uuid.UUID,
    payload: LeaveReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.TEAM_LEADER)),
):
    leave = await leave_service.team_leader_decide(
        db, current_user, leave_id, approve=False, reason=payload.reason, signature=payload.signature
    )
    await db.commit()
    return leave


@router.post("/{leave_id}/escalate", response_model=LeavePublic)
async def escalate_leave(
    leave_id: uuid.UUID,
    payload: LeaveEscalate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.TEAM_LEADER)),
):
    leave = await leave_service.team_leader_escalate(db, current_user, leave_id, payload.reason)
    await db.commit()
    return leave


@router.post("/{leave_id}/director-approve", response_model=LeavePublic)
async def director_approve_leave(
    leave_id: uuid.UUID,
    payload: LeaveDecision | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    leave = await leave_service.director_decide(
        db, current_user, leave_id, approve=True,
        reason=payload.reason if payload else None,
        signature=payload.signature if payload else None,
    )
    await db.commit()
    return leave


@router.post("/{leave_id}/director-reject", response_model=LeavePublic)
async def director_reject_leave(
    leave_id: uuid.UUID,
    payload: LeaveReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    leave = await leave_service.director_decide(
        db, current_user, leave_id, approve=False, reason=payload.reason, signature=payload.signature
    )
    await db.commit()
    return leave


@router.post("/{leave_id}/hr-approve", response_model=LeavePublic)
async def hr_approve_leave(
    leave_id: uuid.UUID,
    payload: LeaveDecision | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.HUMAN_RESOURCE, UserRole.SUPER_ADMIN)),
):
    leave = await leave_service.human_resource_decide(
        db, current_user, leave_id, approve=True,
        reason=payload.reason if payload else None,
        signature=payload.signature if payload else None,
    )
    await db.commit()
    return leave


@router.post("/{leave_id}/hr-reject", response_model=LeavePublic)
async def hr_reject_leave(
    leave_id: uuid.UUID,
    payload: LeaveReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.HUMAN_RESOURCE, UserRole.SUPER_ADMIN)),
):
    leave = await leave_service.human_resource_decide(
        db, current_user, leave_id, approve=False, reason=payload.reason, signature=payload.signature
    )
    await db.commit()
    return leave


@router.get("/{leave_id}/download")
async def download_leave(leave_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    leave = await leave_service.get_leave_or_404(db, leave_id)
    await leave_service.assert_can_view(db, current_user, leave)

    employee = await db.get(User, leave.employee_id)
    if not employee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")
    decider = await db.get(User, leave.decided_by) if leave.decided_by else None
    path = pdf_service.generate_leave_pdf(leave, employee, decider.full_name if decider else None)
    return FileResponse(path, filename=os.path.basename(path), media_type="application/pdf")
