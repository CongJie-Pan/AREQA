"""Compatibility alias for ``services.orchestration.turn_plan``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.orchestration.turn_plan")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.turn_plan_service"] = _impl
        setattr(_package, "turn_plan_service", _impl)
