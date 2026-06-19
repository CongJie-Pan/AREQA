import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root, src/main/python, and backend to sys.path so modules can be found
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src' / 'main' / 'python'))
sys.path.insert(0, str(project_root / 'backend'))

# We remove the global patching here so that unit tests can test the actual classes.
# Integration tests should patch these individually as needed.

# No global patches here.
