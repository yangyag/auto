from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api import auth as auth_utils
from app.api.deps import get_api_repository
from app.api.schemas.auth import LoginRequest, LogoutRequest, LogoutResponse, RefreshRequest, TokenResponse
from app.api.services.repository import MobileApiRepository


router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    repository: MobileApiRepository = Depends(get_api_repository),
) -> TokenResponse:
    if not auth_utils.verify_password(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not auth_utils.verify_totp(payload.totp_code):
        raise HTTPException(status_code=401, detail="invalid TOTP code")

    refresh_token, token_hash, expires_at = auth_utils.create_refresh_token()
    repository.create_refresh_token(
        token_hash=token_hash,
        username=payload.username,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        client_host=request.client.host if request.client else None,
    )
    return TokenResponse(**auth_utils.token_response(payload.username, refresh_token))


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    request: Request,
    repository: MobileApiRepository = Depends(get_api_repository),
) -> TokenResponse:
    new_refresh_token, new_hash, expires_at = auth_utils.create_refresh_token()
    username = repository.rotate_refresh_token(
        old_token_hash=auth_utils.hash_refresh_token(payload.refresh_token),
        new_token_hash=new_hash,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        client_host=request.client.host if request.client else None,
    )
    if username is None:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    return TokenResponse(**auth_utils.token_response(username, new_refresh_token))


@router.post("/logout", response_model=LogoutResponse)
def logout(
    payload: LogoutRequest,
    repository: MobileApiRepository = Depends(get_api_repository),
) -> LogoutResponse:
    repository.revoke_refresh_token(token_hash=auth_utils.hash_refresh_token(payload.refresh_token))
    return LogoutResponse(status="ok")
