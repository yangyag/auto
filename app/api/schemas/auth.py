from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ApiModel


class LoginRequest(ApiModel):
    username: str
    password: str
    totp_code: str | None = None


class RefreshRequest(ApiModel):
    refresh_token: str


class LogoutRequest(ApiModel):
    refresh_token: str


class TokenResponse(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class LogoutResponse(ApiModel):
    status: str
