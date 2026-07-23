from pathlib import Path

from pelican_mvp.agents import PolicyAgent
from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import AgentRole


def test_policy_agent_uses_current_state_for_strategy_proposal(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    agent = PolicyAgent(engine.edf)

    snapshot, result = agent.propose_strategy(engine.state)

    assert result.role is AgentRole.POLICY_AGENT
    assert result.reason_code == snapshot.reason_code
    assert result.display_summary.startswith(snapshot.learner_state)
