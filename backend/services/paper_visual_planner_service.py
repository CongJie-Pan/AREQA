"""Compatibility import for ``services.paper_visual.planner``; implementation and state live there."""

import sys
from importlib import import_module

_impl = import_module("services.paper_visual.planner")
sys.modules['services.paper_visual_planner_service'] = _impl
sys.modules['backend.services.paper_visual_planner_service'] = _impl
