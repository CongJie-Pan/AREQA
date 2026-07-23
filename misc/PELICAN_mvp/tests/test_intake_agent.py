from pelican_mvp.agents import AgentExecutionContext, IntakeAgent
from pelican_mvp.models import LearningIntent


def test_intake_agent_routes_spring_autumn_topic_without_raw_payload() -> None:
    agent = IntakeAgent()

    interpretation = agent.propose_topic(
        "中國春秋時期歷史 raw secret",
        context=AgentExecutionContext(turn_id="turn_safe"),
    )

    metadata = interpretation.result.to_safe_metadata()
    assert interpretation.domain_resolution is not None
    assert interpretation.domain_resolution.category.value == "humanities"
    assert metadata["role"] == "intake_agent"
    assert metadata["artifact_type"] == "topic_interpretation"
    assert "raw secret" not in metadata["display_summary"]


def test_intake_agent_goal_and_level_are_bounded_labels() -> None:
    agent = IntakeAgent()

    goal = agent.propose_goal("想理解春秋政治秩序", LearningIntent.CONCEPTUAL)
    level = agent.propose_level("beginner")

    assert goal.intent is LearningIntent.CONCEPTUAL
    assert goal.result.reason_code == "conceptual"
    assert level.level_hint == "beginner"
    assert level.result.reason_code == "beginner"
