import pytest
import os
import json
from unittest.mock import patch
from backend.mailbox_store import MailboxStore

class FakeRedis:
    def __init__(self):
        self.store = {}
        
    async def get(self, key):
        return self.store.get(key)
        
    async def set(self, key, value):
        self.store[key] = value

@pytest.fixture
def temp_store():
    fake_redis = FakeRedis()
    with patch("backend.mailbox_store.get_redis", return_value=fake_redis):
        store = MailboxStore()
        yield store

@pytest.mark.asyncio
async def test_add_mail(temp_store):
    store = temp_store
    mail_id = await store.add_mail("user1", "柏拉圖", "你好，這是第一封信", "", "User", "conv-123")
    
    mails = await store.get_all_mails("user1")
    assert len(mails) == 1
    assert mails[0]["mail_id"] == mail_id
    assert mails[0]["sender"] == "柏拉圖"
    assert mails[0]["content"] == "你好，這是第一封信"
    assert mails[0]["is_read"] is False
    assert mails[0]["conversation_id"] == "conv-123"

@pytest.mark.asyncio
async def test_mark_as_read(temp_store):
    store = temp_store
    mail_id = await store.add_mail("user1", "柏拉圖", "你好，這是第一封信", "", "User")
    
    # mark as read
    success = await store.mark_as_read("user1", mail_id)
    assert success is True
    
    mails = await store.get_all_mails("user1")
    assert mails[0]["is_read"] is True

@pytest.mark.asyncio
async def test_get_unread_count(temp_store):
    store = temp_store
    m1 = await store.add_mail("user1", "A", "content1", "")
    m2 = await store.add_mail("user1", "B", "content2", "")
    m3 = await store.add_mail("user1", "C", "content3", "")
    
    assert await store.get_unread_count("user1") == 3
    
    await store.mark_as_read("user1", m1)
    assert await store.get_unread_count("user1") == 2

@pytest.mark.asyncio
async def test_conversation_thread(temp_store):
    store = temp_store
    await store.add_mail("user1", "A", "content1", "", "User", "conv-1")
    await store.add_mail("user1", "B", "content2", "", "User", "conv-2")
    await store.add_mail("user1", "A", "content3", "", "User", "conv-1")
    
    mails = await store.get_all_mails("user1")
    conv1_mails = [m for m in mails if m.get("conversation_id") == "conv-1"]
    assert len(conv1_mails) == 2
