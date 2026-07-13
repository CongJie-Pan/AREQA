import pytest

from backend.memory_gate import (
    apply_action_gate,
    apply_reflection_gate,
    apply_user_message_gate,
    classify_action,
    classify_learning_observation,
    classify_user_message,
    evaluate_memory_retention_policy,
)


class FakeStore:
    def __init__(self):
        self.profile_ops = []
        self.working_updates = []
        self.behavior_signals = []
        self.learning_observations = []
        self.cold_candidates = []
        self.working_memory = {
            "session_summary": "",
            "current_focus": "",
            "recent_learning_points": [],
            "explicit_memories": [],
            "updated_at": None,
        }

    async def perform_memory_operation(self, user_id, target, action, content, old_text="", **kwargs):
        self.profile_ops.append((user_id, target, action, content, old_text))

    async def update_working_memory(self, user_id, updates):
        self.working_updates.append((user_id, updates))
        self.working_memory.update(updates)

    async def append_behavior_signal(self, user_id, action_type, context, weight=1.0):
        self.behavior_signals.append((user_id, action_type, context, weight))

    async def append_learning_observation(
        self, user_id, text, confidence=8.0, decay=5.0, conversation_id="", source="user_message"
    ):
        self.learning_observations.append(
            (user_id, text, confidence, decay, conversation_id)
        )

    async def get_working_memory(self, user_id):
        return dict(self.working_memory)

    async def append_cold_candidate(self, user_id, text, category, source, reason, confidence=9.0, decay=3.0):
        candidate = {
            "user_id": user_id,
            "text": text,
            "category": category,
            "source": source,
            "reason": reason,
            "confidence": confidence,
            "decay": decay,
        }
        self.cold_candidates.append(candidate)
        return candidate


def test_classify_user_message_as_current_focus():
    decision = classify_user_message("今天文言文這題我卡住了")

    assert decision.category == "current_focus"
    assert decision.should_prompt is True
    assert decision.should_cold_store is False


def test_classify_low_information_greeting_does_not_enter_prompt_memory():
    decision = classify_user_message("你好")

    assert decision.category == "smalltalk"
    assert decision.should_prompt is False
    assert decision.should_cold_store is False
    assert decision.proposition == ""


def test_classify_explicit_memory_request():
    decision = classify_user_message("請你記住我昨天文言文卡很久")

    assert decision.category == "explicit_memory"
    assert decision.should_prompt is True
    assert decision.should_cold_store is True
    assert decision.proposition == "我昨天文言文卡很久"


def test_roleplay_request_is_not_explicit_memory():
    decision = classify_user_message("請你扮演夏目漱石跟我聊天")

    assert decision.category == "current_focus"
    assert decision.should_cold_store is False


def test_classify_action_as_behavior_only():
    decision = classify_action("scroll", {"duration_seconds": 3})

    assert decision.category == "behavior_signal"
    assert decision.should_prompt is False
    assert decision.should_cold_store is False
    assert decision.weight == 0.2


def test_legacy_action_observation_never_enters_prompt():
    decision = classify_learning_observation("[User Action] Type: scroll, Context: {}")

    assert decision.category == "behavior_signal"
    assert decision.should_prompt is False


@pytest.mark.asyncio
async def test_apply_user_message_gate_stores_explicit_memory():
    store = FakeStore()

    decision = await apply_user_message_gate(store, "u1", "請你記住我喜歡先看例子")

    assert decision.category == "explicit_memory"
    assert store.profile_ops == [("u1", "user", "add", "我喜歡先看例子", "")]
    assert store.cold_candidates == []
    assert store.working_updates == []


@pytest.mark.asyncio
async def test_apply_user_message_gate_updates_current_focus_only():
    store = FakeStore()

    decision = await apply_user_message_gate(store, "u1", "這段判詞是什麼意思", conversation_id="conv-a")

    assert decision.category == "current_focus"
    assert store.profile_ops == []
    assert store.working_updates == [
        ("u1", {"current_focus": "這段判詞是什麼意思", "current_focus_conversation_id": "conv-a"})
    ]


@pytest.mark.asyncio
async def test_apply_user_message_gate_does_not_store_greeting_as_current_focus():
    store = FakeStore()

    decision = await apply_user_message_gate(store, "u1", "你好", conversation_id="conv-b")

    assert decision.category == "smalltalk"
    assert store.working_updates == []


@pytest.mark.asyncio
async def test_apply_action_gate_writes_behavior_signal():
    store = FakeStore()

    decision = await apply_action_gate(store, "u1", "reread", {"section": "p1"})

    assert decision.category == "behavior_signal"
    assert store.behavior_signals == [("u1", "reread", {"section": "p1"}, 1.0)]


@pytest.mark.asyncio
async def test_apply_reflection_gate_updates_session_summary():
    store = FakeStore()

    decision = await apply_reflection_gate(store, "u1", "學生昨天文言文卡很久，但願意反覆重讀。")

    assert decision.category == "session_reflection"
    assert decision.should_cold_store is True
    assert store.learning_observations == [
        ("u1", "學生昨天文言文卡很久，但願意反覆重讀。", 9.0, 3.0, "")
    ]
    assert store.cold_candidates == []
    assert store.working_updates == [
        ("u1", {"session_summary": "學生昨天文言文卡很久，但願意反覆重讀。"})
    ]


def test_retention_policy_allows_stable_preference():
    decision = evaluate_memory_retention_policy({
        "text": "使用者偏好用具體例子理解抽象概念",
        "normalized_text": "偏好用具體例子理解抽象概念",
        "category": "preference",
        "evidence_quote": "我偏好用具體例子理解抽象概念",
    })
    assert decision.action == "allow"


def test_retention_policy_denies_negative_capability_label():
    decision = evaluate_memory_retention_policy({
        "text": "使用者在理化科目上有學習困難",
        "category": "background",
        "evidence_quote": "我之前連國中理化都一直不及格",
    })
    assert decision.action == "deny"


def test_retention_policy_adds_expiry_to_time_bound_context():
    decision = evaluate_memory_retention_policy({
        "text": "使用者下週要參加考試",
        "category": "goal",
        "evidence_quote": "我下週要考試",
    })
    assert decision.action == "allow_with_expiry"
    assert decision.expires_in_seconds is not None


def test_retention_policy_keeps_unknown_candidate_pending():
    decision = evaluate_memory_retention_policy({
        "text": "使用者具有高度自我釐清能力",
        "category": "personality",
        "evidence_quote": "我可以清楚區分兩件事",
    })
    assert decision.action == "candidate_only"
