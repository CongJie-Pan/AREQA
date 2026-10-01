"""Compatibility alias for ``services.conversation.parts``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.conversation.parts")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.parts_context_service"] = _impl
        setattr(_package, "parts_context_service", _impl)
