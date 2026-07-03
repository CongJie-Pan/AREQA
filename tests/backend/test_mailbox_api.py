import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import app but clear startup/shutdown events to prevent hanging on DB
from backend.main import app
app.router.on_startup.clear()
app.router.on_shutdown.clear()

client = TestClient(app)

@pytest.fixture
def mock_store():
    with patch("backend.main.get_mailbox_store") as mock_get_store:
        mock_instance = MagicMock()
        mock_get_store.return_value = mock_instance
        yield mock_instance

def test_get_mailbox_empty(mock_store):
    mock_store.get_all_mails.return_value = []
    mock_store.get_unread_count.return_value = 0
    
    response = client.get("/api/v1/mailbox")
    assert response.status_code == 200
    assert response.json() == {"mails": [], "unread_count": 0}

def test_get_mailbox_with_mails(mock_store):
    mock_store.get_all_mails.return_value = [{"mail_id": "1", "sender": "AREQA"}]
    mock_store.get_unread_count.return_value = 1
    
    response = client.get("/api/v1/mailbox")
    assert response.status_code == 200
    assert response.json() == {"mails": [{"mail_id": "1", "sender": "AREQA"}], "unread_count": 1}
    
@patch("backend.main.asyncio.create_task")
def test_post_send_reply_creates_user_mail(mock_create_task, mock_store):
    mock_store.add_mail.return_value = "mock-uuid-123"
    
    response = client.post("/api/v1/mailbox/send", json={"content": "這是我的回信", "recipient": "柏拉圖", "conversation_id": "thread-1"})
    assert response.status_code == 200
    assert response.json() == {"status": "success", "mail_id": "mock-uuid-123"}
    
    mock_store.add_mail.assert_called_once_with(
        sender="User", 
        content="這是我的回信", 
        recipient="柏拉圖",
        conversation_id="thread-1"
    )

@patch("backend.main.asyncio.create_task")
def test_post_send_reply_triggers_background_task(mock_create_task, mock_store):
    mock_store.add_mail.return_value = "mock-uuid-123"
    
    response = client.post("/api/v1/mailbox/send", json={"content": "測試信件", "recipient": "房龍"})
    assert response.status_code == 200
    
    mock_create_task.assert_called_once()
    
def test_post_send_reply_validation():
    # Missing content
    response = client.post("/api/v1/mailbox/send", json={"recipient": "柏拉圖"})
    assert response.status_code == 422

def test_post_read_marks_correct_mail(mock_store):
    mock_store.mark_as_read.return_value = True
    
    response = client.post("/api/v1/mailbox/read/mock-uuid-123")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    
    mock_store.mark_as_read.assert_called_once_with("mock-uuid-123")

def test_post_read_not_found(mock_store):
    mock_store.mark_as_read.return_value = False
    
    response = client.post("/api/v1/mailbox/read/invalid-uuid")
    assert response.status_code == 404
    assert response.json()["detail"] == "Mail not found"

def test_get_suggestions_returns_404():
    response = client.get("/api/v1/suggestions")
    assert response.status_code == 404
