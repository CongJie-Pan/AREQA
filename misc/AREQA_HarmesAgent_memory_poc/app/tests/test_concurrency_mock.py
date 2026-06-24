import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from app.background_review import add_to_review_queue, background_worker
import app.background_review as bg_module

@pytest.fixture
def reset_queue():
    bg_module.review_queue.clear()
    bg_module.last_added_time = 0.0
    yield
    bg_module.review_queue.clear()
    bg_module.last_added_time = 0.0

@pytest.mark.asyncio
async def test_debounce_and_concurrency(reset_queue):
    mock_memory_store = AsyncMock()
    
    call_count = 0
    processed_messages_length = 0
    
    async def mock_process_memories(messages, store):
        nonlocal call_count, processed_messages_length
        call_count += 1
        processed_messages_length = len(messages)
        # 模擬 LLM 處理需要花費時間，且驗證執行序不會發生阻塞死鎖
        await asyncio.sleep(1) 

    with patch("app.background_review.process_memories", side_effect=mock_process_memories):
        # 啟動背景 Worker
        bg_task = asyncio.create_task(background_worker(mock_memory_store))
        
        # 模擬快速連發 (Rapid Fire)
        await add_to_review_queue([{"role": "user", "content": "A"}])
        await asyncio.sleep(0.5)
        
        await add_to_review_queue([{"role": "user", "content": "B"}])
        await asyncio.sleep(0.5)
        
        await add_to_review_queue([{"role": "user", "content": "C"}])
        
        # 此時由於防抖設計 (需等待 3 秒無新訊息)，呼叫次數仍為 0
        assert call_count == 0
        
        # 等待 4 秒，讓防抖計時器過期並觸發處理
        await asyncio.sleep(4)
        
        # 驗證只有一次呼叫，且打包了所有的訊息
        assert call_count == 1
        assert processed_messages_length == 3 # A, B, C 三條訊息被 Batch
        
        # 確保清理任務
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
