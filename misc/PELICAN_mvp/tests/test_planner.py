import pytest
from pelican_mvp.models import DiagnosticQuestion, KnowledgeNode, LearningPlanSnapshot
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


def test_planner_llm_success(caplog):
    import logging
    caplog.set_level(logging.INFO)
    mock_llm = Mock(spec=LlmAdapter)
    mock_llm.available = True
    valid_plan = LearningPlanSnapshot(
        plan_id="p1",
        topic="test",
        goal_summary="test",
        nodes=(
            KnowledgeNode(node_id="n1", label="1"),
        ),
        diagnostics=(
            DiagnosticQuestion(node_id="n1", prompt="p", expected_answer="e"),
        ),
        task_steps=(
            {"step_id": "s1", "node_id": "n1", "prompt": "p", "expected": "e"},
        )
    )
    mock_llm.generate_learning_plan.return_value = valid_plan
    planner = LearningPlanner(mock_llm)

    plan = planner.create_plan("test")
    assert plan == valid_plan

    generated_logs = [r for r in caplog.records if r.message == "pelican_plan_generated"]
    assert len(generated_logs) > 0
    assert generated_logs[0].plan_source == "generated"


def test_planner_llm_failure_triggers_fallback(caplog):
    import logging
    caplog.set_level(logging.INFO)
    mock_llm = Mock(spec=LlmAdapter)
    mock_llm.available = True
    mock_llm.generate_learning_plan.side_effect = ValueError("Invalid structure")
    planner = LearningPlanner(mock_llm)

    plan = planner.create_plan("test fallback")
    assert plan.topic == "test fallback"
    assert plan.nodes[0].node_id == "f1"

    fallback_warns = [r for r in caplog.records if r.message == "pelican_plan_fallback"]
    assert len(fallback_warns) > 0
    assert fallback_warns[0].reason_code == "ValueError"
