import pytest
import os
import json
from unittest.mock import patch
from backend.mailbox_store import MailboxStore

@pytest.fixture
def temp_store(tmp_path):
    store_dir = tmp_path / "data"
    store = MailboxStore(data_dir=str(store_dir))
    return store, store_dir

def test_add_mail(temp_store):
    store, _ = temp_store
    mail_id = store.add_mail("柏拉圖", "你好，這是第一封信", "User", "conv-123")
    
    mails = store.get_all_mails()
    assert len(mails) == 1
    assert mails[0]["mail_id"] == mail_id
    assert mails[0]["sender"] == "柏拉圖"
    assert mails[0]["content"] == "你好，這是第一封信"
    assert mails[0]["is_read"] is False
    assert mails[0]["conversation_id"] == "conv-123"

def test_mark_as_read(temp_store):
    store, _ = temp_store
    mail_id = store.add_mail("柏拉圖", "你好，這是第一封信", "User")
    
    # mark as read
    success = store.mark_as_read(mail_id)
    assert success is True
    
    mails = store.get_all_mails()
    assert mails[0]["is_read"] is True

def test_get_unread_count(temp_store):
    store, _ = temp_store
    m1 = store.add_mail("A", "content1")
    m2 = store.add_mail("B", "content2")
    m3 = store.add_mail("C", "content3")
    
    assert store.get_unread_count() == 3
    
    store.mark_as_read(m1)
    assert store.get_unread_count() == 2
    
def test_atomic_write_integrity(temp_store):
    store, store_dir = temp_store
    store.add_mail("A", "content1")
    
    # Mock os.replace to simulate a crash during atomic write
    original_replace = os.replace
    
    def failing_replace(src, dst):
        raise Exception("Simulated crash")
        
    with patch("os.replace", side_effect=failing_replace):
        with pytest.raises(Exception):
            store.add_mail("B", "content2")
            
    # the original file should be intact with only the first mail
    mails = store.get_all_mails()
    assert len(mails) == 1
    assert mails[0]["sender"] == "A"
    
def test_conversation_thread(temp_store):
    store, _ = temp_store
    store.add_mail("A", "content1", "User", "conv-1")
    store.add_mail("B", "content2", "User", "conv-2")
    store.add_mail("A", "content3", "User", "conv-1")
    
    mails = store.get_all_mails()
    conv1_mails = [m for m in mails if m.get("conversation_id") == "conv-1"]
    assert len(conv1_mails) == 2
