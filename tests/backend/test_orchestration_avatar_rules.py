from backend.services.orchestration_service import (
    _extract_explicit_chat_avatar,
    _is_stop_roleplay_request,
)


def test_letter_request_does_not_enable_chat_avatar():
    assert _extract_explicit_chat_avatar("你可以讓夏目漱石寫封信給我嗎") is None


def test_explicit_roleplay_enables_chat_avatar():
    assert _extract_explicit_chat_avatar("請你扮演夏目漱石跟我對話") == "夏目漱石"


def test_stop_roleplay_request_is_detected():
    assert _is_stop_roleplay_request("請停止扮演，回到 AREQA")
