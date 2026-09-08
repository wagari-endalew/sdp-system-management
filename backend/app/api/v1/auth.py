from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_optional_current_user
from app.models.user import User, UserRole
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import Message
from app.schemas.user import UserPublic
from app.services import auth_service
from app.core.security import verify_password, hash_password

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    acting_user: User | None = Depends(get_optional_current_user),
):
    if payload.role in (UserRole.DIRECTOR, UserRole.TEAM_LEADER) and not (
        acting_user and acting_user.role == UserRole.SUPER_ADMIN
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Director and Team Leader accounts can only be created by a Super Admin, from Users management.",
        )
    user = await auth_service.register_user(db, payload)
    if user.status.value == "pending":
        await db.commit()
        # Elevated roles cannot auto-login until activated by a Super Admin.
        return TokenResponse(
            access_token="",
            refresh_token="",
            user=UserPublic.model_validate(user),
        )
    access, refresh = await auth_service.issue_tokens(db, user)
    await db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserPublic.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate(
        db,
        payload.email,
        payload.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    access, refresh = await auth_service.issue_tokens(db, user, remember_me=payload.remember_me)
    await db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserPublic.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    access, refresh, user = await auth_service.rotate_refresh_token(db, payload.refresh_token)
    await db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserPublic.model_validate(user))


@router.post("/logout", response_model=Message)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.logout(db, payload.refresh_token)
    await db.commit()
    return Message(message="Logged out successfully")


@router.post("/logout-all", response_model=Message)
async def logout_all(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await auth_service.logout_all(db, current_user.id)
    await db.commit()
    return Message(message="Logged out from all devices")


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password", response_model=Message)
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        from fastapi import HTTPException
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    await auth_service.logout_all(db, current_user.id)
    await db.commit()
    return Message(message="Password changed. Please log in again.")


@router.post("/forgot-password", response_model=Message)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user:
        token = await auth_service.create_password_reset_token(db, user)
        await db.commit()
        # In production this token is emailed to the user. For this deliverable
        # (no SMTP configured) it is returned only in DEBUG mode for testing.
        from app.core.config import settings
        if settings.DEBUG:
            return Message(message=f"[DEV ONLY] Reset token: {token}")
    return Message(message="If that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=Message)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.reset_password(db, payload.token, payload.new_password)
    await db.commit()
    return Message(message="Password has been reset. Please log in.")
