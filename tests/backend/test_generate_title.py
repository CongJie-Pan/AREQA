import pytest
from httpx import AsyncClient, ASGITransport
import json
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Import the FastAPI app
from backend.main import app

@pytest.mark.asyncio
async def test_generate_title_missing_api_key():
    # 模擬 OPENROUTER_API_KEY 遺失
    with patch('backend.main.os.environ.get', return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            req_data = {
                "messages": [{"role": "user", "content": "你好"}]
            }
            response = await ac.post("/api/v1/generate-title", json=req_data)
            
            assert response.status_code == 200
            content = response.text
            
            assert "data: [ERROR] OPENROUTER_API_KEY missing" in content
            assert "data: [DONE]" in content

@pytest.mark.asyncio
async def test_generate_title_success():
    # 模擬 OPENROUTER_API_KEY 存在
    with patch('backend.main.os.environ.get', return_value="mock-key"):
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            
            async def fake_create(*args, **kwargs):
                class FakeAsyncIterator:
                    def __init__(self):
                        self.yielded = False
                    def __aiter__(self):
                        return self
                    async def __anext__(self):
                        if not self.yielded:
                            self.yielded = True
                            chunk = MagicMock()
                            chunk.choices = [MagicMock()]
                            chunk.choices[0].delta.content = "測試標題"
                            return chunk
                        raise StopAsyncIteration
                return FakeAsyncIterator()
            
            mock_client.chat.completions.create = MagicMock(side_effect=fake_create)
            mock_openai.return_value = mock_client
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！"}]
                }
                response = await ac.post("/api/v1/generate-title", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                # Check for the expected SSE JSON format
                expected_data = json.dumps({"content": "測試標題"}, ensure_ascii=False)
                assert f"data: {expected_data}" in content
                assert "data: [DONE]" in content

@pytest.mark.asyncio
async def test_generate_title_api_error():
    # 模擬 OPENROUTER_API_KEY 存在，但 API 呼叫異常
    with patch('backend.main.os.environ.get', return_value="mock-key"):
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            
            async def fake_create_error(*args, **kwargs):
                raise Exception("OpenRouter API Error")
            
            # 模擬發生異常
            mock_client.chat.completions.create = MagicMock(side_effect=fake_create_error)
            mock_openai.return_value = mock_client
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "你好"}]
                }
                response = await ac.post("/api/v1/generate-title", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                expected_error = json.dumps({"error": "OpenRouter API Error"}, ensure_ascii=False)
                assert f"data: {expected_error}" in content
                assert "data: [DONE]" in content
