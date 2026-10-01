"""Compatibility alias for ``services.paper_visual.planner``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.paper_visual.planner")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.paper_visual_planner_service"] = _impl
        setattr(_package, "paper_visual_planner_service", _impl)
