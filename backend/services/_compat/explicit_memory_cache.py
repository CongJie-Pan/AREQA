"""Compatibility alias for ``services.memory.recall_cache``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.memory.recall_cache")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.explicit_memory_cache"] = _impl
        setattr(_package, "explicit_memory_cache", _impl)
