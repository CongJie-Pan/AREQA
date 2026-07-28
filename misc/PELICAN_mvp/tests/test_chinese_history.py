import pytest
import tempfile
from pelican_mvp.curriculum import CURRICULUMS
from pelican_mvp.engine import PelicanEngine
from pelican_mvp.agents import CapabilityPolicy, LearningManagerAction, LearningManagerDecision
from pelican_mvp.domain_skill import DomainCategory
from pelican_mvp.models import (
    DiagnosticQuestion,
    KnowledgeNode,
    LearnerIntakeProfile,
    LearningIntent,
    LearningPlanSnapshot,
    NodeState,
    PlanSource,
)

def test_chinese_history_curriculum_loads() -> None:
    assert "chinese_history" in CURRICULUMS
    curriculum = CURRICULUMS["chinese_history"]
    
    assert len(curriculum.nodes) == 6
    assert "hist_basics" in curriculum.nodes
    assert curriculum.nodes["ming_fall"].prerequisites == ("ming_decline",)

def test_chinese_history_engine_flow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = PelicanEngine(tmpdir, learner_id="test_history", mode="rule", curriculum_id="chinese_history")
        
        # Diagnosis phase starts with the deepest leaf node according to successor-first
        # Leaves: ming_fall (priority 50), so it should start there.
        outcome = engine.start()
        assert outcome.node_id == "ming_fall"
        
        # We answer correctly
        outcome = engine.respond("吳三桂")
        assert outcome.category.value == "correct"
        # It should complete diagnosis phase immediately since ming_fall correctness 
        # infers all prerequisites mastered.
        assert engine.state.phase == "tutoring"
        
        # First task step
        assert engine.state.current_node_id == "ming_founding"
        assert "明朝建立" in engine.state.current_prompt

        # We answer incorrectly
        outcome = engine.respond("李自成")
        assert outcome.category.value == "incorrect"
        assert outcome.strategy == "correction"
        assert "明朝建立" in outcome.message


class FakeLearningManagerOrchestrator:
    """Return one deterministic learning-manager action for history regressions."""

    def __init__(
        self,
        action: LearningManagerAction,
        *,
        capability: str = "",
        policy: CapabilityPolicy = CapabilityPolicy.NONE,
    ) -> None:
        self.action = action
        self.capability = capability
        self.policy = policy

    def interpret_turn(self, context):
        return LearningManagerDecision(
            action=self.action,
            capability=self.capability,
            policy=self.policy,
            target_phase=context.phase,
            confidence=0.95,
            reason_code="test_decision",
            proposal_source="llm",
            snapshot_id=context.snapshot_id,
        )


def meiji_engine(tmp_path) -> PelicanEngine:
    """Create a generated humanities session centered on Meiji turns."""
    engine = PelicanEngine(tmp_path, learner_id="meiji_student", mode="rule")
    plan = LearningPlanSnapshot(
        plan_id="meiji_plan",
        topic="明治維新",
        goal_summary="理解明治維新如何改變日本的政治與社會結構",
        nodes=(
            KnowledgeNode("class_structure", "打破舊有階級", priority=2),
            KnowledgeNode("political_centralization", "政治中央集權", priority=1),
        ),
        diagnostics=(
            DiagnosticQuestion(
                "class_structure",
                "在這些改革中，你覺得哪一項對打破舊有階級影響最深？",
                "廢藩置縣",
                source="skill",
            ),
            DiagnosticQuestion(
                "political_centralization",
                "明治維新如何把政治權力集中到中央政府？",
                "廢藩置縣讓中央政府取代各藩治理地方",
                source="skill",
            ),
        ),
        task_steps=(
            {
                "step_id": "meiji_step_1",
                "node_id": "class_structure",
                "label": "明治改革的社會影響",
                "prompt": "中途島戰役是日本由攻轉守的轉折點；明治維新也有類似的制度轉折。",
                "expected": "明治維新透過廢藩置縣與四民平等，改變政治與社會結構。",
            },
        ),
        skill_id="meiji_restoration_history",
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
        level_hint="beginner",
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
    engine.state.current_node_id = "class_structure"
    engine.state.current_prompt = "在這些改革中，你覺得哪一項對打破舊有階級影響最深？"
    engine.state.current_expected_answer = "廢藩置縣"
    engine.state.current_prompt_source = "skill"
    return engine


def test_meiji_short_answer_to_active_prompt_is_diagnosed(tmp_path) -> None:
    engine = meiji_engine(tmp_path)
    engine.state.mode = "llm"
    engine.learning_manager_orchestrator = FakeLearningManagerOrchestrator(
        LearningManagerAction.CALL_CAPABILITY,
        capability="diagnose_answer",
        policy=CapabilityPolicy.WRITE_PROPOSED,
    )

    outcome = engine.respond("廢藩置縣")

    assert outcome.category is not None
    assert outcome.category.value == "correct"
    assert engine.state.history[-1].response == "廢藩置縣"


def test_meiji_turning_point_question_gets_focused_clarification(tmp_path) -> None:
    engine = meiji_engine(tmp_path)
    engine.state.phase = "tutoring"
    engine._set_current_step(engine.state.learning_plan.task_steps[0])
    engine.state.mode = "llm"
    engine.learning_manager_orchestrator = FakeLearningManagerOrchestrator(
        LearningManagerAction.ANSWER_DIRECTLY,
        policy=CapabilityPolicy.NONE,
    )
    evidence_count = len(engine.state.direct_evidence)

    outcome = engine.respond("什麼轉折點?")

    assert outcome.category is None
    assert "這裡的「轉折點」是指" in outcome.message
    assert len(engine.state.direct_evidence) == evidence_count


def test_meiji_partial_humanities_answer_is_treated_as_substance(tmp_path) -> None:
    engine = meiji_engine(tmp_path)
    engine.state.mode = "llm"
    engine.learning_manager_orchestrator = FakeLearningManagerOrchestrator(
        LearningManagerAction.CALL_CAPABILITY,
        capability="diagnose_answer",
        policy=CapabilityPolicy.WRITE_PROPOSED,
    )

    outcome = engine.respond("簡單來說，明治維新是日本推動西化和現代化的改革。")

    assert outcome.category is not None
    assert engine.state.history[-1].response.startswith("簡單來說")
    assert "這裡的「轉折點」是指" not in outcome.message
