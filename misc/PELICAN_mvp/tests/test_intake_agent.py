from pathlib import Path

from pelican_mvp.agents import AgentExecutionContext, IntakeAgent
from pelican_mvp.domain_skill import DomainSkill
from pelican_mvp.models import LearningIntent
from pelican_mvp.skill_artifacts import save_validated_skill_artifact
from test_skill_agent import spring_autumn_payload


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


def test_intake_agent_routes_topic_from_relevant_validated_skill_cache(tmp_path: Path) -> None:
    payload = spring_autumn_payload()
    payload["skill_id"] = "tokugawa_polity_transition"
    payload["title"] = "Tokugawa polity transition"
    payload["supported_topics"] = ["Tokugawa polity transition", "late shogunate institutions"]
    cached = DomainSkill.from_dict(payload)
    save_validated_skill_artifact(cached, topic="Tokugawa polity transition", route="route/humanities", root=tmp_path)
    agent = IntakeAgent(artifact_root=tmp_path)

    interpretation = agent.propose_topic(
        "learn Tokugawa polity transition",
        context=AgentExecutionContext(turn_id="turn_safe"),
    )

    assert interpretation.domain_resolution is not None
    assert interpretation.domain_resolution.category.value == "humanities"
    assert interpretation.domain_resolution.reason_code == "matched_validated_skill_artifact"


def test_intake_agent_goal_and_level_are_bounded_labels() -> None:
    agent = IntakeAgent()

    goal = agent.propose_goal("想理解春秋政治秩序", LearningIntent.CONCEPTUAL)
    level = agent.propose_level("beginner")

    assert goal.intent is LearningIntent.CONCEPTUAL
    assert goal.result.reason_code == "conceptual"
    assert level.level_hint == "beginner"
    assert level.result.reason_code == "beginner"
