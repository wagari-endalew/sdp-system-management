import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services import complaint_service, leave_service, performance_plan_service

router = APIRouter(prefix="/reports", tags=["Reports"])


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/performance-plans/export")
async def export_performance_plans(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    plans = await performance_plan_service.list_plans(db, current_user)
    rows = [
        {
            "id": str(p.id),
            "employee_id": str(p.employee_id),
            "title": p.title,
            "period": p.period.value,
            "status": p.status.value,
            "created_at": p.created_at.isoformat(),
            "decided_at": p.decided_at.isoformat() if p.decided_at else "",
        }
        for p in plans
    ]
    return _csv_response(rows, "performance_plans.csv")


@router.get("/leave-requests/export")
async def export_leave_requests(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    leaves = await leave_service.list_leaves(db, current_user)
    rows = [
        {
            "id": str(l.id),
            "employee_id": str(l.employee_id),
            "leave_type": l.leave_type.value,
            "days": l.days,
            "start_date": l.start_date.isoformat(),
            "end_date": l.end_date.isoformat(),
            "status": l.status.value,
            "created_at": l.created_at.isoformat(),
        }
        for l in leaves
    ]
    return _csv_response(rows, "leave_requests.csv")


@router.get("/complaints/export")
async def export_complaints(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    complaints = await complaint_service.list_complaints(db, current_user)
    rows = [
        {
            "id": str(c.id),
            "employee_id": str(c.employee_id),
            "category": c.category,
            "subject": c.subject,
            "status": c.status.value,
            "current_handler_role": c.current_handler_role,
            "created_at": c.created_at.isoformat(),
        }
        for c in complaints
    ]
    return _csv_response(rows, "complaints.csv")
