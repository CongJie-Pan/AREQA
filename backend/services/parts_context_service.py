"""Compatibility facade for LearnLM PARTS context services.

The implementation lives in ``services.conversation.parts``. This module keeps
legacy imports such as ``services.parts_context_service`` and
``backend.services.parts_context_service`` working while the conversation domain
is grouped under one package.
"""

from __future__ import annotations

import sys

from services.conversation import parts as _impl
from services.conversation.parts import *  # noqa: F401,F403

_current_module = sys.modules[__name__]
sys.modules["services.parts_context_service"] = _current_module
sys.modules["backend.services.parts_context_service"] = _current_module
if services_package := sys.modules.get("services"):
    setattr(services_package, "parts_context_service", _current_module)
if backend_services_package := sys.modules.get("backend.services"):
    setattr(backend_services_package, "parts_context_service", _current_module)


def __getattr__(name: str):
    """Forward legacy attribute access to the implementation module."""

    return getattr(_impl, name)


def __dir__() -> list[str]:
    """Return facade and implementation attributes for interactive inspection."""

    return sorted(set(globals()) | set(dir(_impl)))
