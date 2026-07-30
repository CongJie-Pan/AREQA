from pathlib import Path
from dataclasses import replace

from pelican_mvp.agents import FastTutorAgent, SlowSimulatorAgent
from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import AgentRole, BoundedTutorProposal, ProposalValidationStatus, TranscriptEntry, TutoringStrategy


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


class SlowChoiceLlm:
    available = True

    def slow_strategy_simulation(self, **kwargs):
        return {
            "selected_strategy": "short_reframe",
            "reason_code": "lower load clarification",
            "rationale": "Use a lighter clarification before another lesson.",
        }

    def tutor_proposal(self, **kwargs) -> BoundedTutorProposal:
        return BoundedTutorProposal(
            response="Here is a short reframing of the current idea before the next check.",
            pedagogical_move="short_reframe",
            summary="Selected short reframe from candidate simulation.",
            node_id=kwargs["node_id"],
            strategy=kwargs["strategy"].value,
            evidence_signal=kwargs["evidence_signal"],
            source="llm",
        )


class RecordingTutorContextLlm:
    available = True

    def __init__(self) -> None:
        self.kwargs = {}

    def tutor_proposal(self, **kwargs) -> BoundedTutorProposal:
        self.kwargs = kwargs
        return BoundedTutorProposal(
            response="我會承接上一題，不重複同一個檢核問題。",
            pedagogical_move="contextual_follow_up",
            summary="Uses recent tutor context.",
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
    assert "load=" in response.result.display_summary
    assert "fit=" in response.result.display_summary


def test_slow_simulator_agent_accepts_valid_llm_candidate_selection(tmp_path: Path) -> None:
    engine = prepared_engine(tmp_path)
    engine.state.mode = "llm"
    engine.state.edf_snapshot = replace(
        engine.state.edf_snapshot,
        learner_state="CLARIFYING",
        pedagogical_strategy="give_choices",
        dialogue_act="micro_check_confusion",
    )
    engine.state.memory_snapshot = replace(engine.state.memory_snapshot, repeated_confusion_count=1)
    agent = SlowSimulatorAgent(SlowChoiceLlm())

    response = agent.propose_response(
        state=engine.state,
        curriculum=engine.curriculum,
        strategy=TutoringStrategy.GIVE_CHOICES,
        node_id="math_intuition",
        base_prompt=engine.state.current_prompt,
        evidence_signal="unknown",
    )

    assert response.proposal.strategy == "short_reframe"
    assert response.validation_status is ProposalValidationStatus.ACCEPTED
    assert "selection=llm" in response.result.display_summary


def test_fast_tutor_agent_passes_recent_visible_context_to_llm(tmp_path: Path) -> None:
    engine = prepared_engine(tmp_path)
    engine.state.mode = "llm"
    engine.state.transcript.append(
        TranscriptEntry(
            role="assistant",
            text="你覺得廢藩置縣對建立軍隊有什麼好處？",
            phase="tutoring",
        )
    )
    llm = RecordingTutorContextLlm()
    agent = FastTutorAgent(llm)

    response = agent.propose_response(
        state=engine.state,
        curriculum=engine.curriculum,
        strategy=TutoringStrategy.EXPLANATION,
        node_id="math_intuition",
        base_prompt=engine.state.current_prompt,
        evidence_signal="partial_correct",
        context=engine._learning_manager_turn_context("會更統一、行動一致?"),
    )

    assert response.validation_status is ProposalValidationStatus.ACCEPTED
    assert llm.kwargs["last_assistant_prompt"] == "你覺得廢藩置縣對建立軍隊有什麼好處？"
    assert llm.kwargs["recent_messages"][-1]["text"] == "你覺得廢藩置縣對建立軍隊有什麼好處？"


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


def test_question_only_unknown_tutor_proposal_is_not_rejected_by_validator(tmp_path: Path) -> None:
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

    assert response.validation_status is ProposalValidationStatus.ACCEPTED
    assert response.result.reason_code == "accepted"
    assert response.proposal.source == "llm"
    assert response.proposal.response == "你認為這個概念還可以從哪個角度繼續拆解？"


def test_humanities_partial_correct_without_acknowledgement_is_not_rejected_by_validator(tmp_path: Path) -> None:
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
        base_message="你說到改革與西化是對的，我再補一點。\n\n先不用完整重述。你可以先說說看最關鍵的轉折點是哪一個？",
    )

    assert response.validation_status is ProposalValidationStatus.ACCEPTED
    assert response.result.reason_code == "accepted"
    assert response.proposal.source == "llm"
    assert "明治維新的背景脈絡" in response.proposal.response
