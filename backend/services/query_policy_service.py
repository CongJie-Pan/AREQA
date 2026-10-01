"""Compatibility import for ``services.query_policy.classifier``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.query_policy.classifier")
sys.modules['services.query_policy_service'] = _impl
sys.modules['backend.services.query_policy_service'] = _impl
