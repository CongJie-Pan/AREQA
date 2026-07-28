"""Tests for the orchestration-oriented Agent MVP."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.delegation import DelegationManager, build_child_system_prompt
from core.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT, OrchestratorAgent
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
                        (
                            '{"goal": "inspect architecture", "context": "repo", '
                            '"role": "leaf", "tool_policy": "none"}'
                        ),
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
    assert agent.delegation_manager.records[0].tool_policy == "none"
    assert any(t["event"] == "delegation_started" for t in traces)


def test_leaf_child_does_not_receive_delegate_tool():
    """Leaf children should only receive base tools."""
    manager = DelegationManager(base_tool_factory=base_tools, client=FakeClient([message("done")]))

    result = manager.run_child(goal="single task", role="leaf")

    assert "status=completed" in result
    tool_names = manager.base_tool_factory().tools.keys()
    assert "delegate_task" not in tool_names


def test_none_tool_policy_hides_base_tools_from_child():
    """Conceptual child tasks should run without unrelated base tools."""
    client = FakeClient(
        [
            message(
                tool_calls=[
                    tool_call("echo", '{"text": "should not be available"}')
                ]
            ),
            message("Recovered after tool rejection."),
        ]
    )
    manager = DelegationManager(base_tool_factory=base_tools, client=client)

    result = manager.run_child(goal="conceptual task", tool_policy="none")
    first_call_tools = client.chat.completions.calls[0].get("tools", [])

    assert first_call_tools == []
    assert "status=completed" in result


def test_base_tool_policy_exposes_base_tools_to_child():
    """Children should receive normal tools only when policy requests them."""
    client = FakeClient([message("done")])
    manager = DelegationManager(base_tool_factory=base_tools, client=client)

    result = manager.run_child(goal="use a base tool if needed", tool_policy="base")
    first_call_tools = client.chat.completions.calls[0].get("tools", [])

    assert "status=completed" in result
    assert any(schema["function"]["name"] == "echo" for schema in first_call_tools)


def test_delegate_tool_policy_exposes_delegate_to_orchestrator_child():
    """Nested delegation should require both orchestrator role and delegate policy."""
    client = FakeClient([message("done")])
    manager = DelegationManager(base_tool_factory=base_tools, client=client, max_spawn_depth=2)

    result = manager.run_child(
        goal="coordinate subtasks",
        role="orchestrator",
        tool_policy="delegate",
    )
    first_call_tools = client.chat.completions.calls[0].get("tools", [])

    assert "role=orchestrator" in result
    assert any(schema["function"]["name"] == "delegate_task" for schema in first_call_tools)


def test_delegate_policy_requires_exact_orchestrator_role():
    """Descriptive role labels must not receive nested delegation tools."""
    client = FakeClient([message("done")])
    manager = DelegationManager(base_tool_factory=base_tools, client=client, max_spawn_depth=2)

    result = manager.run_child(
        goal="coordinate subtasks",
        role="team lead - AI agent teaching coordinator",
        tool_policy="delegate",
    )
    first_call_tools = client.chat.completions.calls[0].get("tools", [])

    assert "role=leaf" in result
    assert "tool_policy=none" in result
    assert first_call_tools == []


def test_orchestrator_at_depth_limit_loses_delegate_policy():
    """Depth-limited orchestrator requests should not keep delegate policy metadata."""
    client = FakeClient([message("done")])
    manager = DelegationManager(base_tool_factory=base_tools, client=client, max_spawn_depth=2)

    result = manager.run_child(
        goal="coordinate subtasks",
        role="orchestrator",
        tool_policy="delegate",
        parent_depth=1,
    )
    first_call_tools = client.chat.completions.calls[0].get("tools", [])

    assert "role=leaf" in result
    assert "tool_policy=none" in result
    assert first_call_tools == []


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
        tool_policy="delegate",
        depth=1,
        max_spawn_depth=2,
    )

    assert "Orchestrator role" in prompt
    assert "delegate_task" in prompt


def test_none_tool_policy_prompt_discourages_example_tool_calls():
    """The child prompt should explicitly block tools-for-examples behavior."""
    prompt = build_child_system_prompt(goal="explain tool calling", tool_policy="none")

    assert "Tool policy: none" in prompt
    assert "do not ask to call tools for examples" in prompt


def test_orchestrator_prompt_grants_base_policy_for_tool_backed_child_tasks():
    """Delegated tool-backed work should be routed with base tool access."""
    assert 'tool_policy="base"' in ORCHESTRATOR_SYSTEM_PROMPT
    assert "arithmetic" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "tool-backed" in ORCHESTRATOR_SYSTEM_PROMPT


def test_orchestrator_prompt_respects_explicit_subagent_routing():
    """Explicit user delegation requests should override direct tool use."""
    assert "Respect explicit user routing requests" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "call delegate_task even when the" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "user did not" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "ask for a child/subagent" in ORCHESTRATOR_SYSTEM_PROMPT
