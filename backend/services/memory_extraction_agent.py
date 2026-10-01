"""Compatibility import for ``services.memory.extraction``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.extraction")
sys.modules['services.memory_extraction_agent'] = _impl
sys.modules['backend.services.memory_extraction_agent'] = _impl
