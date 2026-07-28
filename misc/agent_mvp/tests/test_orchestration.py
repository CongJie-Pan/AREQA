"""Tests for the orchestration-oriented Agent MVP."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.delegation import DelegationManager, build_child_system_prompt
from core.orchestrator import OrchestratorAgent
from core.tools import ToolRegistry


class FakeChatCompletions:
    """Minimal fake OpenAI-compatible chat completions endpoint."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("No fake responses left.")
        return SimpleNamespace(choices=[SimpleNamespace(message=self.responses.pop(0))])


class FakeClient:
    """Minimal fake client exposing ``chat.completions.create``."""

    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(responses))


def message(content="", tool_calls=None):
    """Build a fake assistant message."""
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def tool_call(name, arguments, call_id="call_1"):
    """Build a fake tool call."""
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def base_tools():
    """Return normal tools shared by orchestrator and children."""
    registry = ToolRegistry()

    def echo(text: str) -> str:
        """Echo text."""
        return text

    registry.register_tool(echo)
    return registry


def test_orchestrator_can_delegate_and_synthesize():
    """The top-level orchestrator should expose delegate_task as a model tool."""
    client = FakeClient(
        [
            message(
                tool_calls=[
                    tool_call(
                        "delegate_task",
                        '{"goal": "inspect architecture", "context": "repo", "role": "leaf"}',
                    )
                ]
            ),
            message("Child found a small agent loop."),
            message("Final synthesis from child result."),
        ]
    )
    traces = []
    agent = OrchestratorAgent(
        base_tool_factory=base_tools,
        client=client,
        trace_callback=traces.append,
    )

    result = agent.run_conversation("Review this architecture.")

    assert result == "Final synthesis from child result."
    assert agent.delegation_manager.records[0].status == "completed"
    assert agent.delegation_manager.records[0].role == "leaf"
    assert any(t["event"] == "delegation_started" for t in traces)


def test_leaf_child_does_not_receive_delegate_tool():
    """Leaf children should only receive base tools."""
    manager = DelegationManager(base_tool_factory=base_tools, client=FakeClient([message("done")]))

    result = manager.run_child(goal="single task", role="leaf")

    assert "status=completed" in result
    tool_names = manager.base_tool_factory().tools.keys()
    assert "delegate_task" not in tool_names


def test_max_spawn_depth_rejects_nested_delegation():
    """Delegation must stop when the configured depth is exceeded."""
    manager = DelegationManager(base_tool_factory=base_tools, max_spawn_depth=1)

    result = manager.run_child(goal="too deep", parent_depth=1, role="orchestrator")

    assert "max_spawn_depth reached" in result
    assert manager.records == []


def test_orchestrator_prompt_mentions_delegation_rules():
    """Orchestrator child prompts should explain when delegation is allowed."""
    prompt = build_child_system_prompt(
        goal="coordinate research",
        role="orchestrator",
        depth=1,
        max_spawn_depth=2,
    )

    assert "Orchestrator role" in prompt
    assert "delegate_task" in prompt
