"""Compatibility alias for ``services.memory.extraction``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.memory.extraction")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.memory_extraction_agent"] = _impl
        setattr(_package, "memory_extraction_agent", _impl)
