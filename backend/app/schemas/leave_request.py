import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.leave_request import ALLOWED_LEAVE_DAYS, LeaveStatus, LeaveType

MAX_SIGNATURE_LEN = 300_000  # ~225KB decoded; generous for a canvas-drawn PNG signature


def _validate_signature(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    if not v.startswith("data:image/"):
        raise ValueError("Signature must be a base64 image data URL (data:image/...)")
    if len(v) > MAX_SIGNATURE_LEN:
        raise ValueError("Signature image is too large")
    return v


class LeaveCreate(BaseModel):
    leave_type: LeaveType
    days: int
    start_date: date
    reason: str = Field(min_length=3)
    prepared_signature: Optional[str] = None
    extra_fields: Optional[dict[str, Any]] = None

    @field_validator("days")
    @classmethod
    def validate_days(cls, v: int) -> int:
        if v not in ALLOWED_LEAVE_DAYS:
            raise ValueError(
                f"Days must be one of {ALLOWED_LEAVE_DAYS} (30 represents a one-month leave break)"
            )
        return v

    @field_validator("prepared_signature")
    @classmethod
    def validate_sig(cls, v):
        return _validate_signature(v)

    @model_validator(mode="after")
    def compute_ok(self) -> "LeaveCreate":
        return self


class LeaveReject(BaseModel):
    reason: str = Field(min_length=3)
    signature: Optional[str] = None

    @field_validator("signature")
    @classmethod
    def validate_sig(cls, v):
        return _validate_signature(v)


class LeaveEscalate(BaseModel):
    reason: str = Field(min_length=3)


class LeaveDecision(BaseModel):
    reason: Optional[str] = None
    signature: Optional[str] = None

    @field_validator("signature")
    @classmethod
    def validate_sig(cls, v):
        return _validate_signature(v)


class LeavePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    leave_type: LeaveType
    days: int
    start_date: date
    end_date: date
    reason: str
    status: LeaveStatus
    decided_by: Optional[uuid.UUID]
    decision_reason: Optional[str]
    decided_at: Optional[datetime]
    prepared_signature: Optional[str] = None
    decided_signature: Optional[str] = None
    extra_fields: Optional[dict[str, Any]] = None
    created_at: datetime
