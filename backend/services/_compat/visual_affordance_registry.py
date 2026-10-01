"""Compatibility alias for ``services.visual.affordance``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.visual.affordance")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.visual_affordance_registry"] = _impl
        setattr(_package, "visual_affordance_registry", _impl)
