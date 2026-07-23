from pathlib import Path

from pelican_mvp.agents import FastTutorAgent, SlowSimulatorAgent
from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import AgentRole, BoundedTutorProposal, ProposalValidationStatus, TutoringStrategy


class OffNodeTutorLlm:
    available = True

    def tutor_proposal(self, **kwargs) -> BoundedTutorProposal:
        return BoundedTutorProposal(
            response="This response is structurally bounded but points to the wrong node.",
            pedagogical_move="scaffold",
            summary="Invalid off-node test proposal.",
            node_id="wrong_node",
            strategy=kwargs["strategy"].value,
            evidence_signal=kwargs["evidence_signal"],
            source="llm",
        )


def prepared_engine(tmp_path: Path) -> PelicanEngine:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")
    engine.respond("想理解原理")
    engine.respond("完全沒有基礎")
    return engine


def test_fast_tutor_agent_returns_bounded_rule_scaffold(tmp_path: Path) -> None:
    engine = prepared_engine(tmp_path)
    agent = FastTutorAgent(engine.llm)

    response = agent.propose_response(
        state=engine.state,
        curriculum=engine.curriculum,
        strategy=TutoringStrategy.DECOMPOSITION,
        node_id="math_intuition",
        base_prompt=engine.state.current_prompt,
        evidence_signal="unknown",
    )

    assert response.result.role is AgentRole.FAST_TUTOR_AGENT
    assert response.validation_status is ProposalValidationStatus.FALLBACK_USED
    assert response.proposal.pedagogical_move == "scaffold"
    assert "raw" not in response.result.to_safe_metadata()["display_summary"]


def test_slow_simulator_agent_marks_slow_route_metadata(tmp_path: Path) -> None:
    engine = prepared_engine(tmp_path)
    agent = SlowSimulatorAgent(engine.llm)

    response = agent.propose_response(
        state=engine.state,
        curriculum=engine.curriculum,
        strategy=TutoringStrategy.DECOMPOSITION,
        node_id="math_intuition",
        base_prompt=engine.state.current_prompt,
        evidence_signal="unknown",
    )

    assert response.result.role is AgentRole.SLOW_SIMULATOR_AGENT
    assert response.proposal.pedagogical_move == "slow_scaffold"
    assert response.result.reason_code == "rule_mode_baseline"


def test_invalid_llm_tutor_proposal_falls_back_safely(tmp_path: Path) -> None:
    engine = prepared_engine(tmp_path)
    engine.state.mode = "llm"
    agent = FastTutorAgent(OffNodeTutorLlm())

    response = agent.propose_response(
        state=engine.state,
        curriculum=engine.curriculum,
        strategy=TutoringStrategy.DECOMPOSITION,
        node_id="math_intuition",
        base_prompt=engine.state.current_prompt,
        evidence_signal="unknown",
    )

    assert response.validation_status is ProposalValidationStatus.FALLBACK_USED
    assert response.result.reason_code == "off_node_tutor_proposal"
    assert response.proposal.source == "rule"
