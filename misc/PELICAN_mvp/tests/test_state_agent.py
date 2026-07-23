from pelican_mvp.agents import StateAgent
from pelican_mvp.models import AgentRole, ResponseCategory


def test_state_agent_proposes_safe_diagnostic_delta_without_raw_answer() -> None:
    agent = StateAgent()

    result = agent.propose_diagnostic_update("zhou_authority", ResponseCategory.INCORRECT)
    metadata = result.to_safe_metadata()

    assert result.role is AgentRole.STATE_AGENT
    assert metadata["artifact_type"] == "diagnostic_state_update"
    assert metadata["reason_code"] == "incorrect"
    assert "raw" not in metadata["display_summary"]
