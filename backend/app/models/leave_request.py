import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import GUID, PortableJSON, TimestampMixin, gen_uuid, str_enum


class LeaveType(str, enum.Enum):
    ANNUAL = "annual"
    SICK = "sick"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    UNPAID = "unpaid"
    EMERGENCY = "emergency"
    OTHER = "other"


# Allowed leave-break durations, in days. "One month" is represented as 30 days.
ALLOWED_LEAVE_DAYS = [5, 10, 15, 20, 25, 30]


class LeaveStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    DIRECTOR_APPROVED = "director_approved"
    DIRECTOR_REJECTED = "director_rejected"
    PENDING_HR = "pending_hr"          # non-Employee submitter: goes straight to HR (or Super Admin if requester IS HR)
    HR_APPROVED = "hr_approved"
    HR_REJECTED = "hr_rejected"


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    leave_type: Mapped[LeaveType] = mapped_column(
        str_enum(LeaveType, "leave_type"), nullable=False
    )
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)

    status: Mapped[LeaveStatus] = mapped_column(
        str_enum(LeaveStatus, "leave_status"),
        default=LeaveStatus.SUBMITTED,
        nullable=False,
    )
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Captured signature images (base64 PNG data URLs from the on-screen signature pad)
    prepared_signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Everything else the rich leave-application form captures (department,
    # job title, phone, contact address, work delegation, HR audit fields,
    # typed requester/approver names+dates) that doesn't map to a dedicated
    # workflow column. Rendered into the PDF when present.
    extra_fields: Mapped[Optional[dict]] = mapped_column(PortableJSON, nullable=True)


class LeaveRequestHistory(Base):
    __tablename__ = "leave_request_history"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    leave_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("leave_requests.id"), nullable=False, index=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False
    )
