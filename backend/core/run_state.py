from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .budgets import ToolBudget, ToolBudgetTracker


@dataclass(slots=True)
class ConversationRunState:
    """Mutable data scoped to one conversation execution only."""

    context_results: Any = None
    context_prompt: str = ""
    web_search_results: list[dict[str, Any]] = field(default_factory=list)
    tool_budget: ToolBudgetTracker = field(
        default_factory=lambda: ToolBudgetTracker(ToolBudget())
    )
