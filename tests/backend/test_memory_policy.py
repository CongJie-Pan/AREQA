import pytest

from backend.policies import MemoryPolicy, MemoryScope


@pytest.mark.parametrize("query", ["你好", "嗨", "謝謝"])
def test_low_information_messages_cannot_query_long_term_memory(query):
    decision = MemoryPolicy().evaluate(query)
    assert decision.scope == MemoryScope.DENY_MEMORY
    assert decision.allow_long_term_query is False


@pytest.mark.parametrize(
    "query",
    [
        "血壓 118/77 正常嗎？",
        "我最近的家庭壓力很大怎麼辦？",
    ],
)
def test_sensitive_query_requires_explicit_recall_consent(query):
    decision = MemoryPolicy().evaluate(query)
    assert decision.scope == MemoryScope.DENY_MEMORY
    assert decision.reason_code == "SENSITIVE_WITHOUT_CONSENT"


def test_explicit_cross_conversation_recall_is_allowed():
    decision = MemoryPolicy().evaluate("請結合昨天家庭壓力的情況回答")
    assert decision.scope == MemoryScope.ALLOW_EXPLICIT_RECALL
    assert decision.allow_long_term_query is True


def test_substantive_non_sensitive_query_allows_agent_query():
    decision = MemoryPolicy().evaluate("請解釋 React dependency array")
    assert decision.scope == MemoryScope.ALLOW_AGENT_QUERY
    assert decision.allow_long_term_query is True


@pytest.mark.parametrize(
    "query",
    [
        "你還記得我喜歡用什麼方式整理重點嗎？",
        "記不記得我喜歡哪種整理方式？",
        "我喜歡的整理方式，還記得嗎？",
    ],
)
def test_asking_whether_assistant_remembers_is_explicit_recall(query):
    decision = MemoryPolicy().evaluate(query)
    assert decision.scope == MemoryScope.ALLOW_EXPLICIT_RECALL
    assert decision.allow_long_term_query is True


def test_remember_instruction_is_not_treated_as_recall():
    decision = MemoryPolicy().evaluate("請你記得我喜歡用表格整理重點")
    assert decision.scope != MemoryScope.ALLOW_EXPLICIT_RECALL


def test_user_own_reminiscence_does_not_unlock_sensitive_memory():
    decision = MemoryPolicy().evaluate("我還記得我最近的家庭壓力很大")
    assert decision.scope == MemoryScope.DENY_MEMORY
    assert decision.reason_code == "SENSITIVE_WITHOUT_CONSENT"
