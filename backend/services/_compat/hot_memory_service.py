"""Compatibility alias for ``services.memory.hot``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.memory.hot")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.hot_memory_service"] = _impl
        setattr(_package, "hot_memory_service", _impl)
