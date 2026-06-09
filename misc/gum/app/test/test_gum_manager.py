import pytest
import asyncio
import os
import sys

# Append paths to make modules importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backEnd")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from core import gum_manager
from gum.schemas import Update



@pytest.mark.asyncio
async def test_init_gum():
    """Test initializing GUM instance."""
    # Note: we use mock or patch if db connection fails without valid creds,
    # but GUM uses sqlite by default which should work locally.
    instance = await gum_manager.init_gum(
        user_name="test_user",
        model_name="gpt-4o-mini",
        api_key="fake-api-key"
    )
    assert instance is not None
    assert instance.user_name == "test_user"
    assert instance.model == "gpt-4o-mini"

@pytest.mark.asyncio
async def test_start_stop_recording():
    """Test start and stop recording loops."""
    # Ensure it's not running
    await gum_manager.stop_recording()
    assert gum_manager.recording_task is None
    
    gum_manager.start_recording(
        user_name="test_user",
        model_name="gpt-4o-mini",
        api_key="fake-api-key"
    )
    assert gum_manager.recording_task is not None
    assert not gum_manager.recording_task.done()
    
    # Give it a moment to initialize
    await asyncio.sleep(0.1)
    
    await gum_manager.stop_recording()
    assert gum_manager.recording_task is None
    assert gum_manager.gum_instance is None
