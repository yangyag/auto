from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import app.config.settings as cfg
from app.api.errors import ApiError
from app.api.schemas.command import CommandResponse
from app.api.services.repository import MobileApiRepository


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SECRET_PATTERNS = [
    re.compile(r"UPBIT_ACCESS_KEY=\S+"),
    re.compile(r"UPBIT_SECRET_KEY=\S+"),
    re.compile(r"Authorization: Bearer\s+\S+", re.IGNORECASE),
]


def redact_log(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[-20000:]


def command_response(row: dict[str, Any]) -> CommandResponse:
    return CommandResponse(
        id=row["id"],
        kind=row["kind"],
        params=row["params"] or {},
        status=row["status"],
        requested_by=row["requested_by"],
        requested_at=row["requested_at"],
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        log_tail=(row.get("log") or "")[-4000:],
        result=row.get("result"),
        error=row.get("error"),
    )


def enqueue_command(
    repository: MobileApiRepository,
    *,
    kind: str,
    params: dict[str, Any],
    requested_by: str,
) -> CommandResponse:
    try:
        row = repository.enqueue_command(kind=kind, params=params, requested_by=requested_by)
    except Exception as exc:
        if "commands_one_active_kind_idx" in str(exc):
            raise ApiError(f"active command already exists for kind={kind}", status_code=409) from exc
        raise
    return command_response(row)


def build_command_argv(command: dict[str, Any]) -> tuple[list[str], str | None]:
    kind = command["kind"]
    params = command.get("params") or {}
    python_bin = os.getenv("PYTHON_BIN", sys.executable)

    if kind == "bot_stop":
        return [str(PROJECT_ROOT / "stop.sh")], None
    if kind == "bot_start":
        return [str(PROJECT_ROOT / "run.sh")], None
    if kind == "reset":
        return [python_bin, "scripts/reset_live.py"], None
    if kind == "adjust_budget":
        target_budget = str(params["target_budget"])
        argv = [python_bin, "scripts/adjust_budget_live.py", "--target-budget", target_budget]
        if params.get("force"):
            argv.append("--force")
        return argv, "y\n"
    if kind == "reset_stop_loss":
        argv = [python_bin, "main.py", "reset-stop-loss"]
        if params.get("force"):
            argv.append("--force")
        return argv, None

    raise ValueError(f"unsupported command kind: {kind}")


def execute_command_once(repository: MobileApiRepository) -> bool:
    command = repository.claim_next_command()
    if command is None:
        return False

    try:
        argv, stdin_text = build_command_argv(command)
        completed = subprocess.run(
            argv,
            cwd=PROJECT_ROOT,
            input=stdin_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=int(os.getenv("MOBILE_API_COMMAND_TIMEOUT_SECONDS", "900")),
        )
        log = redact_log((completed.stdout or "") + (completed.stderr or ""))
        if completed.returncode == 0:
            repository.finish_command(
                command_id=command["id"],
                status="succeeded",
                log=log,
                result={"returncode": completed.returncode},
            )
        else:
            repository.finish_command(
                command_id=command["id"],
                status="failed",
                log=log,
                result={"returncode": completed.returncode},
                error=f"command exited with {completed.returncode}",
            )
    except Exception as exc:
        repository.finish_command(
            command_id=command["id"],
            status="failed",
            log="",
            error=str(exc),
        )
    return True


def worker_loop(*, poll_seconds: float = 2.0) -> None:
    repository = MobileApiRepository.from_config(cfg)
    while True:
        did_work = execute_command_once(repository)
        if not did_work:
            time.sleep(poll_seconds)
