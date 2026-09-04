"""Compatibility facade for attachment image storage services."""

from __future__ import annotations

import sys

from services.attachments import storage as _impl
from services.attachments.storage import *  # noqa: F401,F403

_current_module = sys.modules[__name__]
sys.modules["services.attachment_image_storage_service"] = _current_module
sys.modules["backend.services.attachment_image_storage_service"] = _current_module
if services_package := sys.modules.get("services"):
    setattr(services_package, "attachment_image_storage_service", _current_module)
if backend_services_package := sys.modules.get("backend.services"):
    setattr(backend_services_package, "attachment_image_storage_service", _current_module)


def __getattr__(name: str):
    """Forward legacy attribute access to the implementation module."""

    return getattr(_impl, name)


def __dir__() -> list[str]:
    """Return facade and implementation attributes for interactive inspection."""

    return sorted(set(globals()) | set(dir(_impl)))
