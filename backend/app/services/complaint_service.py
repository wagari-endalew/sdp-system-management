import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint, ComplaintResponse, ComplaintStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.complaint import ComplaintCreate
from app.services import notification_service, user_service

# Recipients that broadcast to every active holder of the role, rather than
# one specific person — there's no "the" Super Admin/HR/Technical Committee
# member the way there's a specific Director or Team Leader.
BROADCAST_RECIPIENTS = {"super_admin", "technical_committee", "human_resource"}


async def _add_history(db: AsyncSession, complaint_id: uuid.UUID, actor_id, action: str, message: str | None = None):
    db.add(ComplaintResponse(complaint_id=complaint_id, actor_id=actor_id, action=action, message=message))
    await db.flush()


async def _notify_role_broadcast(db: AsyncSession, role: UserRole, title: str, message: str, link: str) -> None:
    result = await db.execute(select(User).where(User.role == role, User.status == UserStatus.ACTIVE))
    for u in result.scalars().all():
        await notification_service.notify(db, user_id=u.id, title=title, message=message, link=link)


def _default_handler_role(submitter: User) -> str:
    """The old behavior, kept as a fallback for callers that don't specify
    an explicit recipient (or for the 'employee' recipient, where the named
    person is descriptive, not a routing target — the complaint still needs
    a real handler)."""
    is_employee = submitter.role == UserRole.EMPLOYEE
    if is_employee and submitter.team_leader_id:
        return "team_leader"
    if is_employee:
        return "director"
    return "human_resource"


async def create_complaint(db: AsyncSession, submitter: User, payload: ComplaintCreate) -> Complaint:
    target_user_id = None
    target_label = payload.target_label

    if payload.recipient in ("director", "team_leader"):
        target = await db.get(User, payload.target_user_id)
        if not target or target.role.value != payload.recipient or target.status != UserStatus.ACTIVE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected recipient is invalid or no longer active")
        handler_role = payload.recipient
        target_user_id = target.id
        target_label = target_label or target.full_name
    elif payload.recipient in BROADCAST_RECIPIENTS:
        handler_role = payload.recipient
    else:
        # No recipient (backward compat) or recipient == "employee": the
        # named person is context for the complaint, not who handles it —
        # it still needs to go to a real reviewer via the normal chain.
        handler_role = _default_handler_role(submitter)

    complaint = Complaint(
        employee_id=submitter.id,
        category=payload.category,
        subject=payload.subject,
        message=payload.message,
        status=ComplaintStatus.SUBMITTED,
        current_handler_role=handler_role,
        target_user_id=target_user_id,
        target_label=target_label,
    )
    db.add(complaint)
    await db.flush()
    await _add_history(db, complaint.id, submitter.id, "submitted", payload.message)

    notify_title = "New complaint submitted"
    notify_message = f"{submitter.full_name} ({submitter.role.value.replace('_',' ').title()}) submitted: {payload.subject}"
    if target_user_id:
        await notification_service.notify(
            db, user_id=target_user_id, title=notify_title, message=notify_message, link=f"/complaints/{complaint.id}"
        )
    elif handler_role in BROADCAST_RECIPIENTS:
        await _notify_role_broadcast(db, UserRole(handler_role), notify_title, notify_message, f"/complaints/{complaint.id}")
    else:
        handler_id = submitter.team_leader_id or submitter.director_id
        if handler_id:
            await notification_service.notify(
                db, user_id=handler_id, title=notify_title, message=notify_message, link=f"/complaints/{complaint.id}"
            )
    await db.refresh(complaint)
    return complaint


