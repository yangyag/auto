from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt

try:
    import pyotp
except ModuleNotFoundError:  # pragma: no cover - optional until dependency installed
    pyotp = None


ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30
JWT_ALGORITHM = "HS256"


class AuthError(RuntimeError):
    pass


def api_username() -> str:
    return os.getenv("MOBILE_API_USERNAME", "admin")


def _api_password() -> str:
    return os.getenv("MOBILE_API_PASSWORD", "")


def jwt_secret() -> str:
    secret = os.getenv("MOBILE_API_JWT_SECRET", "")
    if not secret:
        raise AuthError("MOBILE_API_JWT_SECRET is not configured")
    return secret


def verify_password(username: str, password: str) -> bool:
    configured_password = _api_password()
    if not configured_password:
        return False
    return hmac.compare_digest(username, api_username()) and hmac.compare_digest(
        password,
        configured_password,
    )


def totp_required() -> bool:
    return bool(os.getenv("MOBILE_API_TOTP_SECRET", ""))


def verify_totp(code: str | None) -> bool:
    secret = os.getenv("MOBILE_API_TOTP_SECRET", "")
    if not secret:
        return True
    if not code or pyotp is None:
        return False
    return bool(pyotp.TOTP(secret).verify(code, valid_window=1))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(username: str) -> str:
    now = _utcnow()
    payload = {
        "sub": username,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError("invalid access token") from exc
    if payload.get("typ") != "access" or not payload.get("sub"):
        raise AuthError("invalid access token")
    return payload


def create_refresh_token() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(48)
    return token, hash_refresh_token(token), _utcnow() + timedelta(days=REFRESH_TOKEN_DAYS)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_response(username: str, refresh_token: str):
    return {
        "access_token": create_access_token(username),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    }


def validate_command_totp(code: str | None, *, required: bool = True) -> None:
    if required and not verify_totp(code):
        raise AuthError("valid TOTP code required")
