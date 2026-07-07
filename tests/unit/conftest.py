import sys
from unittest.mock import MagicMock

sys.modules['jose'] = MagicMock()
sys.modules['asyncpg'] = MagicMock()
sys.modules['pgvector'] = MagicMock()

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
