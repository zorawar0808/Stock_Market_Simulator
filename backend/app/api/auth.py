"""
Auth endpoints (spec section 7): participant registration/login and admin
login. Admin accounts are provisioned out-of-band by a SUPER_ADMIN (see
app/services/team_service.py pattern — an equivalent `admin_service.create_admin`
should be added alongside the admin-management API), never self-registered.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import create_access_token, create_refresh_token, decode_token, JWTError
from app.auth.security import hash_password, verify_password  # noqa: F401 (hash_password used by team_service)
from app.database import get_db
from app.models.user import Admin, User
from app.schemas.auth import (
    AdminOut,
    LoginRequest,
    ParticipantRegisterRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from app.services.audit_service import record as audit_record
from app.services.team_service import RegistrationError, register_participant

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: ParticipantRegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_participant(
            db,
            name=payload.name,
            email=payload.email,
            password=payload.password,
            invitation_code=payload.invitation_code,
        )
    except RegistrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)

    await audit_record(db, actor=f"user:{user.user_id}", action="REGISTER", metadata={"email": user.email})
    await db.commit()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(str(user.user_id), "user")
    refresh_token = create_refresh_token(str(user.user_id), "user")
    await audit_record(db, actor=f"user:{user.user_id}", action="LOGIN")
    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/admin/login", response_model=TokenResponse)
async def admin_login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Admin).where(Admin.email == payload.email))
    admin = result.scalar_one_or_none()
    if admin is None or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(str(admin.admin_id), "admin", {"role": admin.role.value})
    refresh_token = create_refresh_token(str(admin.admin_id), "admin")
    await audit_record(db, actor=f"admin:{admin.admin_id}", action="ADMIN_LOGIN", metadata={"role": admin.role.value})
    await db.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest):
    try:
        decoded = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    if decoded.get("token_type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    kind = decoded["kind"]
    subject = decoded["sub"]
    extra = {"role": decoded["role"]} if kind == "admin" and "role" in decoded else None
    new_access = create_access_token(subject, kind, extra)
    new_refresh = create_refresh_token(subject, kind)
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)
