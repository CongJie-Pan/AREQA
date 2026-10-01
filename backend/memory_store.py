"""Compatibility import for ``services.memory.store.service``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.store.service")
sys.modules['memory_store'] = _impl
sys.modules['backend.memory_store'] = _impl
