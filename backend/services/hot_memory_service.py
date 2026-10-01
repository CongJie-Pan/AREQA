"""Compatibility import for ``services.memory.hot``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.hot")
sys.modules['services.hot_memory_service'] = _impl
sys.modules['backend.services.hot_memory_service'] = _impl
