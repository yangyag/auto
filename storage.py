"""Compatibility alias for the former `storage` package."""
from __future__ import annotations

import importlib
import sys

_pkg = importlib.import_module("app.storage")
sys.modules[__name__] = _pkg
for _submodule in (
    "interfaces",
    "postgres_common",
    "postgres_grid_repository",
    "postgres_order_repository",
    "factory",
):
    sys.modules.setdefault(
        f"{__name__}.{_submodule}",
        importlib.import_module(f"app.storage.{_submodule}"),
    )
