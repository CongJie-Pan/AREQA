"""Compatibility import for ``services.memory.gum.runtime``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.gum.runtime")
sys.modules['gum_integration'] = _impl
sys.modules['backend.gum_integration'] = _impl
