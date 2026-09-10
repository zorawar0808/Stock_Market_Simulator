"""
FastAPI dependencies for authentication + role-based access control.
"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import JWTError, decode_token
from app.database import get_db
from app.models.base import AdminRole
from app.models.user import Admin, User


oauth2_scheme = HTTPBearer(auto_error=False)
admin_oauth2_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized("Not authenticated")

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError:
        raise _unauthorized()

    if payload.get("kind") != "user" or payload.get("token_type") == "refresh":
        raise _unauthorized("Wrong token type")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise _unauthorized()

    user = await db.get(User, user_id)

    if user is None:
        raise _unauthorized("User no longer exists")

    return user


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(admin_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    if credentials is None:
        raise _unauthorized("Not authenticated")

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError:
        raise _unauthorized()

    if payload.get("kind") != "admin" or payload.get("token_type") == "refresh":
        raise _unauthorized("Wrong token type")

    try:
        admin_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise _unauthorized()

    admin = await db.get(Admin, admin_id)

    if admin is None or not admin.is_active:
        raise _unauthorized("Admin account inactive or missing")

    return admin


def require_role(*allowed_roles: AdminRole):
    """
    Usage:
        admin: Admin = Depends(
            require_role(AdminRole.SUPER_ADMIN)
        )

    SUPER_ADMIN implicitly passes every role check.
    """

    async def _dependency(
        admin: Admin = Depends(get_current_admin),
    ) -> Admin:
        if admin.role == AdminRole.SUPER_ADMIN:
            return admin

        if admin.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {admin.role.value} is not permitted to perform this action",
            )

        return admin

    return _dependency
