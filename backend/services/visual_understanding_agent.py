"""Compatibility facade for visual understanding services."""

from __future__ import annotations

import sys

from services.visual import understanding as _impl
from services.visual.understanding import *  # noqa: F401,F403

_current_module = sys.modules[__name__]
sys.modules["services.visual_understanding_agent"] = _current_module
sys.modules["backend.services.visual_understanding_agent"] = _current_module
if services_package := sys.modules.get("services"):
    setattr(services_package, "visual_understanding_agent", _current_module)
if backend_services_package := sys.modules.get("backend.services"):
    setattr(backend_services_package, "visual_understanding_agent", _current_module)


def __getattr__(name: str):
    """Forward legacy attribute access to the implementation module."""

    return getattr(_impl, name)


def __dir__() -> list[str]:
    """Return facade and implementation attributes for interactive inspection."""

    return sorted(set(globals()) | set(dir(_impl)))
