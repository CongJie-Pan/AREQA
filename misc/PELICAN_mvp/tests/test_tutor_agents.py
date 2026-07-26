from pathlib import Path
from dataclasses import replace

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


class QuestionOnlyUnknownTutorLlm:
    available = True

    def tutor_proposal(self, **kwargs) -> BoundedTutorProposal:
        return BoundedTutorProposal(
            response="你認為這個概念還可以從哪個角度繼續拆解？",
            pedagogical_move="scaffold",
            summary="Invalid question-only inability response.",
            node_id=kwargs["node_id"],
            strategy=kwargs["strategy"].value,
            evidence_signal=kwargs["evidence_signal"],
            source="llm",
        )


class HumanitiesPartialWithoutAckLlm:
    available = True

    def tutor_proposal(self, **kwargs) -> BoundedTutorProposal:
        return BoundedTutorProposal(
            response=(
                "明治維新的背景脈絡是日本推動中央集權與社會改革，"
                "所以請用自己的話再說一次。"
            ),
            pedagogical_move="mini_lesson_with_verification",
            summary="Missing acknowledgement of partial evidence.",
            node_id=kwargs["node_id"],
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
        strategy=TutoringStrategy.EXPLANATION,
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
    assert "slow_simulation" in response.result.display_summary
    assert "candidates=" in response.result.display_summary
    assert "selected=" in response.result.display_summary


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


def test_question_only_unknown_tutor_proposal_falls_back_to_explanation(tmp_path: Path) -> None:
    engine = prepared_engine(tmp_path)
    engine.state.mode = "llm"
    agent = FastTutorAgent(QuestionOnlyUnknownTutorLlm())

    response = agent.propose_response(
        state=engine.state,
        curriculum=engine.curriculum,
        strategy=TutoringStrategy.EXPLANATION,
        node_id="math_intuition",
        base_prompt=engine.state.current_prompt,
        evidence_signal="unknown",
        base_message="沒關係，我先直接講「數學直覺」。\n\n重點是：先理解誤差代表猜測偏差。",
    )

    assert response.validation_status is ProposalValidationStatus.FALLBACK_USED
    assert response.result.reason_code == "question_only_inability_response"
    assert "重點是" in response.proposal.response


def test_humanities_partial_correct_without_acknowledgement_falls_back(tmp_path: Path) -> None:
    engine = prepared_engine(tmp_path)
    engine.state.mode = "llm"
    engine.state.intake_profile = replace(engine.state.intake_profile, domain_category="humanities")
    engine.state.learning_plan = replace(engine.state.learning_plan, domain_category="humanities")
    agent = FastTutorAgent(HumanitiesPartialWithoutAckLlm())

    response = agent.propose_response(
        state=engine.state,
        curriculum=engine.curriculum,
        strategy=TutoringStrategy.CORRECTION,
        node_id="math_intuition",
        base_prompt=engine.state.current_prompt,
        evidence_signal="partial_correct",
        learner_answer="簡單來說，是改革與西化。",
        base_message="你說到改革與西化是對的，我再補一點。\n\n好，接下來，你可以用自己的話說一次嗎？",
    )

    assert response.validation_status is ProposalValidationStatus.FALLBACK_USED
    assert response.result.reason_code == "missing_partial_acknowledgement"
    assert "你說到改革與西化是對的" in response.proposal.response
