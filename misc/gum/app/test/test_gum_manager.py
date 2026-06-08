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
async def test_mock_observer_creation():
    """Test that MockObserver can be instantiated and generates Updates."""
    observer = gum_manager.MockObserver(interval=0.1)
    
    # Wait briefly for it to generate at least one update
    await asyncio.sleep(0.3)
    
    # Check if there's something in the queue
    assert not observer.update_queue.empty(), "MockObserver should have generated updates."
    
    update = await observer.update_queue.get()
    assert isinstance(update, Update)
    assert update.content_type == "input_text"
    assert "User is" in update.content
    
    # Stop the observer
    await observer.stop()

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
    
    # Check if mock observer is assigned
    assert instance.observers[0] is gum_manager.mock_observer
    assert gum_manager.mock_observer is not None

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
    assert gum_manager.mock_observer is None
    assert gum_manager.gum_instance is None
