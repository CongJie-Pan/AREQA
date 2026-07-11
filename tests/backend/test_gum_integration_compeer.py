import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.gum_integration import (
    detect_proactive_event_via_llm,
    generate_areqa_care_letter_via_llm,
    generate_scaffolding_message_via_llm,
    run_reflection
)
import backend.gum_integration as gi

@pytest.fixture(autouse=True)
def mock_gum_instance():
    mock_instance = MagicMock()
    mock_instance.client.chat.completions.create = AsyncMock()
    mock_instance.model = "test-model"
    with patch.object(gi, "gum_instance", mock_instance, create=True), \
         patch("backend.gum_integration.get_gum_instance", new_callable=AsyncMock) as mock_get_gum:
        mock_get_gum.return_value = (mock_instance, AsyncMock())
        yield mock_instance

@pytest.mark.asyncio
async def test_detect_event_returns_no_event_for_normal_browsing(mock_gum_instance):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"has_event": false, "event_summary": "", "importance": 0.0}'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response
    
    result = await detect_proactive_event_via_llm("test_user", "Snapshot data")
    assert result["has_event"] is False
    assert result["importance"] == 0.0

@pytest.mark.asyncio
async def test_detect_event_returns_event_for_frustrated_user(mock_gum_instance):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"has_event": true, "event_summary": "User stuck on poem", "importance": 0.8}'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response
    
    result = await detect_proactive_event_via_llm("test_user", "Snapshot data")
    assert result["has_event"] is True
    assert result["importance"] == 0.8
    assert result["event_summary"] == "User stuck on poem"

@pytest.mark.asyncio
async def test_detect_event_handles_llm_timeout_gracefully(mock_gum_instance):
    mock_gum_instance.client.chat.completions.create.side_effect = Exception("Timeout")
    
    result = await detect_proactive_event_via_llm("test_user", "Snapshot data")
    assert result["has_event"] is False
    assert result["importance"] == 0.0

@pytest.mark.asyncio
async def test_generate_scaffolding_returns_string(mock_gum_instance):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='這是一條測試訊息'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response
    
    result = await generate_scaffolding_message_via_llm(
        user_id="test_user",
        hot_memory_snapshot="hot",
        cold_memory_context="cold",
        learner_state="NORMAL",
        edf_policy="STRICT"
    )
    assert result == "這是一條測試訊息"

@pytest.mark.asyncio
async def test_care_letter_prompt_blocks_specific_topics_without_evidence(mock_gum_instance):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"subject":"給你的學習小箋","content":"我注意到你最近可能停留了一會兒。你願意回信告訴我，剛剛是哪個地方讓你卡住嗎？"}'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response

    subject, content = await generate_areqa_care_letter_via_llm(
        user_id="test_user",
        hot_memory_snapshot="【工作記憶 (Working Memory)】\n- Current focus: README.md 更新",
        cold_memory_context="【檢索到的長尾記憶 (Cold Memory)】\n- 學生昨天文言文卡很久，但願意反覆重讀。",
        learner_state="STARTING",
        edf_policy="default",
        event_summary="EDF 系統偵測到使用者遭遇學習瓶頸 (狀態: STARTING)",
        allow_topic_specific=False,
    )

    prompt = mock_gum_instance.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "系統沒有足夠的近期語意證據" in prompt
    assert "尤其禁止自行輸出「文言文」、「判詞」、「紅樓夢」" in prompt
    assert "學生昨天文言文卡很久" not in prompt
    assert subject == "給你的學習小箋"
    assert "文言文" not in content
    assert "判詞" not in content

@pytest.mark.asyncio
async def test_care_letter_prompt_allows_specific_topics_with_evidence(mock_gum_instance):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"subject":"README 小箋","content":"我注意到你正在整理 README。你願意回信說說目前最難判斷的是架構描述還是啟動流程嗎？"}'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response

    await generate_areqa_care_letter_via_llm(
        user_id="test_user",
        hot_memory_snapshot="【工作記憶 (Working Memory)】\n- Current focus: README.md 更新",
        cold_memory_context="Mocked cold context",
        learner_state="STARTING",
        edf_policy="default",
        event_summary="使用者正在整理 README.md 的架構描述",
        allow_topic_specific=True,
    )

    prompt = mock_gum_instance.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "系統已確認有足夠的近期語意證據" in prompt
    assert "Mocked cold context" in prompt

@pytest.mark.asyncio
async def test_run_reflection_returns_insights_list(mock_gum_instance):
    # Mock recent observations
    obs1 = MagicMock(id="1", content="Obs 1")
    obs2 = MagicMock(id="2", content="Obs 2")
    mock_gum_instance.recent_observations = AsyncMock(return_value=[obs1, obs2])
    mock_gum_instance.update_observation_status = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"insights": ["Insight 1", "Insight 2"]}'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response
    
    with patch("memory_store.get_global_store", return_value=None):
        insights = await run_reflection(user_id="test_user")
    
    assert len(insights) == 2
    assert insights[0] == "Insight 1"
    assert mock_gum_instance.update_observation_status.call_count == 2
