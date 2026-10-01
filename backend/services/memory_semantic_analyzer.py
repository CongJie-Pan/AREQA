"""Compatibility import for ``services.memory.semantic_analysis``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.semantic_analysis")
sys.modules['services.memory_semantic_analyzer'] = _impl
sys.modules['backend.services.memory_semantic_analyzer'] = _impl
