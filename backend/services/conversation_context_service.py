"""Compatibility facade for conversation context services.

The implementation lives in ``services.conversation.context``. This module keeps
legacy imports such as ``services.conversation_context_service`` and
``backend.services.conversation_context_service`` working during the service
directory consolidation.
"""

from __future__ import annotations

import sys

from services.conversation import context as _impl
from services.conversation.context import *  # noqa: F401,F403

_current_module = sys.modules[__name__]
sys.modules["services.conversation_context_service"] = _current_module
sys.modules["backend.services.conversation_context_service"] = _current_module
if services_package := sys.modules.get("services"):
    setattr(services_package, "conversation_context_service", _current_module)
if backend_services_package := sys.modules.get("backend.services"):
    setattr(backend_services_package, "conversation_context_service", _current_module)


def __getattr__(name: str):
    """Forward legacy attribute access to the implementation module."""

    return getattr(_impl, name)


def __dir__() -> list[str]:
    """Return facade and implementation attributes for interactive inspection."""

    return sorted(set(globals()) | set(dir(_impl)))
