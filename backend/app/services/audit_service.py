import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def record(
    db: AsyncSession,
    *,
    user_id: Optional[uuid.UUID],
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta,
        ip_address=ip_address,
    )
    db.add(log)
    await db.flush()
