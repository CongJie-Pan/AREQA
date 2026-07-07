import pytest
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from gum_integration import init_gum_instance, gum_instance, stop_gum_instance

@pytest.mark.asyncio
async def test_gum_singleton():
    with patch("gum_integration.gum") as mock_gum:
        mock_instance = AsyncMock()
        mock_gum.return_value = mock_instance
        
        # Test initialization
        instance1 = await init_gum_instance()
        assert instance1 is not None
        
        # In a real singleton architecture, subsequent calls or different users 
        # should reuse the same engine. For our basic test, we just ensure 
        # the global instance was set.
        from gum_integration import gum_instance
        assert gum_instance == instance1
        
        await stop_gum_instance()
