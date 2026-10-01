"""Compatibility import for ``services.orchestration.service``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.orchestration.service")
sys.modules['services.orchestration_service'] = _impl
sys.modules['backend.services.orchestration_service'] = _impl
