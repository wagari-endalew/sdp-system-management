import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.user import Department, Team, User, UserRole, UserStatus
from app.schemas.auth import RegisterRequest
from app.schemas.user import (
    DepartmentCreate,
    DepartmentPublic,
    TeamCreate,
    TeamPublic,
    UserAssignTeam,
    UserBrief,
    UserPublic,
    UserUpdateDetails,
    UserUpdateRole,
    UserUpdateStatus,
)
from app.services import audit_service

router = APIRouter(tags=["Users"])


@router.get("/users/by-role/{role}", response_model=list[UserBrief])
async def list_users_by_role(role: UserRole, db: AsyncSession = Depends(get_db)):
    """Public picker endpoint used by the registration form
    (e.g. choose your Team Leader / Director)."""
    result = await db.execute(
        select(User).where(
            User.role == role, User.status == UserStatus.ACTIVE, User.is_deleted.is_(False)
        )
    )
    return list(result.scalars().all())


@router.get("/users", response_model=list[UserPublic])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.DIRECTOR, UserRole.HUMAN_RESOURCE)),
):
    result = await db.execute(select(User).where(User.is_deleted.is_(False)).order_by(User.created_at.desc()))
    return list(result.scalars().all())


@router.get("/users/{user_id}", response_model=UserPublic)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = await db.get(User, user_id)
    if not user or user.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.patch("/users/{user_id}/status", response_model=UserPublic)
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserUpdateStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.status = payload.status
    await audit_service.record(
        db, user_id=current_user.id, action="update_user_status", entity_type="user",
        entity_id=str(user_id), meta={"new_status": payload.status.value},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/role", response_model=UserPublic)
async def update_user_role(
    user_id: uuid.UUID,
    payload: UserUpdateRole,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.role = payload.role
    await audit_service.record(
        db, user_id=current_user.id, action="update_user_role", entity_type="user",
        entity_id=str(user_id), meta={"new_role": payload.role.value},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/details", response_model=UserPublic)
async def update_user_details(
    user_id: uuid.UUID,
    payload: UserUpdateDetails,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    """Lets a Super Admin fix a name/position/email typo, or clean up a
    duplicate account's details, without needing to delete and re-register."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.position is not None:
        user.position = payload.position
    if payload.email is not None:
        new_email = payload.email.strip().lower()
        if new_email != user.email:
            existing = await db.execute(select(User).where(User.email == new_email, User.id != user_id))
            if existing.scalar_one_or_none():
                raise HTTPException(status.HTTP_409_CONFLICT, "Another account already uses that email")
            user.email = new_email
    await audit_service.record(
        db, user_id=current_user.id, action="update_user_details", entity_type="user", entity_id=str(user_id)
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/assignment", response_model=UserPublic)
async def update_user_assignment(
    user_id: uuid.UUID,
    payload: UserAssignTeam,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if payload.team_id is not None:
        user.team_id = payload.team_id
    if payload.team_leader_id is not None:
        user.team_leader_id = payload.team_leader_id
    if payload.director_id is not None:
        user.director_id = payload.director_id
    if payload.department_id is not None:
        user.department_id = payload.department_id
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", response_model=UserPublic)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.is_deleted = True
    user.status = UserStatus.SUSPENDED
    await audit_service.record(
        db, user_id=current_user.id, action="soft_delete_user", entity_type="user", entity_id=str(user_id)
    )
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------- Departments
dept_router = APIRouter(prefix="/departments", tags=["Departments"])


@dept_router.get("", response_model=list[DepartmentPublic])
async def list_departments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Department).where(Department.is_deleted.is_(False)))
    return list(result.scalars().all())


@dept_router.post("", response_model=DepartmentPublic, status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    dept = Department(**payload.model_dump())
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


@dept_router.delete("/{dept_id}", response_model=DepartmentPublic)
async def delete_department(
    dept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    dept.is_deleted = True
    await db.commit()
    await db.refresh(dept)
    return dept


# --------------------------------------------------------------------- Teams
team_router = APIRouter(prefix="/teams", tags=["Teams"])


@team_router.get("", response_model=list[TeamPublic])
async def list_teams(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.is_deleted.is_(False)))
    return list(result.scalars().all())


@team_router.post("", response_model=TeamPublic, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    team = Team(**payload.model_dump())
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


@team_router.delete("/{team_id}", response_model=TeamPublic)
async def delete_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPER_ADMIN)),
):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    team.is_deleted = True
    await db.commit()
    await db.refresh(team)
    return team
