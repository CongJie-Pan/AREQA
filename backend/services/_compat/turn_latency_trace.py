"""Compatibility alias for ``services.orchestration.trace``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.orchestration.trace")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.turn_latency_trace"] = _impl
        setattr(_package, "turn_latency_trace", _impl)
