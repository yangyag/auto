from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import app.config.settings as cfg
from app.api.auth import AuthError, decode_access_token
from app.api.services.repository import MobileApiRepository


bearer_scheme = HTTPBearer(auto_error=False)


def get_api_repository() -> MobileApiRepository:
    return MobileApiRepository.from_config(cfg)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="bearer token required")
    try:
        payload = decode_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return str(payload["sub"])
