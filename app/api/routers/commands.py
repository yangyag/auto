from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import AuthError, validate_command_totp
from app.api.deps import get_api_repository, get_current_user
from app.api.schemas.command import (
    AdjustBudgetRequest,
    CommandCreateResponse,
    CommandResponse,
    CommandTotpRequest,
    ResetStopLossRequest,
)
from app.api.services.command_service import command_response, enqueue_command
from app.api.services.repository import MobileApiRepository


router = APIRouter(prefix="/v1/commands", tags=["commands"], dependencies=[Depends(get_current_user)])


def _require_totp(code: str | None) -> None:
    try:
        validate_command_totp(code)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _created(response: CommandResponse) -> CommandCreateResponse:
    return CommandCreateResponse(id=response.id, status=response.status)


@router.post("/bot/stop", response_model=CommandCreateResponse, status_code=202)
def stop_bot(
    payload: CommandTotpRequest,
    user: str = Depends(get_current_user),
    repository: MobileApiRepository = Depends(get_api_repository),
) -> CommandCreateResponse:
    _require_totp(payload.totp_code)
    return _created(enqueue_command(repository, kind="bot_stop", params={}, requested_by=user))


@router.post("/bot/start", response_model=CommandCreateResponse, status_code=202)
def start_bot(
    payload: CommandTotpRequest,
    user: str = Depends(get_current_user),
    repository: MobileApiRepository = Depends(get_api_repository),
) -> CommandCreateResponse:
    _require_totp(payload.totp_code)
    return _created(enqueue_command(repository, kind="bot_start", params={}, requested_by=user))


@router.post("/reset", response_model=CommandCreateResponse, status_code=202)
def reset(
    payload: CommandTotpRequest,
    user: str = Depends(get_current_user),
    repository: MobileApiRepository = Depends(get_api_repository),
) -> CommandCreateResponse:
    _require_totp(payload.totp_code)
    if payload.confirmation != "RESET":
        raise HTTPException(status_code=400, detail="confirmation must be RESET")
    return _created(enqueue_command(repository, kind="reset", params={}, requested_by=user))


@router.post("/adjust-budget", response_model=CommandCreateResponse, status_code=202)
def adjust_budget(
    payload: AdjustBudgetRequest,
    user: str = Depends(get_current_user),
    repository: MobileApiRepository = Depends(get_api_repository),
) -> CommandCreateResponse:
    _require_totp(payload.totp_code)
    if payload.confirmation != "ADJUST_BUDGET":
        raise HTTPException(status_code=400, detail="confirmation must be ADJUST_BUDGET")
    return _created(
        enqueue_command(
            repository,
            kind="adjust_budget",
            params={"target_budget": str(payload.target_budget), "force": payload.force},
            requested_by=user,
        )
    )


@router.post("/reset-stop-loss", response_model=CommandCreateResponse, status_code=202)
def reset_stop_loss(
    payload: ResetStopLossRequest,
    user: str = Depends(get_current_user),
    repository: MobileApiRepository = Depends(get_api_repository),
) -> CommandCreateResponse:
    _require_totp(payload.totp_code)
    return _created(
        enqueue_command(
            repository,
            kind="reset_stop_loss",
            params={"force": payload.force},
            requested_by=user,
        )
    )


@router.get("/{command_id}", response_model=CommandResponse)
def get_command(
    command_id: str,
    repository: MobileApiRepository = Depends(get_api_repository),
) -> CommandResponse:
    row = repository.get_command(command_id)
    if row is None:
        raise HTTPException(status_code=404, detail="command not found")
    return command_response(row)
