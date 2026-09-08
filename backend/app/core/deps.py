import uuid
from typing import Sequence

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole, UserStatus

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error
    try:
        payload = decode_token(token)
    except ValueError:
        raise credentials_error
    if payload.get("type") != "access":
        raise credentials_error
    user_id = payload.get("sub")
    if not user_id:
        raise credentials_error

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or user.is_deleted:
        raise credentials_error
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Contact an administrator.",
        )
    return user


async def get_optional_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like get_current_user, but returns None instead of raising for a
    missing/invalid/expired token — for endpoints that behave differently
    for an authenticated caller but must still work anonymously (e.g.
    /auth/register: open to the public for most roles, but Director/Team
    Leader creation additionally allows a logged-in Super Admin through)."""
    if not token:
        return None
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    if payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or user.is_deleted or user.status != UserStatus.ACTIVE:
        return None
    return user


def require_roles(*roles: UserRole):
    """Dependency factory enforcing RBAC: caller's role must be in `roles`."""

    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return checker


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
