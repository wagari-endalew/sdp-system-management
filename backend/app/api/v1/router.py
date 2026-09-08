from fastapi import APIRouter

from app.api.v1 import (
    audit_logs,
    auth,
    complaints,
    dashboard,
    leave_requests,
    notifications,
    performance_plans,
    reports,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(users.dept_router)
api_router.include_router(users.team_router)
api_router.include_router(performance_plans.router)
api_router.include_router(leave_requests.router)
api_router.include_router(complaints.router)
api_router.include_router(notifications.router)
api_router.include_router(audit_logs.router)
api_router.include_router(dashboard.router)
api_router.include_router(reports.router)
