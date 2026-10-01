"""Compatibility alias for ``services.realtime.speaking_material``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.realtime.speaking_material")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.speaking_material_service"] = _impl
        setattr(_package, "speaking_material_service", _impl)
