"""
Observer module for GUM - General User Models.

This module provides observer classes for different types of user interactions.
"""

from .observer import Observer

__all__ = ["Observer", "Screen", "Calendar"]

def __getattr__(name):
    if name == "Screen":
        from .screen import Screen
        return Screen
    if name == "Calendar":
        from .calendar import Calendar
        return Calendar
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
