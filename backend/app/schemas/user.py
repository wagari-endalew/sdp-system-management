import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole, UserStatus


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    full_name: str
    role: UserRole
    position: str
    status: UserStatus
    department_id: Optional[uuid.UUID] = None
    team_id: Optional[uuid.UUID] = None
    team_leader_id: Optional[uuid.UUID] = None
    director_id: Optional[uuid.UUID] = None
    created_at: datetime


class UserBrief(BaseModel):
    """Minimal shape used for dropdown pickers (e.g. choose your team leader)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    position: str
    role: UserRole


class UserUpdateStatus(BaseModel):
    status: UserStatus


class UserUpdateRole(BaseModel):
    role: UserRole


class UserUpdateDetails(BaseModel):
    full_name: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None


class UserAssignTeam(BaseModel):
    team_id: Optional[uuid.UUID] = None
    team_leader_id: Optional[uuid.UUID] = None
    director_id: Optional[uuid.UUID] = None
    department_id: Optional[uuid.UUID] = None


class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None


class DepartmentPublic(DepartmentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class TeamCreate(BaseModel):
    name: str
    department_id: Optional[uuid.UUID] = None
    team_leader_id: Optional[uuid.UUID] = None


class TeamPublic(TeamCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
