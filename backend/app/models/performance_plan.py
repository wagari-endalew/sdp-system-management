import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import GUID, PortableJSON, TimestampMixin, gen_uuid, str_enum


class PlanPeriod(str, enum.Enum):
    SIX_MONTHS = "6_months"
    ONE_YEAR = "1_year"


class PlanStatus(str, enum.Enum):
    SUBMITTED = "submitted"          # awaiting team leader
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"          # awaiting director
    DIRECTOR_APPROVED = "director_approved"
    DIRECTOR_REJECTED = "director_rejected"


class PerformancePlan(Base, TimestampMixin):
    __tablename__ = "performance_plans"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    period: Mapped[PlanPeriod] = mapped_column(
        str_enum(PlanPeriod, "plan_period"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    goals: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    status: Mapped[PlanStatus] = mapped_column(
        str_enum(PlanStatus, "plan_status"),
        default=PlanStatus.SUBMITTED,
        nullable=False,
    )
    technical_committee_comment: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Everything captured by the rich evaluation form (institutional details,
    # 6-month/yearly scoring tables, comments, typed signatures) that doesn't
    # map to a dedicated column. Rendered into the PDF when present.
    extra_fields: Mapped[Optional[dict]] = mapped_column(PortableJSON, nullable=True)

    # Captured signature images (base64 PNG data URLs from the on-screen signature pad)
    prepared_signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PerformancePlanHistory(Base):
    __tablename__ = "performance_plan_history"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=gen_uuid)
    plan_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("performance_plans.id"), nullable=False, index=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False
    )
