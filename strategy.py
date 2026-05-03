"""Compatibility alias for the former `strategy` package."""
from __future__ import annotations

import importlib
import sys

_pkg = importlib.import_module("app.strategy")
sys.modules[__name__] = _pkg
for _submodule in ("recenter_preview", "breakout_guard", "grid_strategy"):
    sys.modules.setdefault(
        f"{__name__}.{_submodule}",
        importlib.import_module(f"app.strategy.{_submodule}"),
    )
