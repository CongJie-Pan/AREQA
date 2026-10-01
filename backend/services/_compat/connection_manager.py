"""Compatibility alias for ``services.notifications.connections``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.notifications.connections")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.connection_manager"] = _impl
        setattr(_package, "connection_manager", _impl)
