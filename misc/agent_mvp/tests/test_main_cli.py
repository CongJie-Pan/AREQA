"""Tests for CLI-local helpers."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import calculator, configure_console_encoding


def test_configure_console_encoding_is_best_effort():
    """Console encoding setup should never block CLI startup."""
    configure_console_encoding()


def test_calculator_accepts_common_division_alias():
    """The calculator should accept aliases models commonly emit."""
    assert calculator(23, 4, "div") == 5.75

