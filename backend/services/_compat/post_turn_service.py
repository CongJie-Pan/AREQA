"""Compatibility alias for ``services.orchestration.post_turn``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.orchestration.post_turn")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.post_turn_service"] = _impl
        setattr(_package, "post_turn_service", _impl)
