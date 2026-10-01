"""Compatibility import for ``services.visual_answer.service``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.visual_answer.service")
sys.modules['services.visual_answer_service'] = _impl
sys.modules['backend.services.visual_answer_service'] = _impl
