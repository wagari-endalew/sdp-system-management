import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import GUID, TimestampMixin, gen_uuid, str_enum


class ComplaintStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    ESCALATED_DIRECTOR = "escalated_director"
    ESCALATED_SUPER_ADMIN = "escalated_super_admin"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class Complaint(Base, TimestampMixin):
    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(4000), nullable=False)

    status: Mapped[ComplaintStatus] = mapped_column(
        str_enum(ComplaintStatus, "complaint_status"),
        default=ComplaintStatus.SUBMITTED,
        nullable=False,
    )
    current_handler_role: Mapped[str] = mapped_column(String(50), default="team_leader", nullable=False)
    # When the complainant picked a SPECIFIC director/team leader from the
    # routing form (rather than the system auto-deriving one from their own
    # reporting line), this pins the complaint to that one person — anyone
    # else holding the same role must not be able to see or act on it.
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    # Human-readable label for the chosen recipient/employee-of-concern,
    # kept even if target_user_id is None (broadcast roles) or the named
    # employee doesn't correspond to a real account.
    target_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(4000), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ComplaintResponse(Base):
    __tablename__ = "complaint_responses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    complaint_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("complaints.id"), nullable=False, index=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(String(4000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False
    )
