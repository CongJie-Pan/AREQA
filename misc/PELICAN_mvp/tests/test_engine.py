import pytest
from pathlib import Path

from pelican_mvp.engine import PelicanEngine
from pelican_mvp.domain_skill import DomainCategory
from pelican_mvp.llm import IntakeSemanticSignal
from pelican_mvp.models import (
    AgentRole,
    DiagnosticQuestion,
    KnowledgeNode,
    KnowledgeStatus,
    LearnerIntakeProfile,
    LearningIntent,
    LearningPlanSnapshot,
    MethodologyEventType,
    MethodologyStage,
    NodeState,
    PlanSource,
    ResponseCategory,
    TutoringStrategy,
    BoundedTutorProposal,
)


def test_unknown_student_is_diagnosed_before_original_problem(tmp_path: Path) -> None:
    # Fixture explicitly selected
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    outcome = engine.start()

    assert engine.state.phase == "diagnosis"
    assert outcome.node_id == "cnn_conv"
    assert "診斷題" in outcome.message


def test_default_intake_path(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    outcome = engine.start()

    assert engine.state.phase == "onboarding"
    assert "你想學什麼" in outcome.message

    outcome = engine.respond("深度學習")
    assert engine.state.phase == "onboarding"
    assert "怎麼學" in outcome.message

    outcome = engine.respond("想理解原理")
    assert engine.state.phase == "onboarding"
    assert "基礎" in outcome.message

    outcome = engine.respond("完全沒有基礎")
    assert engine.state.phase == "diagnosis"
    assert engine.state.learning_plan is not None
    assert engine.state.learning_plan.topic == "深度學習"
    assert engine.state.current_node_id == "math_intuition"


def test_respond_allocates_turn_and_cycle_ids(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()

    engine.respond("深度學習")

    assert engine.state.turn_id
    assert engine.state.cycle_id
    assert engine.state.turn_id.startswith("turn_")
    assert engine.state.cycle_id.startswith("cycle_")


def test_start_resume_does_not_allocate_new_turn(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")
    turn_id = engine.state.turn_id
    cycle_id = engine.state.cycle_id
    sequence = engine.state.methodology_sequence

    restored = PelicanEngine(tmp_path)
    restored.start()

    assert restored.state.turn_id == turn_id
    assert restored.state.cycle_id == cycle_id
    assert restored.state.methodology_sequence == sequence


def test_llm_intake_topic_revision_resets_onboarding_topic(tmp_path: Path) -> None:
    class SemanticLlm:
        available = True

        def intake_question(self, *, topic: str, domain_category: DomainCategory, stage: str, model_route=None):
            return f"{topic} 的 {stage} 問題？"

        def classify_intake_semantics(
            self,
            *,
            current_topic: str,
            answer: str,
            stage: str,
            domain_category: DomainCategory,
            model_route=None,
        ):
            return IntakeSemanticSignal(
                intent="topic_revision",
                confidence=0.94,
                reason_code="explicit_correction",
                new_topic="春秋時期歷史",
            )

    engine = PelicanEngine(tmp_path, mode="llm")
    engine.llm = SemanticLlm()
    engine.start()
    engine.respond("明朝歷史")

    outcome = engine.respond("哦哦 我說錯了是春秋時期的歷史")

    assert "春秋時期歷史" in outcome.message
    assert engine.state.phase == "onboarding"
    assert engine.state.intake_profile.topic == "春秋時期歷史"
    assert engine.state.intake_profile.intake_turns == 1
    assert engine.state.intake_profile.intent.value == "unknown"
    assert engine.state.learning_plan is None


def test_rule_intake_topic_revision_fallback_when_llm_unavailable(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("明朝歷史")

    outcome = engine.respond("我說錯了是春秋時期歷史")

    assert "春秋時期歷史" in outcome.message
    assert engine.state.intake_profile.topic == "春秋時期歷史"
    assert engine.state.intake_profile.intake_turns == 1


def test_rule_mode_completes_problem_and_persists(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    engine.respond("不會")
    diagnosis_done = engine.respond("5")

    assert engine.state.phase == "tutoring"
    assert diagnosis_done.node_id == "cnn_conv"
    engine.respond("26")
    engine.respond("26")
    complete = engine.respond("13")

    assert complete.category is ResponseCategory.CORRECT
    assert engine.state.completed is True
    assert "原題完成" in complete.message
    restored = PelicanEngine(tmp_path)
    assert restored.state.completed is True


def test_show_answer_does_not_change_mastery(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    engine.respond("不會")
    engine.respond("5")
    before = engine.state.nodes["cnn_conv"].status
    outcome = engine.respond("show answer")

    assert "不會更新 mastery" in outcome.message
    assert engine.state.nodes["cnn_conv"].status is before


def test_persistent_failure_activates_slow_thinking(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    engine.respond("不會")
    engine.respond("5")
    engine.respond("我不會")
    second = engine.respond("我不會")

    assert second.strategy is TutoringStrategy.EXPLANATION
    assert "slow-thinking" in second.next_reason
    assert engine.state.nodes["cnn_conv"].status is KnowledgeStatus.NOT_MASTERED
    slow_proposals = [
        proposal
        for proposal in engine.state.agent_proposals
        if proposal.role is AgentRole.SLOW_SIMULATOR_AGENT
    ]
    assert slow_proposals
    assert "slow_simulation" in slow_proposals[-1].display_summary
    assert "candidates=" in slow_proposals[-1].display_summary


def test_current_turn_evidence_drives_current_strategy(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    engine.respond("不會")
    engine.respond("5")
    engine.respond("我不會")

    second = engine.respond("我不會")

    assert engine.state.edf_snapshot.pedagogical_strategy == "simplify_or_decompose"
    assert second.strategy is TutoringStrategy.EXPLANATION
    assert engine.state.learner_progress.current_node_id == "cnn_conv"


def test_agent_proposals_are_correlated_to_turn_cycle(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")

    proposal = engine.state.agent_proposals[-1]

    assert proposal.role is AgentRole.INTAKE_AGENT
    assert proposal.turn_id == engine.state.turn_id
    assert proposal.cycle_id == engine.state.cycle_id
    assert proposal.proposal_id.startswith("proposal_")


def test_state_agent_proposal_precedes_diagnostic_mutation(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    before_sequence = engine.state.methodology_sequence

    engine.respond("8")

    state_proposals = [item for item in engine.state.agent_proposals if item.role is AgentRole.STATE_AGENT]
    assert state_proposals
    assert state_proposals[0].sequence > before_sequence
    assert engine.state.nodes["cnn_conv"].status is KnowledgeStatus.MASTERED


def test_methodology_events_use_six_core_stages_and_subsystem_events(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")
    engine.respond("想理解原理")
    engine.respond("完全沒有基礎")
    engine.respond("用來衡量預測與目標之間的差距")

    pipeline_stages = {
        event.stage
        for event in engine.state.methodology_events
        if event.event_type is MethodologyEventType.PIPELINE_STAGE
    }
    event_types = {event.event_type for event in engine.state.methodology_events}

    assert MethodologyStage.GOAL_FRAMING in pipeline_stages
    assert MethodologyStage.SKILL_CONSTRUCTION in pipeline_stages
    assert MethodologyStage.COGNITIVE_DIAGNOSIS in pipeline_stages
    assert MethodologyStage.KNOWLEDGE_STATE_UPDATE in pipeline_stages
    assert MethodologyStage.EDF_STRATEGY_SELECTION in pipeline_stages
    assert MethodologyEventType.GUM_SUBSYSTEM in event_types
    assert MethodologyEventType.LEARNER_INTERACTION in event_types
    assert None not in pipeline_stages


def test_methodology_stage_agents_emit_executor_proposals(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("中國春秋時期歷史")
    engine.respond("想理解春秋時期的政治秩序")
    engine.respond("完全沒有基礎")
    engine.respond("因為周王室控制力下降")

    roles = {proposal.role for proposal in engine.state.agent_proposals}

    assert AgentRole.INTAKE_AGENT in roles
    assert AgentRole.SKILL_AGENT in roles
    assert AgentRole.DIAGNOSIS_AGENT in roles
    assert AgentRole.STATE_AGENT in roles
    assert AgentRole.POLICY_AGENT in roles


def test_llm_mode_without_key_uses_reviewed_rule_question(tmp_path: Path, monkeypatch) -> None:
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    engine = PelicanEngine(tmp_path, mode="llm", curriculum_id="cnn")

    outcome = engine.start()

    assert engine.state.current_prompt_source == "rule"
    assert "診斷題" in outcome.message

def test_start_when_completed(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.state.completed = True
    outcome = engine.start()

    assert "已完成" in outcome.message

def test_llm_mode_fallback_on_respond(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    engine = PelicanEngine(tmp_path, mode="llm", curriculum_id="cnn")
    engine.start()
    outcome = engine.respond("100")

    assert outcome is not None


def _prepared_generated_humanities_engine(tmp_path: Path) -> PelicanEngine:
    """Create a deterministic humanities generated-plan session for flow tests."""
    engine = PelicanEngine(tmp_path, mode="rule")
    plan = LearningPlanSnapshot(
        plan_id="qing_test_plan",
        topic="大清創業的歷史",
        goal_summary="學習大清創業的歷史",
        nodes=(
            KnowledgeNode("jianzhou_jurchen_origins", "建州女真的崛起", priority=1),
            KnowledgeNode(
                "eight_banners_system",
                "八旗制度的建立",
                priority=2,
            ),
        ),
        diagnostics=(
            DiagnosticQuestion(
                "jianzhou_jurchen_origins",
                "請簡述努爾哈赤在起兵初期，是如何在東北地區逐步擴張勢力的？",
                "努爾哈赤整合建州女真",
                source="skill",
            ),
            DiagnosticQuestion(
                "eight_banners_system",
                "八旗制度為什麼有助於後金政權擴張？",
                "八旗整合軍事和社會組織",
                source="skill",
            ),
        ),
        task_steps=(
            {
                "step_id": "qing_step_1",
                "node_id": "jianzhou_jurchen_origins",
                "label": "說明建州女真",
                "prompt": "請說明建州女真如何成為清朝創業基礎。",
                "expected": "努爾哈赤整合建州女真",
            },
        ),
        skill_id="qing_dynasty_founding_history",
        skill_version="0.1.0",
        skill_lifecycle="validated_generated",
        domain_category=DomainCategory.HUMANITIES.value,
        model_route="~google/gemini-pro-latest",
    )
    engine.state.plan_source = PlanSource.GENERATED
    engine.state.learning_plan = plan
    engine.state.phase = "diagnosis"
    engine.state.intake_profile = LearnerIntakeProfile(
        topic=plan.topic,
        goal_summary=plan.goal_summary,
        intent=LearningIntent.CONCEPTUAL,
        level_hint="unknown",
        domain_category=DomainCategory.HUMANITIES.value,
        skill_id=plan.skill_id,
        skill_version=plan.skill_version,
        skill_lifecycle=plan.skill_lifecycle,
        model_route=plan.model_route,
        intake_turns=3,
    )
    engine.state.nodes = {node.node_id: NodeState() for node in plan.nodes}
    engine.curriculum = engine._resolve_curriculum()
    engine.store.save(engine.state)
    engine.start()
    return engine


def test_humanities_unknown_teaches_then_asks_for_restatement(tmp_path: Path) -> None:
    engine = _prepared_generated_humanities_engine(tmp_path)

    outcome = engine.respond("不知道")

    assert outcome.node_id == "jianzhou_jurchen_origins"
    assert "背景脈絡" in outcome.message
    assert "努爾哈赤" in outcome.message
    assert "先不用完整重述" in outcome.message
    assert "最關鍵的原因" in outcome.message
    assert engine.state.phase == "tutoring"
    assert engine.state.nodes["jianzhou_jurchen_origins"].status is KnowledgeStatus.NOT_MASTERED


def test_humanities_restatement_must_pass_before_next_knowledge_point(tmp_path: Path) -> None:
    engine = _prepared_generated_humanities_engine(tmp_path)
    engine.respond("不知道")

    wrong = engine.respond("我還是不太會")

    assert wrong.node_id == "jianzhou_jurchen_origins"
    assert "先不用完整重述" in wrong.message
    assert engine.state.current_node_id == "jianzhou_jurchen_origins"
    assert engine.state.nodes["jianzhou_jurchen_origins"].status is KnowledgeStatus.NOT_MASTERED

    correct = engine.respond("努爾哈赤整合建州女真")

    assert correct.category is ResponseCategory.CORRECT
    assert engine.state.nodes["jianzhou_jurchen_origins"].status is KnowledgeStatus.MASTERED
    assert engine.state.current_node_id == "eight_banners_system"
    assert "八旗制度" in correct.message


def test_humanities_micro_check_clarification_does_not_repeat_lesson_or_update_mastery(tmp_path: Path) -> None:
    engine = _prepared_generated_humanities_engine(tmp_path)
    first = engine.respond("我不知道")
    evidence_count = len(engine.state.direct_evidence)

    clarification = engine.respond("什麼轉折點？")

    assert clarification.node_id == "jianzhou_jurchen_origins"
    assert "這裡的「轉折點」是指" in clarification.message
    assert "A. 前面發生了什麼" in clarification.message
    assert first.message != clarification.message
    assert "??窗" not in clarification.message
    assert len(engine.state.direct_evidence) == evidence_count
    assert engine.state.nodes["jianzhou_jurchen_origins"].status is KnowledgeStatus.NOT_MASTERED
    assert engine.state.current_node_id == "jianzhou_jurchen_origins"
    assert clarification.strategy is TutoringStrategy.GIVE_CHOICES
    assert engine.state.memory_snapshot.recent_dialogue_acts[-1] == "micro_check_confusion"
    assert engine.state.edf_snapshot.dialogue_act == "micro_check_confusion"
    assert engine.state.edf_snapshot.pedagogical_strategy == "give_choices"
    assert engine.state.strategy_decision.dialogue_act == "micro_check_confusion"
    assert engine.state.strategy_decision.selected_strategy is TutoringStrategy.GIVE_CHOICES
    assert {proposal.role for proposal in engine.state.agent_proposals[-2:]} == {
        AgentRole.DIALOGUE_ACT_AGENT,
        AgentRole.POLICY_AGENT,
    }


def test_humanities_llm_mode_uses_model_generated_remediation(tmp_path: Path) -> None:
    class HumanitiesTutorLlm:
        available = True

        def classify(self, prompt: str, expected: str, answer: str) -> ResponseCategory:
            return ResponseCategory.INCORRECT

        def tutor_proposal(self, **kwargs) -> BoundedTutorProposal:
            return BoundedTutorProposal(
                response="模型生成：我先依照這個主題補完整脈絡，最後請你先選一個關鍵轉折點。",
                pedagogical_move="explain_then_restate",
                summary="LLM generated humanities remediation.",
                node_id=kwargs["node_id"],
                strategy=kwargs["strategy"].value,
                evidence_signal=kwargs["evidence_signal"],
                source="llm",
            )

    engine = _prepared_generated_humanities_engine(tmp_path)
    engine.state.mode = "llm"
    engine.llm = HumanitiesTutorLlm()
    engine.store.save(engine.state)
    engine.respond("不知道")

    wrong = engine.respond("我還是不太會")

    assert wrong.message.startswith("模型生成")
    assert wrong.strategy is TutoringStrategy.CORRECTION
