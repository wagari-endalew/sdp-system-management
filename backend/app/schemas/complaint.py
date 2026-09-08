import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.complaint import ComplaintStatus

RECIPIENT_OPTIONS = {"super_admin", "technical_committee", "human_resource", "director", "team_leader", "employee"}


class ComplaintCreate(BaseModel):
    category: str = "General"
    subject: str = Field(min_length=3)
    message: str = Field(min_length=5)
    # Who the complainant explicitly chose to send this to. Optional for
    # backward compatibility — omitting it falls back to the old behavior
    # (auto-derived from the submitter's own reporting line).
    recipient: Optional[str] = None
    target_user_id: Optional[uuid.UUID] = None
    target_label: Optional[str] = None

    @model_validator(mode="after")
    def check_recipient(self) -> "ComplaintCreate":
        if self.recipient is None:
            return self
        if self.recipient not in RECIPIENT_OPTIONS:
            raise ValueError(f"recipient must be one of {sorted(RECIPIENT_OPTIONS)}")
        if self.recipient in ("director", "team_leader") and not self.target_user_id:
            raise ValueError(f"Select a specific {self.recipient.replace('_', ' ')}")
        if self.recipient == "employee" and not (self.target_label and self.target_label.strip()):
            raise ValueError("Enter the employee's name")
        return self


class ComplaintRespond(BaseModel):
    message: str = Field(min_length=1)
    resolve: bool = False
    reject: bool = False


class ComplaintEscalate(BaseModel):
    message: Optional[str] = None


class ComplaintPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    category: str
    subject: str
    message: str
    status: ComplaintStatus
    current_handler_role: str
    target_user_id: Optional[uuid.UUID] = None
    target_label: Optional[str] = None
    resolution: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime
