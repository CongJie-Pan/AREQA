"""Compatibility facade for conversation streaming services.

The implementation lives in ``services.conversation.stream``. This module keeps
legacy imports and test patch paths stable while the implementation is grouped
with the rest of the conversation domain.
"""

from __future__ import annotations

import sys

from services.conversation import stream as _impl
from services.conversation.stream import *  # noqa: F401,F403

_current_module = sys.modules[__name__]
sys.modules["services.conversation_stream_service"] = _current_module
sys.modules["backend.services.conversation_stream_service"] = _current_module
if services_package := sys.modules.get("services"):
    setattr(services_package, "conversation_stream_service", _current_module)
if backend_services_package := sys.modules.get("backend.services"):
    setattr(backend_services_package, "conversation_stream_service", _current_module)


def __getattr__(name: str):
    """Forward legacy attribute access to the implementation module."""

    return getattr(_impl, name)


def __dir__() -> list[str]:
    """Return facade and implementation attributes for interactive inspection."""

    return sorted(set(globals()) | set(dir(_impl)))
