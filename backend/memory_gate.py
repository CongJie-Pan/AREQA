"""Compatibility import for ``services.memory.gate``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.gate")
sys.modules['memory_gate'] = _impl
sys.modules['backend.memory_gate'] = _impl
