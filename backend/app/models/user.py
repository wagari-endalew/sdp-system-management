import enum
import uuid
from datetime import datetime
from typing import Optional

from app.models.base import str_enum
from sqlalchemy import ForeignKey, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import GUID, TimestampMixin, SoftDeleteMixin, gen_uuid


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    TECHNICAL_COMMITTEE = "technical_committee"
    DIRECTOR = "director"
    HUMAN_RESOURCE = "human_resource"
    TEAM_LEADER = "team_leader"
    EMPLOYEE = "employee"


class UserStatus(str, enum.Enum):
    PENDING = "pending"          # awaiting activation (elevated roles)
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Department(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    teams: Mapped[list["Team"]] = relationship(back_populates="department")


class Team(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("departments.id"), nullable=True
    )
    team_leader_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )

    department: Mapped[Optional["Department"]] = relationship(back_populates="teams")
    team_leader: Mapped[Optional["User"]] = relationship(
        foreign_keys=[team_leader_id], post_update=True
    )
    members: Mapped[list["User"]] = relationship(
        back_populates="team", foreign_keys="User.team_id"
    )


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        str_enum(UserRole, "user_role"), nullable=False
    )
    position: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus, "user_status"),
        default=UserStatus.ACTIVE,
        nullable=False,
    )

    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("departments.id"), nullable=True
    )
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("teams.id"), nullable=True
    )
    # Direct supervisor links used for fast RBAC scoping without extra joins.
    team_leader_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    director_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    department: Mapped[Optional["Department"]] = relationship(foreign_keys=[department_id])
    team: Mapped[Optional["Team"]] = relationship(back_populates="members", foreign_keys=[team_id])
    team_leader: Mapped[Optional["User"]] = relationship(
        remote_side=[id], foreign_keys=[team_leader_id]
    )
    director: Mapped[Optional["User"]] = relationship(
        remote_side=[id], foreign_keys=[director_id]
    )
