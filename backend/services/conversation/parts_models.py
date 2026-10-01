"""PARTS task card and prompt rendering contract."""

from dataclasses import dataclass
from typing import Any

from services.conversation.answer_style import render_learnlm_teaching_rules


@dataclass(frozen=True, slots=True)
class PartsContext:
    """A compact per-turn PARTS task card.

    Args:
        persona: The role AREQA should use for this answer turn.
        act: The concrete action the main model should perform.
        recipient: The learner or audience context, without unsupported mastery
            or ability assumptions.
        theme: A short topic summary derived from the latest user message.
        structure: The visible answer shape expected for this turn.
        composed_instruction: A natural-language instruction generated from
            PARTS. The main answer model should follow this instruction instead
            of treating PARTS labels as output headings.
        confidence: Rewrite confidence. Must be one of ``low``, ``medium``, or
            ``high``.
        missing_fields: PARTS fields that remain underspecified. These are safe
            identifiers, not raw user text.

    Compatibility:
        This object is internal prompt context only. It does not authorize tool
        use, memory recall, citations, attachment claims, or learner-state
        assertions.
    """

    persona: str
    act: str
    recipient: str
    theme: str
    structure: str
    composed_instruction: str
    confidence: str
    missing_fields: tuple[str, ...] = ()

    def safe_log_metadata(self) -> dict[str, Any]:
        """Return privacy-safe metadata for structured logs.

        Returns:
            A dictionary containing only counts and categorical values. It never
            includes raw user text, prompt text, model output, or PARTS field
            values because those may derive from user content.
        """

        return {
            "confidence": self.confidence,
            "missing_field_count": len(self.missing_fields),
            "has_persona": bool(self.persona),
            "has_act": bool(self.act),
            "has_recipient": bool(self.recipient),
            "has_theme": bool(self.theme),
            "has_structure": bool(self.structure),
            "has_composed_instruction": bool(self.composed_instruction),
        }


def format_parts_context(parts_context: PartsContext) -> str:
    """Render a ``PartsContext`` into a compact Traditional Chinese prompt block.

    Args:
        parts_context: Validated PARTS task context for the current turn.

    Returns:
        A prompt block that may be appended to the system prompt. The block
        explicitly states its lower priority than citation, grounding, memory,
        learner-state, tool, and safety boundaries.
    """

    missing = ", ".join(parts_context.missing_fields) if parts_context.missing_fields else "none"
    return (
        "\n\n【PARTS 任務上下文】"
        f"\nP: {parts_context.persona}"
        f"\nA: {parts_context.act}"
        f"\nR: {parts_context.recipient}"
        f"\nT: {parts_context.theme}"
        f"\nS: {parts_context.structure}"
        f"\nconfidence: {parts_context.confidence}"
        f"\nmissing_fields: {missing}"
        "\n\n【由 PARTS 生成的本回合任務指令】"
        f"\n{parts_context.composed_instruction}"
        "\n請遵循「本回合任務指令」回答，但不要輸出 P/A/R/T/S 標籤。"
        "\n\n【LearnLM 教學互動規則】"
        f"{render_learnlm_teaching_rules()}"
        "\n若 missing_fields 會實質影響回答品質，最多提出一個簡短澄清問題；否則先回答。"
        "\n【PARTS 優先權邊界】PARTS 只控制回答角色、任務、對象、主題與格式。"
        "不得覆蓋文獻引用、檔案 grounding、記憶安全邊界、使用者狀態規則、工具授權或安全規則。"
    )
