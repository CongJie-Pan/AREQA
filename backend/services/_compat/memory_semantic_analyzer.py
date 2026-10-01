"""Compatibility alias for ``services.memory.semantic_analysis``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.memory.semantic_analysis")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.memory_semantic_analyzer"] = _impl
        setattr(_package, "memory_semantic_analyzer", _impl)
