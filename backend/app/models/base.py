"""
Shared mixins and portable column types.

GUID stores as native UUID on PostgreSQL and CHAR(36) on SQLite, so the same
models work against Supabase/Postgres in production and SQLite in tests.
PortableJSON uses JSONB on PostgreSQL and JSON elsewhere.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, TypeDecorator
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON


class GUID(TypeDecorator):
    """Platform-independent UUID column."""

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(str(value)))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


PortableJSON = JSON().with_variant(JSONB, "postgresql")


def str_enum(enum_cls, name: str) -> SAEnum:
    """SQLAlchemy Enum column that stores the lowercase Python Enum VALUE
    (e.g. "active") rather than the default uppercase member NAME
    (e.g. "ACTIVE"). This matches every string the frontend sends/compares
    against, and matches what a person would naturally type if they ever
    edit a row by hand in the Supabase Table Editor.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda cls: [e.value for e in cls],
    )


def gen_uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
        nullable=False,
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
