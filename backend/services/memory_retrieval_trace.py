"""Compatibility import for ``services.memory.retrieval_trace``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.retrieval_trace")
sys.modules['services.memory_retrieval_trace'] = _impl
sys.modules['backend.services.memory_retrieval_trace'] = _impl
