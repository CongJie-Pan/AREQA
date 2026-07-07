import pytest
import sys
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from mailbox_store import MailboxStore

@pytest.mark.asyncio
async def test_schedule_delayed_mail():
    mock_redis = AsyncMock()
    
    with patch("mailbox_store.get_redis", return_value=mock_redis):
        store = MailboxStore()
        mail_data = {"subject": "Test"}
        
        # Schedule mail
        await store.schedule_delayed_mail("user_A", mail_data, delay_seconds=300)
        
        # Assert ZADD was called correctly
        assert mock_redis.zadd.called
        args, _ = mock_redis.zadd.call_args
        assert args[0] == "areqa:delayed_mail:user_A"
        
        mapping = args[1]
        # Check mapping content and score
        for k, v in mapping.items():
            assert json.loads(k) == mail_data
            assert v > time.time() + 290
