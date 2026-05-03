"""Compatibility alias for the former `exchange` package."""
from __future__ import annotations

import importlib
import sys

_pkg = importlib.import_module("app.exchange")
sys.modules[__name__] = _pkg
for _submodule in ("base", "upbit_ws", "crypto", "stock"):
    sys.modules.setdefault(
        f"{__name__}.{_submodule}",
        importlib.import_module(f"app.exchange.{_submodule}"),
    )
