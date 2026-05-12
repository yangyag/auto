from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.api.schemas.common import ApiModel


CommandKind = Literal["bot_stop", "bot_start", "reset", "adjust_budget", "reset_stop_loss"]
CommandStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class CommandCreateResponse(ApiModel):
    id: str
    status: CommandStatus


class CommandResponse(ApiModel):
    id: str
    kind: CommandKind
    params: dict[str, Any]
    status: CommandStatus
    requested_by: str
    requested_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log_tail: str
    result: dict[str, Any] | None = None
    error: str | None = None


class CommandTotpRequest(ApiModel):
    totp_code: str | None = None
    confirmation: str | None = None


class AdjustBudgetRequest(CommandTotpRequest):
    target_budget: Decimal
    force: bool = False


class ResetStopLossRequest(CommandTotpRequest):
    force: bool = False