async def list_complaints(db: AsyncSession, current_user: User) -> list[Complaint]:
    stmt = select(Complaint).order_by(Complaint.created_at.desc())

    if current_user.role == UserRole.EMPLOYEE:
        stmt = stmt.where(Complaint.employee_id == current_user.id)
    elif current_user.role == UserRole.TEAM_LEADER:
        scope = await user_service.visible_employee_ids_for(db, current_user)
        # A complaint routed to THIS specific team leader is visible to them
        # even if the submitter isn't one of their direct reports (e.g. it
        # was addressed to them by name from anywhere in the org).
        stmt = stmt.where(Complaint.employee_id.in_(scope) | (Complaint.target_user_id == current_user.id))
    elif current_user.role == UserRole.DIRECTOR:
        scope = await user_service.visible_employee_ids_for(db, current_user)
        stmt = stmt.where(Complaint.employee_id.in_(scope) | (Complaint.target_user_id == current_user.id))
    elif current_user.role in (UserRole.SUPER_ADMIN, UserRole.HUMAN_RESOURCE):
        pass  # sees all
    else:
        stmt = stmt.where(Complaint.employee_id == current_user.id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_complaint_or_404(db: AsyncSession, complaint_id: uuid.UUID) -> Complaint:
    complaint = await db.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found")
    return complaint


async def respond(
    db: AsyncSession, actor: User, complaint_id: uuid.UUID, message: str, resolve: bool, reject: bool
) -> Complaint:
    complaint = await get_complaint_or_404(db, complaint_id)

    expected_role = complaint.current_handler_role
    always_can_respond = (UserRole.SUPER_ADMIN, UserRole.HUMAN_RESOURCE)
    if actor.role not in always_can_respond:
        if actor.role.value != expected_role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This complaint is not currently assigned to your role")
        # Routed to one specific Director/Team Leader — not "anyone holding
        # that role." Without this check, any Team Leader could resolve a
        # complaint that was deliberately addressed to a different one.
        if complaint.target_user_id and complaint.target_user_id != actor.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This complaint was addressed to a different person")

    if resolve:
        complaint.status = ComplaintStatus.RESOLVED
        complaint.resolution = message
        complaint.resolved_at = datetime.now(timezone.utc)
        action = "resolved"
    elif reject:
        complaint.status = ComplaintStatus.REJECTED
        complaint.resolution = message
        complaint.resolved_at = datetime.now(timezone.utc)
        action = "rejected"
    else:
        complaint.status = ComplaintStatus.IN_REVIEW
        action = "responded"

    await _add_history(db, complaint.id, actor.id, action, message)
    await db.flush()

    await notification_service.notify(
        db,
        user_id=complaint.employee_id,
        title=f"Update on your complaint: {complaint.subject}",
        message=message,
        link=f"/complaints/{complaint.id}",
    )
    await db.refresh(complaint)
    return complaint


async def escalate(db: AsyncSession, actor: User, complaint_id: uuid.UUID, message: str | None) -> Complaint:
    complaint = await get_complaint_or_404(db, complaint_id)

    # Same ownership check as respond(): if this was routed to one specific
    # Director/Team Leader, only they (not any peer with the same role) can
    # act on it — escalating included.
    if complaint.target_user_id and complaint.target_user_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This complaint was addressed to a different person")

    if complaint.current_handler_role == "team_leader" and actor.role == UserRole.TEAM_LEADER:
        complaint.current_handler_role = "director"
        complaint.status = ComplaintStatus.ESCALATED_DIRECTOR
        next_handler_id = actor.director_id
        complaint.target_user_id = actor.director_id  # pin to actor's own director specifically
    elif complaint.current_handler_role == "director" and actor.role == UserRole.DIRECTOR:
        complaint.current_handler_role = "super_admin"
        complaint.status = ComplaintStatus.ESCALATED_SUPER_ADMIN
        next_handler_id = None  # broadcast-style: any super admin can pick it up
        complaint.target_user_id = None
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This complaint cannot be escalated from its current stage")

    await _add_history(db, complaint.id, actor.id, "escalated", message)
    await db.flush()

    if next_handler_id:
        await notification_service.notify(
            db,
            user_id=next_handler_id,
            title="Complaint escalated to you",
            message=f"A complaint was escalated: {complaint.subject}",
            link=f"/complaints/{complaint.id}",
        )
    await db.refresh(complaint)
    return complaint


async def get_history(db: AsyncSession, complaint_id: uuid.UUID) -> list[ComplaintResponse]:
    result = await db.execute(
        select(ComplaintResponse)
        .where(ComplaintResponse.complaint_id == complaint_id)
        .order_by(ComplaintResponse.created_at.asc())
    )
    return list(result.scalars().all())
