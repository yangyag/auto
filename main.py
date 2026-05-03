"""Compatibility entrypoint for the trading bot CLI."""
from app.main import *  # noqa: F401,F403
from app.main import main as _main


if __name__ == "__main__":
    raise SystemExit(_main())
