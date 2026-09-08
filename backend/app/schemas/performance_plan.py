import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.performance_plan import PlanPeriod, PlanStatus

MAX_SIGNATURE_LEN = 300_000  # ~225KB decoded; generous for a canvas-drawn PNG signature


def _validate_signature(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    if not v.startswith("data:image/"):
        raise ValueError("Signature must be a base64 image data URL (data:image/...)")
    if len(v) > MAX_SIGNATURE_LEN:
        raise ValueError("Signature image is too large")
    return v


class PlanCreate(BaseModel):
    period: PlanPeriod
    title: str
    goals: list[dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None
    prepared_signature: Optional[str] = None
    extra_fields: Optional[dict[str, Any]] = None

    @field_validator("title")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title cannot be blank")
        return v.strip()

    @field_validator("goals")
    @classmethod
    def at_least_one_goal(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one goal/checklist item is required")
        return v

    @field_validator("prepared_signature")
    @classmethod
    def validate_sig(cls, v):
        return _validate_signature(v)


class PlanUpdate(BaseModel):
    title: Optional[str] = None
    goals: Optional[list[dict[str, Any]]] = None
    notes: Optional[str] = None
    prepared_signature: Optional[str] = None

    @field_validator("prepared_signature")
    @classmethod
    def validate_sig(cls, v):
        return _validate_signature(v)


class PlanDecision(BaseModel):
    reason: Optional[str] = None
    signature: Optional[str] = None

    @field_validator("signature")
    @classmethod
    def validate_sig(cls, v):
        return _validate_signature(v)


class PlanReject(BaseModel):
    reason: str = Field(min_length=3)
    signature: Optional[str] = None

    @field_validator("signature")
    @classmethod
    def validate_sig(cls, v):
        return _validate_signature(v)


class PlanEscalate(BaseModel):
    reason: str = Field(min_length=3)


class PlanComment(BaseModel):
    comment: str = Field(min_length=1)


class PlanHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_id: Optional[uuid.UUID]
    action: str
    reason: Optional[str]
    created_at: datetime


class PlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    period: PlanPeriod
    title: str
    goals: list[dict[str, Any]]
    notes: Optional[str]
    status: PlanStatus
    technical_committee_comment: Optional[str]
    decided_by: Optional[uuid.UUID]
    decision_reason: Optional[str]
    decided_at: Optional[datetime]
    prepared_signature: Optional[str] = None
    decided_signature: Optional[str] = None
    extra_fields: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
