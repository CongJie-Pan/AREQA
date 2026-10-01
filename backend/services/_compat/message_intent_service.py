"""Compatibility alias for ``services.orchestration.message_intent``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.orchestration.message_intent")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.message_intent_service"] = _impl
        setattr(_package, "message_intent_service", _impl)
