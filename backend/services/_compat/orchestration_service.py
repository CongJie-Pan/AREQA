"""Compatibility alias for ``services.orchestration.service``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.orchestration.service")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.orchestration_service"] = _impl
        setattr(_package, "orchestration_service", _impl)
