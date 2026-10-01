"""Compatibility alias for ``services.pdf_visual.extraction``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.pdf_visual.extraction")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.pdf_visual_extraction_service"] = _impl
        setattr(_package, "pdf_visual_extraction_service", _impl)
