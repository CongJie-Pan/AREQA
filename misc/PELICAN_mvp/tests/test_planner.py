import pytest
from pelican_mvp.models import DiagnosticQuestion, KnowledgeNode, LearnerIntakeProfile, LearningIntent, LearningPlanSnapshot
from pelican_mvp.planner import LearningPlanner, validate_learning_plan
from pelican_mvp.llm import LlmAdapter, LlmUnavailable
from unittest.mock import Mock


def test_validate_learning_plan_valid():
    plan = LearningPlanSnapshot(
        plan_id="p1",
        topic="test",
        goal_summary="test",
        nodes=(
            KnowledgeNode(node_id="n1", label="1"),
            KnowledgeNode(node_id="n2", label="2", prerequisites=("n1",)),
        ),
        diagnostics=(
            DiagnosticQuestion(node_id="n1", prompt="p", expected_answer="e"),
            DiagnosticQuestion(node_id="n2", prompt="p", expected_answer="e"),
        ),
        task_steps=(
            {"step_id": "s1", "node_id": "n1", "prompt": "p", "expected": "e"},
        )
    )
    validate_learning_plan(plan)


def test_validate_learning_plan_invalid_duplicate_node():
    plan = LearningPlanSnapshot(
        plan_id="p1",
        topic="test",
        goal_summary="test",
        nodes=(
            KnowledgeNode(node_id="n1", label="1"),
            KnowledgeNode(node_id="n1", label="1"),
        )
    )
    with pytest.raises(ValueError, match="Duplicate node_id"):
        validate_learning_plan(plan)


def test_validate_learning_plan_invalid_cycle():
    plan = LearningPlanSnapshot(
        plan_id="p1",
        topic="test",
        goal_summary="test",
        nodes=(
            KnowledgeNode(node_id="n1", label="1", prerequisites=("n2",)),
            KnowledgeNode(node_id="n2", label="2", prerequisites=("n1",)),
        )
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_learning_plan(plan)


def test_planner_fallback(caplog):
    import logging
    caplog.set_level(logging.INFO)
    mock_llm = Mock(spec=LlmAdapter)
    mock_llm.available = False
    planner = LearningPlanner(mock_llm)

    plan = planner.create_plan("SQL JOIN")
    assert plan.topic == "SQL JOIN"
    assert len(plan.nodes) == 2
    assert plan.nodes[0].node_id == "f1"

    # Check log
    fallback_logs = [r for r in caplog.records if r.message == "pelican_plan_generated"]
    assert len(fallback_logs) > 0
    assert fallback_logs[0].plan_source == "fallback"


def test_planner_no_longer_uses_legacy_llm_plan(caplog):
    import logging
    caplog.set_level(logging.INFO)
    mock_llm = Mock(spec=LlmAdapter)
    mock_llm.available = True
    mock_llm.generate_learning_plan.return_value = LearningPlanSnapshot(
        plan_id="legacy",
        topic="legacy",
        goal_summary="legacy",
        nodes=(KnowledgeNode(node_id="n1", label="legacy"),),
    )
    planner = LearningPlanner(mock_llm)

    plan = planner.create_plan("test")
    assert plan.plan_id != "legacy"
    assert plan.nodes[0].node_id == "f1"
    assert mock_llm.generate_learning_plan.call_count == 0

    generated_logs = [r for r in caplog.records if r.message == "pelican_plan_generated"]
    assert len(generated_logs) > 0
    assert generated_logs[-1].plan_source == "fallback"


def test_planner_runtime_failure_uses_generic_domain_skill(caplog):
    import logging
    caplog.set_level(logging.INFO)
    mock_llm = Mock(spec=LlmAdapter)
    mock_llm.available = False
    planner = LearningPlanner(mock_llm)

    plan = planner.create_plan("中國歷史")
    assert plan.topic == "中國歷史"
    assert plan.skill_id == "generic_humanities"
    assert len(plan.nodes) == 3
    assert plan.nodes[0].node_id == "scope_context"

    generated_logs = [r for r in caplog.records if r.message == "pelican_plan_generated"]
    assert generated_logs[-1].plan_source == "skill"
    assert generated_logs[-1].skill_source == "generic:humanities"


def test_planner_uses_catalog_skill_before_llm_for_deep_learning(caplog):
    import logging
    caplog.set_level(logging.INFO)
    mock_llm = Mock(spec=LlmAdapter)
    mock_llm.available = True
    planner = LearningPlanner(mock_llm)

    plan = planner.create_plan("深度學習")

    assert [node.node_id for node in plan.nodes] == [
        "math_intuition",
        "vectors_tensors",
        "functions_transformations",
    ]
    assert plan.skill_id == "deep_learning"
    assert plan.skill_lifecycle == "validated_generated"
    assert plan.model_route == "catalog"
    assert mock_llm.generate_learning_plan.call_count == 0
    generated_logs = [r for r in caplog.records if r.message == "pelican_plan_generated"]
    assert generated_logs[-1].plan_source == "skill"
    assert generated_logs[-1].skill_id == "deep_learning"


def test_planner_profile_aware_method_selects_implementation_route() -> None:
    mock_llm = Mock(spec=LlmAdapter)
    mock_llm.available = False
    planner = LearningPlanner(mock_llm)
    profile = LearnerIntakeProfile(
        topic="深度學習",
        intent=LearningIntent.IMPLEMENTATION,
        level_hint="beginner",
        intake_turns=1,
    )

    plan = planner.create_plan_for_profile(profile)

    node_ids = [node.node_id for node in plan.nodes]
    assert "mlp_implementation" in node_ids
    assert node_ids[0] == "math_intuition"
