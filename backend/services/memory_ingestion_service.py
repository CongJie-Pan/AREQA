"""Compatibility import for ``services.memory.ingestion.service``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.memory.ingestion.service")
sys.modules['services.memory_ingestion_service'] = _impl
sys.modules['backend.services.memory_ingestion_service'] = _impl
