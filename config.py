"""Compatibility alias for the former `config` package."""
from __future__ import annotations

import importlib
import sys

_pkg = importlib.import_module("app.config")
sys.modules[__name__] = _pkg
sys.modules.setdefault(f"{__name__}.settings", importlib.import_module("app.config.settings"))
