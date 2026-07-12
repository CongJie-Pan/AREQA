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
