import pytest
from unittest.mock import AsyncMock, patch
import pickle
from services.cache_service import RagCacheService

@pytest.fixture
def mock_redis():
    with patch('services.cache_service.aioredis.from_url') as mock_from_url:
        mock_redis_instance = AsyncMock()
        mock_from_url.return_value = mock_redis_instance
        yield mock_redis_instance

@pytest.fixture
def cache_service(mock_redis):
    service = RagCacheService("redis://mock_url:6379")
    service.redis = mock_redis
    return service

@pytest.mark.asyncio
async def test_cache_set(cache_service, mock_redis):
    fingerprint = "test_fp_123"
    result_obj = {"key": "value", "list": [1, 2, 3]}
    
    await cache_service.set(fingerprint, result_obj)
    
    # Verify setex was called with correct TTL and serialized data
    mock_redis.setex.assert_called_once_with(
        f"rag:{fingerprint}",
        cache_service.TTL,
        pickle.dumps(result_obj)
    )

@pytest.mark.asyncio
async def test_cache_get_miss(cache_service, mock_redis):
    fingerprint = "test_fp_miss"
    
    # Simulate cache miss
    mock_redis.get.return_value = None
    
    result = await cache_service.get(fingerprint)
    
    assert result is None
    mock_redis.get.assert_called_once_with(f"rag:{fingerprint}")

@pytest.mark.asyncio
async def test_cache_get_hit(cache_service, mock_redis):
    fingerprint = "test_fp_hit"
    result_obj = {"found": True, "score": 0.99}
    
    # Simulate cache hit with pickled data
    mock_redis.get.return_value = pickle.dumps(result_obj)
    
    result = await cache_service.get(fingerprint)
    
    assert result == result_obj
    mock_redis.get.assert_called_once_with(f"rag:{fingerprint}")

@pytest.mark.asyncio
async def test_cache_get_error_handling(cache_service, mock_redis):
    fingerprint = "test_fp_error"
    
    # Simulate connection error
    mock_redis.get.side_effect = Exception("Connection lost")
    
    # Should not raise exception, but return None
    result = await cache_service.get(fingerprint)
    
    assert result is None
