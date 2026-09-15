import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.schemas.complaint import ComplaintCreate, ComplaintEscalate, ComplaintPublic, ComplaintRespond
from app.services import complaint_service

router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.post("", response_model=ComplaintPublic, status_code=status.HTTP_201_CREATED)
async def create_complaint(
    payload: ComplaintCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    complaint = await complaint_service.create_complaint(db, current_user, payload)
    await db.commit()
    return complaint


@router.get("", response_model=list[ComplaintPublic])
async def list_complaints(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await complaint_service.list_complaints(db, current_user)


@router.get("/{complaint_id}", response_model=ComplaintPublic)
async def get_complaint(complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    complaint = await complaint_service.get_complaint_or_404(db, complaint_id)
    if not await complaint_service.can_view_complaint(db, complaint, current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot access this record")
    return complaint


@router.get("/{complaint_id}/history")
async def get_complaint_history(complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    complaint = await complaint_service.get_complaint_or_404(db, complaint_id)
    if not await complaint_service.can_view_complaint(db, complaint, current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot access this record")
    return await complaint_service.get_history(db, complaint_id)


@router.post("/{complaint_id}/respond", response_model=ComplaintPublic)
async def respond_to_complaint(
    complaint_id: uuid.UUID,
    payload: ComplaintRespond,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.TEAM_LEADER, UserRole.DIRECTOR, UserRole.HUMAN_RESOURCE, UserRole.TECHNICAL_COMMITTEE, UserRole.SUPER_ADMIN)
    ),
):
    complaint = await complaint_service.respond(
        db, current_user, complaint_id, payload.message, payload.resolve, payload.reject
    )
    await db.commit()
    return complaint


@router.post("/{complaint_id}/escalate", response_model=ComplaintPublic)
async def escalate_complaint(
    complaint_id: uuid.UUID,
    payload: ComplaintEscalate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.TEAM_LEADER, UserRole.DIRECTOR)),
):
    complaint = await complaint_service.escalate(db, current_user, complaint_id, payload.message)
    await db.commit()
    return complaint
