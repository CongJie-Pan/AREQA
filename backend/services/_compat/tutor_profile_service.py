"""Compatibility alias for ``services.conversation.tutor_profile``; do not add implementation here."""

import sys
from importlib import import_module

_impl = import_module("services.conversation.tutor_profile")
sys.modules[__name__] = _impl
for _package_name in ("services", "backend.services"):
    if _package := sys.modules.get(_package_name):
        sys.modules[f"{_package_name}.tutor_profile_service"] = _impl
        setattr(_package, "tutor_profile_service", _impl)
