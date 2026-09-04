"""Compatibility facade for output image services."""

from __future__ import annotations

import sys

from services.visual import output as _impl
from services.visual.output import *  # noqa: F401,F403

_current_module = sys.modules[__name__]
sys.modules["services.output_image_service"] = _current_module
sys.modules["backend.services.output_image_service"] = _current_module
if services_package := sys.modules.get("services"):
    setattr(services_package, "output_image_service", _current_module)
if backend_services_package := sys.modules.get("backend.services"):
    setattr(backend_services_package, "output_image_service", _current_module)


def __getattr__(name: str):
    """Forward legacy attribute access to the implementation module."""

    return getattr(_impl, name)


def __dir__() -> list[str]:
    """Return facade and implementation attributes for interactive inspection."""

    return sorted(set(globals()) | set(dir(_impl)))
