"""Slow simulator agent executor for deeper tutor-response proposals."""

from __future__ import annotations

from ..curriculum import Curriculum
from ..llm import LlmAdapter
from ..models import AgentRole, SessionState, TutoringStrategy
from .base import AgentExecutionContext
from .fast_tutor_agent import TutorAgentResponse, _candidate_or_fallback, _response_from_proposal


class SlowSimulatorAgent:
    """Produce slow-route tutor proposals for repeated or fragile difficulty."""

    role = AgentRole.SLOW_SIMULATOR_AGENT

    def __init__(self, llm: LlmAdapter | None = None) -> None:
        """Create a slow simulator agent around an optional tutor LLM adapter."""
        self.llm = llm or LlmAdapter()

    def propose_response(
        self,
        *,
        state: SessionState,
        curriculum: Curriculum,
        strategy: TutoringStrategy,
        node_id: str,
        base_prompt: str,
        evidence_signal: str,
        recent_safe_signals: tuple[str, ...] = (),
        base_message: str | None = None,
        context: AgentExecutionContext | None = None,
    ) -> TutorAgentResponse:
        """Propose a slow-route response with explicit fallback status."""
        proposal, status, reason = _candidate_or_fallback(
            role=self.role,
            llm=self.llm,
            state=state,
            curriculum=curriculum,
            strategy=strategy,
            node_id=node_id,
            base_prompt=base_prompt,
            evidence_signal=evidence_signal,
            recent_safe_signals=recent_safe_signals,
            base_message=base_message,
            slow_route=True,
        )
        return _response_from_proposal(self.role, proposal, status, reason)
