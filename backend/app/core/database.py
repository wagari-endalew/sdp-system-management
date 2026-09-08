"""
Async SQLAlchemy 2.x engine & session management.
Works against Supabase/PostgreSQL in production and SQLite (aiosqlite) in tests.
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def _make_engine(url: str):
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_async_engine(
        url,
        echo=settings.DEBUG and settings.ENV == "development",
        future=True,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


engine = _make_engine(settings.DATABASE_URL)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_models() -> None:
    """Create all tables. Used on startup for dev/demo and by the test-suite.

    In production, prefer Alembic migrations (see /backend/alembic).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
