from pathlib import Path

from pelican_mvp.agents import DiagnosisAgent
from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import AgentRole


def test_diagnosis_agent_selects_next_skill_locked_question(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")
    engine.respond("想理解原理")
    engine.respond("完全沒有基礎")
    agent = DiagnosisAgent(engine.llm)

    proposal = agent.propose_next_diagnostic(engine.state, engine.curriculum)

    assert proposal.result.role is AgentRole.DIAGNOSIS_AGENT
    assert proposal.node_id == "math_intuition"
    assert proposal.question is not None
    assert proposal.question.source == "skill"
    assert proposal.result.display_summary == "skill:math_intuition"
