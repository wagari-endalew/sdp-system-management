from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from datetime import datetime
from typing import Any, Optional

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.audit import AuditLog
from app.models.user import User, UserRole

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


class AuditLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    action: str
    entity_type: str
    entity_id: Optional[str]
    meta: Optional[dict[str, Any]]
    ip_address: Optional[str]
    created_at: datetime


@router.get("", response_model=list[AuditLogPublic])
async def list_audit_logs(
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    )
    return list(result.scalars().all())
