import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.token import LoginHistory, PasswordResetToken, RefreshToken
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth import RegisterRequest


# Registration no longer gates any role behind Super Admin activation — every
# role auto-activates immediately (see create_plan/register_user below).
# Fixed bcrypt hash used to normalize login timing when no account exists —
# see the comment in authenticate() below for why this matters.
_DUMMY_PASSWORD_HASH = "$2b$12$fa.gExN4Chlw0XCMb3Byhuu7XTpJLyLnU5GHzXH6kPotUKISVcCoO"


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    existing = await db.execute(
        select(User).where(
            or_(User.email == payload.email.lower(), User.username == payload.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email or username already exists",
        )

    if payload.team_leader_id:
        tl = await db.get(User, payload.team_leader_id)
        if not tl or tl.role != UserRole.TEAM_LEADER:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected Team Leader is invalid")

    if payload.director_id:
        director = await db.get(User, payload.director_id)
        if not director or director.role != UserRole.DIRECTOR:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected Director is invalid")

    initial_status = UserStatus.ACTIVE

    user = User(
        full_name=payload.full_name,
        username=payload.username,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        position=payload.position,
        department_id=payload.department_id,
        team_leader_id=payload.team_leader_id,
        director_id=payload.director_id,
        status=initial_status,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate(
    db: AsyncSession, email: str, password: str, ip_address: str | None, user_agent: str | None
) -> User:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()

    # Security: always run the (slow, bcrypt) password check, even when the
    # account doesn't exist, using a fixed dummy hash. Short-circuiting this
    # when `user is None` makes "no such account" responses measurably
    # faster than "wrong password" ones, letting an attacker enumerate valid
    # emails (e.g. probing for real Director/Super Admin accounts) purely by
    # timing the login endpoint — the error message being identical doesn't
    # help if the response latency gives it away.
    hash_to_check = user.password_hash if user else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, hash_to_check)
    success = bool(user and not user.is_deleted and password_ok)

    db.add(
        LoginHistory(
            user_id=user.id if user else None,
            email_attempted=email.lower(),
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
        )
    )

    if not success:
        await db.flush()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if user.status == UserStatus.PENDING:
        await db.flush()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your account is pending activation by a Super Admin",
        )
    if user.status == UserStatus.SUSPENDED:
        await db.flush()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account has been suspended")

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def issue_tokens(db: AsyncSession, user: User, remember_me: bool = False) -> tuple[str, str]:
    days = settings.REMEMBER_ME_REFRESH_TOKEN_EXPIRE_DAYS if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
    access = create_access_token(str(user.id), user.role.value)
    refresh, jti = create_refresh_token(str(user.id), days=days)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(days=days),
        )
    )
    await db.flush()
    return access, refresh


async def rotate_refresh_token(db: AsyncSession, refresh_token: str) -> tuple[str, str, User]:
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")

    jti = payload.get("jti")
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    stored = result.scalar_one_or_none()
    if not stored or stored.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token revoked or not found")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user or user.is_deleted or user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is not active")

    # Rotate: revoke old, issue new
    stored.revoked = True
    access, new_refresh = await issue_tokens(db, user)
    return access, new_refresh, user


async def logout(db: AsyncSession, refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        return
    jti = payload.get("jti")
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
        await db.flush()


async def logout_all(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)))
    for token in result.scalars().all():
        token.revoked = True
    await db.flush()


async def create_password_reset_token(db: AsyncSession, user: User) -> str:
    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    await db.flush()
    return raw_token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.used.is_(False))
    )
    candidates = result.scalars().all()
    matched: PasswordResetToken | None = None
    for candidate in candidates:
        if verify_password(token, candidate.token_hash):
            matched = candidate
            break

    if not matched or matched.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    user = await db.get(User, matched.user_id)
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "User no longer exists")

    user.password_hash = hash_password(new_password)
    matched.used = True
    await logout_all(db, user.id)
    await db.flush()
