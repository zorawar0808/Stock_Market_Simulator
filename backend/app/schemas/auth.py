"""Auth request/response schemas. Never include password_hash in any response model."""
import uuid

from pydantic import BaseModel, EmailStr, Field


class ParticipantRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    invitation_code: str = Field(min_length=1, max_length=32)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: EmailStr
    team_id: uuid.UUID | None
    status: str
    email_verified: bool

    model_config = {"from_attributes": True}


class AdminOut(BaseModel):
    admin_id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    is_active: bool

    model_config = {"from_attributes": True}
