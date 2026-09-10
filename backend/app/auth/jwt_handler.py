"""
JWT access/refresh token issuance and verification (spec sections 7, 8, 57).

Tokens embed `sub` (the account id), `kind` ("user" or "admin"), and for
admins, `role`, so that RBAC checks (rbac.py) don't need a DB round-trip on
every request. Tokens are short-lived; refresh tokens are longer-lived and
only ever exchanged for a new access token, never accepted directly by
protected endpoints.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()

TokenKind = Literal["user", "admin"]


def _create_token(subject: str, kind: TokenKind, expires_delta: timedelta, extra_claims: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "kind": kind,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str, kind: TokenKind, extra_claims: dict | None = None) -> str:
    return _create_token(
        subject, kind, timedelta(minutes=settings.access_token_expire_minutes), extra_claims
    )


def create_refresh_token(subject: str, kind: TokenKind) -> str:
    return _create_token(
        subject, kind, timedelta(days=settings.refresh_token_expire_days), {"token_type": "refresh"}
    )


def decode_token(token: str) -> dict:
    """Raises jose.JWTError on invalid/expired tokens - callers must catch it."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


__all__ = ["create_access_token", "create_refresh_token", "decode_token", "JWTError"]
