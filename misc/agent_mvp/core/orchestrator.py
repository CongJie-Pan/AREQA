"""Top-level orchestration agent for the Agent MVP."""

from __future__ import annotations

from typing import Callable

from .agent import Agent, DEFAULT_MODEL
from .delegation import DelegationManager
from .memory import Memory
from .tools import ToolRegistry


ORCHESTRATOR_SYSTEM_PROMPT = """You are an orchestration-oriented AI agent.

Your job is to decide whether to answer directly or use tools.
Use `delegate_task` only when the user's request is meaningfully decomposable,
research-heavy, or benefits from an isolated specialist worker.

Rules:
- Do simple tasks directly.
- Respect explicit user routing requests. If the user asks you to use, ask,
  assign, or delegate to a child/subagent, call delegate_task even when the
  subtask is simple.
- Use normal tools directly when one tool call is enough and the user did not
  ask for a child/subagent to handle it.
- Delegate independent subtasks, not your entire job.
- When delegating conceptual analysis, set tool_policy="none".
- Set tool_policy="base" only when the child needs normal tools.
- If the delegated task involves arithmetic, lookup, weather, or any tool-backed
  action, set tool_policy="base" so the child can call the required normal tool.
- Set tool_policy="delegate" only for a child orchestrator that must spawn workers.
- For normal specialist children, set role="leaf".
- For a child that must coordinate other children, set role exactly to "orchestrator".
- Put descriptive job titles in the goal or context, not in the role field.
- After delegation, synthesize the child summaries into one final answer.
- Be concise and clear about uncertainty.
"""


class OrchestratorAgent:
    """Compose a top-level agent with delegation capability.

    Args:
        base_tool_factory: Callable returning the normal tools visible to the
            top-level agent and child agents.
        model: OpenRouter/OpenAI-compatible model route.
        max_iterations: Maximum iterations for the top-level agent.
        child_max_iterations: Maximum iterations for each child agent.
        max_spawn_depth: Maximum delegation depth.
        client: Optional shared OpenAI-compatible client.
        trace_callback: Optional callback receiving safe trace dictionaries.

    Side Effects:
        Owns a top-level ``Agent`` and an in-process ``DelegationManager``. Child
        agents are created synchronously when the model calls ``delegate_task``.
    """

    def __init__(
        self,
        *,
        base_tool_factory: Callable[[], ToolRegistry],
        model: str = DEFAULT_MODEL,
        max_iterations: int = 8,
        child_max_iterations: int = 5,
        max_spawn_depth: int = 2,
        client=None,
        trace_callback=None,
    ) -> None:
        self.delegation_manager = DelegationManager(
            base_tool_factory=base_tool_factory,
            model=model,
            max_iterations=child_max_iterations,
            max_spawn_depth=max_spawn_depth,
            client=client,
            trace_callback=trace_callback,
        )

        registry = base_tool_factory()
        registry.register_tool(
            self.delegation_manager.build_delegate_tool(current_depth=0),
            name="delegate_task",
            description=(
                "Delegate a focused subtask to an isolated child agent. Use this "
                "for independent, reasoning-heavy work; do not use it for simple tasks. "
                "Set tool_policy to 'none' for conceptual analysis, 'base' for "
                "normal tools, or 'delegate' for nested orchestration. Role must "
                "be exactly 'leaf' or 'orchestrator'; put job titles in goal or context."
            ),
        )
        memory = Memory(system_prompt=ORCHESTRATOR_SYSTEM_PROMPT)
        self.agent = Agent(
            memory=memory,
            tool_registry=registry,
            model=model,
            max_iterations=max_iterations,
            client=client,
            name="orchestrator",
            role="orchestrator",
            depth=0,
            trace_callback=trace_callback,
        )

    def run_conversation(self, user_message: str) -> str:
        """Run one top-level orchestrated user turn.

        Args:
            user_message: Latest user input.

        Returns:
            Final response synthesized by the top-level agent.
        """
        return self.agent.run_conversation(user_message)
