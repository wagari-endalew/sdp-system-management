import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message: str
    link: Optional[str]
    is_read: bool
    created_at: datetime
