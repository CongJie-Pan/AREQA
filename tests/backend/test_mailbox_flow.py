import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from backend.services.compeer_scheduler import proactive_scheduler_loop
from backend.memory_store import MemoryStore

@pytest.fixture
def mock_store(tmp_path):
    store = MemoryStore(str(tmp_path / "hot.json"), str(tmp_path / "profile.json"))
    with patch("memory_store.get_global_store", return_value=store):
        yield store

@pytest.mark.asyncio
async def test_mailbox_flow(mock_store):
    # Setup initial state
    hot = mock_store.get_hot_memory()
    hot["active_avatar"] = "柏拉圖"
    hot["avatar_summon_pending"] = True
    mock_store._atomic_write(mock_store.hot_memory_path, hot)
    
    mock_mb_store = MagicMock()
    
    with patch("services.compeer_scheduler.asyncio.sleep", side_effect=asyncio.CancelledError) as mock_sleep, \
         patch("gum_integration.generate_epistolary_letter_via_llm", new_callable=AsyncMock) as mock_gen_letter, \
         patch("gum_integration.query_cold_memory_for_context", new_callable=AsyncMock) as mock_query, \
         patch("mailbox_store.get_mailbox_store", return_value=mock_mb_store), \
         patch("services.connection_manager.ws_manager.broadcast_mail_alert", new_callable=AsyncMock) as mock_broadcast:
        
        mock_gen_letter.return_value = "這是一封來自柏拉圖的信"
        
        try:
            await proactive_scheduler_loop()
        except asyncio.CancelledError:
            pass
            
        # 1. Check if generate_epistolary_letter_via_llm was called
        mock_gen_letter.assert_called_once()
        args, _ = mock_gen_letter.call_args
        assert args[0] == "柏拉圖"
        
        # 2. Check if mail was written
        mock_mb_store.add_mail.assert_called_once_with(sender="柏拉圖", content="這是一封來自柏拉圖的信", recipient="User")
        
        # 3. Check if broadcast was sent
        mock_broadcast.assert_called_once_with("柏拉圖")
        
        # 4. Check if avatar_summon_pending was cleared
        hot_mem = mock_store.get_hot_memory()
        assert "avatar_summon_pending" not in hot_mem
        assert hot_mem["active_avatar"] == "柏拉圖"
