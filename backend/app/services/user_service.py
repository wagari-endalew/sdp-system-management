import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


async def visible_employee_ids_for(db: AsyncSession, current_user: User) -> set[uuid.UUID] | None:
    """
    Returns the set of employee ids whose records `current_user` may see for
    scoping performance-plan / leave / complaint queries.

    Returns None to mean "no restriction" (super admin, technical committee -
    read all).
    """
    if current_user.role in (UserRole.SUPER_ADMIN, UserRole.TECHNICAL_COMMITTEE, UserRole.HUMAN_RESOURCE):
        return None

    if current_user.role == UserRole.EMPLOYEE:
        return {current_user.id}

    if current_user.role == UserRole.TEAM_LEADER:
        result = await db.execute(select(User.id).where(User.team_leader_id == current_user.id))
        ids = {row[0] for row in result.all()}
        ids.add(current_user.id)
        return ids

    if current_user.role == UserRole.DIRECTOR:
        # Directors oversee all team leaders reporting to them, plus those
        # team leaders' employees.
        tl_result = await db.execute(select(User.id).where(User.director_id == current_user.id))
        team_leader_ids = {row[0] for row in tl_result.all()}
        ids = set(team_leader_ids)
        ids.add(current_user.id)
        if team_leader_ids:
            emp_result = await db.execute(
                select(User.id).where(User.team_leader_id.in_(team_leader_ids))
            )
            ids |= {row[0] for row in emp_result.all()}
        return ids

    return {current_user.id}


async def is_direct_report(db: AsyncSession, team_leader: User, employee_id: uuid.UUID) -> bool:
    employee = await db.get(User, employee_id)
    return bool(employee and employee.team_leader_id == team_leader.id)


async def director_covers_employee(db: AsyncSession, director: User, employee_id: uuid.UUID) -> bool:
    employee = await db.get(User, employee_id)
    if not employee or not employee.team_leader_id:
        return False
    team_leader = await db.get(User, employee.team_leader_id)
    return bool(team_leader and team_leader.director_id == director.id)


async def director_covers_team_leader_self_review(db: AsyncSession, director: User, team_leader_id: uuid.UUID) -> bool:
    """Performance-plan-only: a Team Leader has no one below them to review
    their own self-assessment, so it's routed straight to their Director.
    Kept separate from director_covers_employee so this doesn't change who a
    Director can act on for leave requests or complaints, which intentionally
    route a Team Leader's own record to HR instead."""
    team_leader = await db.get(User, team_leader_id)
    return bool(team_leader and team_leader.role == UserRole.TEAM_LEADER and team_leader.director_id == director.id)
