import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import Message
from app.schemas.notification import NotificationPublic

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationPublic])
async def list_notifications(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == current_user.id, Notification.is_read.is_(False)
        )
    )
    return {"unread_count": result.scalar_one()}


@router.post("/{notification_id}/read", response_model=NotificationPublic)
async def mark_read(notification_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    notif = await db.get(Notification, notification_id)
    if not notif or notif.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    notif.is_read = True
    await db.commit()
    await db.refresh(notif)
    return notif


@router.post("/read-all", response_model=Message)
async def mark_all_read(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await db.execute(
        update(Notification).where(Notification.user_id == current_user.id).values(is_read=True)
    )
    await db.commit()
    return Message(message="All notifications marked as read")
