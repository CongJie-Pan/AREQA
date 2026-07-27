from pathlib import Path

from pelican_mvp.agents import PolicyAgent
from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import AgentRole, TutoringStrategy


def test_policy_agent_uses_current_state_for_strategy_proposal(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    agent = PolicyAgent(engine.edf)

    decision, result = agent.propose_strategy(engine.state)

    assert result.role is AgentRole.POLICY_AGENT
    assert result.artifact_type == "strategy_decision"
    assert result.reason_code == decision.reason_code
    assert result.display_summary.startswith(decision.learner_state)
    assert decision.selected_strategy in set(TutoringStrategy)


def test_policy_agent_uses_valid_llm_edf_decision_in_llm_mode(tmp_path: Path) -> None:
    class PolicyLlm:
        available = True

        def edf_policy_decision(self, **kwargs):
            return {
                "learner_state": "STRUGGLING",
                "route": "slow",
                "selected_strategy": "decomposition",
                "intervention_strength": 0.86,
                "should_advance": False,
                "should_recheck": True,
                "reason_code": "LLM: repeated support needed",
                "dialogue_act": "",
            }

    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    engine.state.mode = "llm"
    agent = PolicyAgent(engine.edf, PolicyLlm())

    decision, result = agent.propose_strategy(engine.state)

    assert decision.selected_strategy is TutoringStrategy.DECOMPOSITION
    assert decision.route == "slow"
    assert decision.reason_code == "llm_repeated_support_needed"
    assert result.proposal_source == "llm"


def test_policy_agent_rejects_invalid_llm_edf_decision(tmp_path: Path) -> None:
    class InvalidPolicyLlm:
        available = True

        def edf_policy_decision(self, **kwargs):
            return {
                "learner_state": "STRUGGLING",
                "route": "unsafe",
                "selected_strategy": "invented_strategy",
                "intervention_strength": 1.5,
                "should_advance": True,
                "should_recheck": False,
                "reason_code": "invalid",
                "dialogue_act": "",
            }

    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    engine.state.mode = "llm"
    agent = PolicyAgent(engine.edf, InvalidPolicyLlm())

    decision, result = agent.propose_strategy(engine.state)

    assert decision.selected_strategy in set(TutoringStrategy)
    assert decision.route != "unsafe"
    assert result.proposal_source == "edf"
