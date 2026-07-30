import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from backend.services.compeer_scheduler import proactive_scheduler_loop

@pytest.fixture
def mock_store():
    store = MagicMock()
    # Mock redis for scan
    store.redis = AsyncMock()
    store.redis.scan.return_value = (0, ["areqa:hot_memory:test_user"])
    
    # We also need to mock get_hot_memory to return our test state
    hot_memory = {
        "active_avatar": "柏拉圖",
        "avatar_summon_pending": True
    }
    
    async def get_hot_memory_mock(user_id):
        if user_id == "test_user":
            return hot_memory
        return {}
        
    store.get_hot_memory = AsyncMock(side_effect=get_hot_memory_mock)
    
    with patch("memory_store.get_global_store", return_value=store):
        yield store

@pytest.mark.asyncio
async def test_mailbox_flow(mock_store):
    mock_mb_store = MagicMock()
    mock_mb_store.schedule_delayed_mail = AsyncMock()
    
    with patch("config.settings.enable_mailbox_sending", True), \
         patch("backend.services.compeer_scheduler.asyncio.sleep", side_effect=asyncio.CancelledError) as mock_sleep, \
         patch("gum_integration.generate_epistolary_letter_via_llm", new_callable=AsyncMock) as mock_gen_letter, \
         patch("gum_integration.query_cold_memory_for_context", new_callable=AsyncMock) as mock_query, \
         patch("gum_integration.get_hot_memory_snapshot", new_callable=AsyncMock) as mock_snapshot, \
         patch("mailbox_store.get_mailbox_store", return_value=mock_mb_store):
        
        mock_gen_letter.return_value = ("標題", "這是一封來自柏拉圖的信")
        mock_query.return_value = "cold_context"
        mock_snapshot.return_value = {}
        
        try:
            await proactive_scheduler_loop()
        except asyncio.CancelledError:
            pass
            
        # 1. Check if generate_epistolary_letter_via_llm was called
        mock_gen_letter.assert_called_once()
        args, _ = mock_gen_letter.call_args
        assert args[0] == "test_user"
        assert args[1] == "柏拉圖"
        
        # 2. Check if mail was scheduled
        mock_mb_store.schedule_delayed_mail.assert_called_once()
        call_kwargs = mock_mb_store.schedule_delayed_mail.call_args.kwargs
        assert call_kwargs["user_id"] == "test_user"
        assert call_kwargs["mail_data"]["sender"] == "柏拉圖"
        assert call_kwargs["mail_data"]["content"] == "這是一封來自柏拉圖的信"
        
        # 3. Check if avatar_summon_pending was cleared
        hot_mem = await mock_store.get_hot_memory("test_user")
        assert "avatar_summon_pending" not in hot_mem
        assert hot_mem["active_avatar"] == "柏拉圖"
