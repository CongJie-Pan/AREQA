"""Compatibility import for ``services.memory.recall_cache``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.recall_cache")
sys.modules['services.explicit_memory_cache'] = _impl
sys.modules['backend.services.explicit_memory_cache'] = _impl
