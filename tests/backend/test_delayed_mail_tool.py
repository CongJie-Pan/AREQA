from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools import DelayedMailTool


@pytest.mark.asyncio
async def test_delayed_mail_requires_explicit_letter_intent():
    store = MagicMock()
    store.schedule_delayed_mail = AsyncMock()
    tool = DelayedMailTool(lambda: store)

    with pytest.raises(PermissionError, match="explicit user intent"):
        await tool.execute({
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "user_message": "請介紹柏拉圖",
            "avatar_name": "柏拉圖",
            "task_id": "task-1",
        })
    store.schedule_delayed_mail.assert_not_awaited()


@pytest.mark.asyncio
async def test_delayed_mail_schedules_validated_idempotent_task():
    store = MagicMock()
    store.schedule_delayed_mail = AsyncMock(return_value="task-1")
    tool = DelayedMailTool(lambda: store)

    with patch("config.settings.enable_mailbox_sending", True):
        result = await tool.execute({
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "user_message": "請柏拉圖寫信給我",
            "avatar_name": "柏拉圖",
            "task_id": "task-1",
        })

    assert result.content["task_id"] == "task-1"
    payload = store.schedule_delayed_mail.await_args.kwargs["mail_data"]
    assert payload["task_id"] == "task-1"
    assert payload["active_avatar"] == "柏拉圖"


@pytest.mark.asyncio
async def test_delayed_mail_tool_is_disabled_by_default():
    store = MagicMock()
    store.schedule_delayed_mail = AsyncMock()
    tool = DelayedMailTool(lambda: store)

    result = await tool.execute({
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "user_message": "請柏拉圖寫信給我",
        "avatar_name": "柏拉圖",
        "task_id": "task-1",
    })

    assert result.status == "disabled"
    store.schedule_delayed_mail.assert_not_awaited()


@pytest.mark.asyncio
async def test_delayed_mail_rejects_unbounded_avatar_input():
    tool = DelayedMailTool(lambda: MagicMock())
    with pytest.raises(ValueError, match="avatar name"):
        await tool.execute({
            "user_id": "user-1",
            "user_message": "請寫信給我",
            "avatar_name": "x" * 100,
            "task_id": "task-1",
        })
