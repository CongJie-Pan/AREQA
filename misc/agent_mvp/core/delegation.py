"""Delegation primitives for orchestration-oriented agent workflows."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable, List

from .agent import Agent, DEFAULT_MODEL
from .memory import Memory
from .tools import ToolRegistry

TOOL_POLICY_NONE = "none"
TOOL_POLICY_BASE = "base"
TOOL_POLICY_DELEGATE = "delegate"
SUPPORTED_TOOL_POLICIES = frozenset({TOOL_POLICY_NONE, TOOL_POLICY_BASE, TOOL_POLICY_DELEGATE})


@dataclass
class DelegationRecord:
    """Safe trace record for one delegated subagent task.

    Args:
        delegation_id: Stable in-process id for this delegated task.
        parent_id: Optional parent delegation id for nested orchestration.
        role: Effective child role, either ``leaf`` or ``orchestrator``.
        tool_policy: Effective tool visibility policy.
        depth: Child delegation depth.
        goal: Delegated goal. This MVP keeps the trace in-process for local
            debugging; production systems should bound or redact this field.
        status: Current lifecycle status.
        result_summary: Final child result or bounded failure summary.
    """

    delegation_id: str
    parent_id: str | None
    role: str
    tool_policy: str
    depth: int
    goal: str
    status: str = "created"
    result_summary: str = ""


@dataclass
class DelegationManager:
    """Create model-callable delegation tools and isolated child agents.

    Args:
        base_tool_factory: Callable that returns the non-delegation tools each
            child may use.
        model: Model route for child agents.
        max_iterations: Maximum model/tool iterations per child turn.
        max_spawn_depth: Maximum depth at which delegation may create children.
        client: Optional shared OpenAI-compatible client.
        trace_callback: Optional callback for safe event dictionaries.

    Compatibility:
        This is intentionally synchronous for MVP clarity. Parent agents block
        until the child returns a final summary, matching the simplest Hermes
        delegation shape without introducing a durable queue.
    """

    base_tool_factory: Callable[[], ToolRegistry]
    model: str = DEFAULT_MODEL
    max_iterations: int = 5
    max_spawn_depth: int = 2
    client: object | None = None
    trace_callback: Callable[[dict], None] | None = None
    records: List[DelegationRecord] = field(default_factory=list)
    _counter: itertools.count = field(default_factory=lambda: itertools.count(1))

    def build_delegate_tool(
        self,
        *,
        current_depth: int = 0,
        parent_id: str | None = None,
    ):
        """Build a ``delegate_task`` closure scoped to one parent agent.

        Args:
            current_depth: Depth of the parent agent that owns the returned tool.
            parent_id: Parent delegation id for nested traces.

        Returns:
            A callable named ``delegate_task`` suitable for ``ToolRegistry``.
        """

        def delegate_task(
            goal: str,
            context: str = "",
            role: str = "leaf",
            tool_policy: str = TOOL_POLICY_NONE,
        ) -> str:
            """Delegate a focused task to an isolated child agent.

            Args:
                goal: Specific task the child must complete.
                context: Optional context needed by the child.
                role: ``leaf`` for a focused worker or ``orchestrator`` for a
                    child that may spawn further workers when depth allows.
                tool_policy: Child tool visibility. Use ``none`` for conceptual
                    analysis, ``base`` when the child needs normal tools, or
                    ``delegate`` when an orchestrator child may spawn workers.

            Returns:
                A concise child summary for the parent model to synthesize.
            """
            return self.run_child(
                goal=goal,
                context=context,
                role=role,
                tool_policy=tool_policy,
                parent_depth=current_depth,
                parent_id=parent_id,
            )

        return delegate_task

    def run_child(
        self,
        *,
        goal: str,
        context: str = "",
        role: str = "leaf",
        tool_policy: str = TOOL_POLICY_NONE,
        parent_depth: int = 0,
        parent_id: str | None = None,
    ) -> str:
        """Create and run one isolated child agent.

        Args:
            goal: Specific delegated goal.
            context: Optional context provided by the parent agent.
            role: Requested child role.
            tool_policy: Requested tool visibility policy.
            parent_depth: Delegation depth of the parent.
            parent_id: Optional parent delegation id.

        Returns:
            Child final response, prefixed with delegation metadata.
        """
        child_depth = parent_depth + 1
        if child_depth > self.max_spawn_depth:
            return (
                "Delegation rejected: max_spawn_depth reached. "
                "Handle the task directly or summarize the limitation."
            )

        effective_role = _normalize_role(role)
        effective_tool_policy = _normalize_tool_policy(tool_policy)
        if effective_role != "orchestrator" and effective_tool_policy == TOOL_POLICY_DELEGATE:
            # A descriptive role like "team lead" still normalizes to leaf. Do
            # not expose nested delegation unless the parent explicitly requests
            # the supported orchestrator role.
            effective_tool_policy = TOOL_POLICY_NONE
        can_delegate = (
            effective_role == "orchestrator"
            and effective_tool_policy == TOOL_POLICY_DELEGATE
            and child_depth < self.max_spawn_depth
        )
        if effective_role == "orchestrator" and not can_delegate:
            effective_role = "leaf"
            if effective_tool_policy == TOOL_POLICY_DELEGATE:
                effective_tool_policy = TOOL_POLICY_NONE

        delegation_id = f"delegation_{next(self._counter)}"
        record = DelegationRecord(
            delegation_id=delegation_id,
            parent_id=parent_id,
            role=effective_role,
            tool_policy=effective_tool_policy,
            depth=child_depth,
            goal=goal,
            status="running",
        )
        self.records.append(record)
        self._trace(
            "delegation_started",
            delegation_id=delegation_id,
            parent_id=parent_id,
            role=effective_role,
            tool_policy=effective_tool_policy,
            depth=child_depth,
        )

        child_registry = self._registry_for_policy(effective_tool_policy)
        if can_delegate:
            child_registry.register_tool(
                self.build_delegate_tool(
                    current_depth=child_depth,
                    parent_id=delegation_id,
                ),
                name="delegate_task",
                description="Delegate a focused subtask to another isolated child agent.",
            )

        child_memory = Memory(
            system_prompt=build_child_system_prompt(
                goal=goal,
                context=context,
                role=effective_role,
                tool_policy=effective_tool_policy,
                depth=child_depth,
                max_spawn_depth=self.max_spawn_depth,
            )
        )
        child = Agent(
            memory=child_memory,
            tool_registry=child_registry,
            model=self.model,
            max_iterations=self.max_iterations,
            client=self.client,
            name=delegation_id,
            role=effective_role,
            depth=child_depth,
            trace_callback=self.trace_callback,
        )

        try:
            result = child.run_conversation(goal)
            record.status = "completed"
            record.result_summary = _bound_text(result)
            self._trace(
                "delegation_completed",
                delegation_id=delegation_id,
                role=effective_role,
                tool_policy=effective_tool_policy,
                depth=child_depth,
            )
            return (
                f"[{delegation_id} | role={effective_role} | "
                f"tool_policy={effective_tool_policy} | status=completed]\n"
                f"{record.result_summary}"
            )
        except Exception as exc:
            record.status = "failed"
            record.result_summary = _bound_text(str(exc))
            self._trace(
                "delegation_failed",
                delegation_id=delegation_id,
                role=effective_role,
                tool_policy=effective_tool_policy,
                depth=child_depth,
            )
            return (
                f"[{delegation_id} | role={effective_role} | "
                f"tool_policy={effective_tool_policy} | status=failed]\n"
                f"{record.result_summary}"
            )

    def _registry_for_policy(self, tool_policy: str) -> ToolRegistry:
        """Return a child tool registry for the effective policy.

        Args:
            tool_policy: Normalized tool policy.

        Returns:
            An empty registry for ``none`` and base tools for other policies.
        """
        if tool_policy == TOOL_POLICY_NONE:
            return ToolRegistry()
        return self.base_tool_factory()

    def _trace(self, event: str, **metadata) -> None:
        """Emit a safe delegation trace event."""
        if self.trace_callback is None:
            return
        payload = {"event": event}
        payload.update(metadata)
        self.trace_callback(payload)


def build_child_system_prompt(
    *,
    goal: str,
    context: str = "",
    role: str = "leaf",
    tool_policy: str = TOOL_POLICY_NONE,
    depth: int = 1,
    max_spawn_depth: int = 2,
) -> str:
    """Build the system prompt for an isolated child agent.

    Args:
        goal: Specific task assigned to the child.
        context: Optional parent-provided background.
        role: Effective role after depth validation.
        tool_policy: Effective child tool visibility policy.
        depth: Child depth in the delegation tree.
        max_spawn_depth: Maximum configured delegation depth.

    Returns:
        A focused system prompt that prevents pass-through delegation and asks
        the child to return a compact, verifiable summary.
    """
    parts = [
        "You are a focused subagent working on one delegated task.",
        "",
        f"Task:\n{goal}",
    ]
    if context.strip():
        parts.extend(["", f"Context:\n{context}"])
    parts.extend(
        [
            "",
            _tool_policy_instruction(tool_policy),
            "Return a concise summary of what you did, what you found, and any issues.",
            "Do not mention hidden chain-of-thought. Report only useful conclusions.",
        ]
    )
    if role == "orchestrator":
        parts.extend(
            [
                "",
                "Orchestrator role:",
                "- You may use delegate_task for independent subtasks.",
                "- Do not delegate trivial work or pass your whole task to one worker.",
                "- Synthesize child results before reporting back.",
                f"- Current depth is {depth}; max_spawn_depth is {max_spawn_depth}.",
            ]
        )
    else:
        parts.extend(["", "Leaf role: complete the assigned task directly; do not delegate."])
    return "\n".join(parts)


def _normalize_role(role: str) -> str:
    """Normalize a requested child role to a supported role."""
    normalized = str(role or "leaf").strip().lower()
    return normalized if normalized in {"leaf", "orchestrator"} else "leaf"


def _normalize_tool_policy(tool_policy: str) -> str:
    """Normalize a requested tool policy to a supported policy."""
    normalized = str(tool_policy or TOOL_POLICY_NONE).strip().lower()
    return normalized if normalized in SUPPORTED_TOOL_POLICIES else TOOL_POLICY_NONE


def _tool_policy_instruction(tool_policy: str) -> str:
    """Return child prompt guidance for the effective tool policy."""
    if tool_policy == TOOL_POLICY_NONE:
        return (
            "Tool policy: none. You do not have tools in this child context. "
            "Analyze conceptually and do not ask to call tools for examples."
        )
    if tool_policy == TOOL_POLICY_DELEGATE:
        return (
            "Tool policy: delegate. Use normal tools only when they are required "
            "for the task, and use delegate_task only for independent subtasks."
        )
    return (
        "Tool policy: base. Use normal tools only when the task genuinely needs "
        "external data or computation. Do not call tools merely to create examples."
    )


def _bound_text(value: str, limit: int = 4000) -> str:
    """Return bounded text suitable for parent-agent context."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 32].rstrip() + "\n...[truncated child summary]"
