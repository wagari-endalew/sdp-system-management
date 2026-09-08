import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def notify(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str,
    message: str,
    link: Optional[str] = None,
) -> None:
    db.add(Notification(user_id=user_id, title=title, message=message, link=link))
    await db.flush()
