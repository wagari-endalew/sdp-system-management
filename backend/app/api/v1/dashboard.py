from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole, UserStatus
from app.services import complaint_service, leave_service, performance_plan_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    plans = await performance_plan_service.list_plans(db, current_user)
    leaves = await leave_service.list_leaves(db, current_user)
    complaints = await complaint_service.list_complaints(db, current_user)

    plan_status_counts = dict(Counter(p.status.value for p in plans))
    leave_status_counts = dict(Counter(l.status.value for l in leaves))
    complaint_status_counts = dict(Counter(c.status.value for c in complaints))

    pending_action_plans = 0
    pending_action_leaves = 0
    pending_action_complaints = 0

    if current_user.role == UserRole.TEAM_LEADER:
        pending_action_plans = sum(1 for p in plans if p.status.value == "submitted")
        pending_action_leaves = sum(1 for l in leaves if l.status.value == "submitted")
        pending_action_complaints = sum(1 for c in complaints if c.current_handler_role == "team_leader" and c.status.value in ("submitted", "in_review"))
    elif current_user.role == UserRole.DIRECTOR:
        pending_action_plans = sum(1 for p in plans if p.status.value == "escalated")
        pending_action_leaves = sum(1 for l in leaves if l.status.value == "escalated")
        pending_action_complaints = sum(1 for c in complaints if c.current_handler_role == "director")
    elif current_user.role == UserRole.HUMAN_RESOURCE:
        pending_action_leaves = sum(1 for l in leaves if l.status.value == "pending_hr")
        pending_action_complaints = sum(1 for c in complaints if c.current_handler_role == "human_resource" and c.status.value in ("submitted", "in_review"))
    elif current_user.role == UserRole.SUPER_ADMIN:
        pending_action_leaves = sum(1 for l in leaves if l.status.value == "pending_hr")
        pending_action_complaints = sum(1 for c in complaints if c.current_handler_role == "super_admin")

    result = {
        "role": current_user.role.value,
        "total_performance_plans": len(plans),
        "total_leave_requests": len(leaves),
        "total_complaints": len(complaints),
        "performance_plan_status_counts": plan_status_counts,
        "leave_status_counts": leave_status_counts,
        "complaint_status_counts": complaint_status_counts,
        "pending_action_plans": pending_action_plans,
        "pending_action_leaves": pending_action_leaves,
        "pending_action_complaints": pending_action_complaints,
    }

    if current_user.role == UserRole.SUPER_ADMIN:
        total_users = await db.execute(select(func.count()).select_from(User).where(User.is_deleted.is_(False)))
        pending_activation = await db.execute(
            select(func.count()).select_from(User).where(User.status == UserStatus.PENDING)
        )
        result["total_users"] = total_users.scalar_one()
        result["pending_activations"] = pending_activation.scalar_one()

    if current_user.role == UserRole.TEAM_LEADER:
        team_size = await db.execute(
            select(func.count()).select_from(User).where(User.team_leader_id == current_user.id)
        )
        result["team_size"] = team_size.scalar_one()

    return result
