"""Compatibility alias for the former `core` package."""
from __future__ import annotations

import importlib
import sys

_pkg = importlib.import_module("app.core")
sys.modules[__name__] = _pkg
for _submodule in ("models", "grid_properties", "grid_builder", "grid"):
    sys.modules.setdefault(
        f"{__name__}.{_submodule}",
        importlib.import_module(f"app.core.{_submodule}"),
    )
