import re
import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.models.user import UserRole
from app.schemas.user import UserPublic

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.]{3,30}$")


def _validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number")
    return password


class RegisterRequest(BaseModel):
    full_name: str
    username: str
    email: EmailStr
    password: str
    confirm_password: str
    role: UserRole
    position: str
    department_id: Optional[uuid.UUID] = None
    # Required when role == employee: the employee's direct team leader
    team_leader_id: Optional[uuid.UUID] = None
    # Required when role == team_leader: the team leader's director
    director_id: Optional[uuid.UUID] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-30 characters: letters, numbers, dot or underscore only"
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("full_name", "position")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("This field cannot be blank")
        return v.strip()

    @model_validator(mode="after")
    def check_passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password and confirm password do not match")
        if self.role == UserRole.EMPLOYEE and not self.team_leader_id:
            raise ValueError("Employees must select their Team Leader")
        if self.role == UserRole.TEAM_LEADER and not self.director_id:
            raise ValueError("Team Leaders must select their Director")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @model_validator(mode="after")
    def check_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @model_validator(mode="after")
    def check_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
