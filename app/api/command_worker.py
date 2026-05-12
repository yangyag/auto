from __future__ import annotations

import argparse

from app.api.services.command_service import execute_command_once, worker_loop
from app.api.services.repository import MobileApiRepository
import app.config.settings as cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.api.command_worker")
    parser.add_argument("--once", action="store_true", help="Run at most one queued command and exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args(argv)

    if args.once:
        return 0 if execute_command_once(MobileApiRepository.from_config(cfg)) else 1

    worker_loop(poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
