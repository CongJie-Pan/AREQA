"""Compatibility alias for ``services.conversation.response_boundary``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.conversation.response_boundary")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.response_boundary_validator"] = _impl
        setattr(_package, "response_boundary_validator", _impl)
