"""Budget trusted retrieval independently of user text at the provider boundary."""
from __future__ import annotations

from copy import deepcopy
import json
import logging
import re
from typing import Any

from services.conversation.attachment_budget import conversation_view

logger = logging.getLogger(__name__)


class ContextBudgetError(ValueError):
    """Carry a stable reason code and content-free sizes to the stream logger."""

    def __init__(self, reason: str, **sizes: int):
        """Initialize content-free rejection diagnostics.

        Args:
            reason: Internal stable reason code, never an arbitrary provider error.
            sizes: Numeric serialized sizes/reservations only, never prompt text.
        """
        super().__init__(reason)
        self.reason = reason
        self.sizes = sizes


def token_bound(value: Any) -> int:
    """Return a conservative UTF-8 byte proxy including serialized framing.

    Args:
        value: JSON-compatible provider content, never logged here.

    Returns:
        Conversation-only UTF-8 size plus framing. Attachment payloads use a
        separate reading allowance; this function never rewrites provider input.
    """
    return len(json.dumps(conversation_view(value), ensure_ascii=False, separators=(',', ':')).encode('utf-8')) + 16


def _shorten_source(source: str, allowance: int) -> str:
    lines = source.splitlines()
    header = lines[0]
    if len(lines) > 1 and lines[1].startswith('URL: '):
        header += '\n' + lines.pop(1)
    body = '\n'.join(lines[1:])
    if token_bound(source) <= allowance:
        return source
    suffix = ' … [excerpt shortened]'
    if not body or token_bound(header + '\n' + body[:1] + suffix) > allowance:
        return ''
    low, high = 1, len(body)
    while low < high:
        mid = (low + high + 1) // 2
        if token_bound(header + '\n' + body[:mid] + suffix) <= allowance:
            low = mid
        else:
            high = mid - 1
    return header + '\n' + body[:low] + suffix


def _select_sources(prefix: str, allowance: int) -> tuple[str, int, int]:
    wrapper_start, wrapper_end = '<context>\n', '\n</context>\n\n'
    text = prefix.strip()
    if text.startswith('<context>') and text.endswith('</context>'):
        text = text[len('<context>'):-len('</context>')].strip()
    blocks = [part.strip() for part in re.split(r'(?m)(?=^\[文獻\d+\])', text) if part.strip()]
    if not blocks:
        return '', 0, 0
    if token_bound(prefix) <= allowance:
        return prefix, len(blocks), len(blocks)
    # Each source retains its original identifier and URL; never renumber UI citations.
    share = max(0, (allowance - token_bound(wrapper_start + wrapper_end)) // len(blocks))
    selected = [shortened for block in blocks if (shortened := _shorten_source(block, share))]
    result = wrapper_start + '\n\n'.join(selected) + wrapper_end if selected else ''
    return result, len(blocks), len(selected)


def budget_retrieval(
    messages: list[dict[str, Any]], *, retrieval_context: str, budget: int,
    conversation_id: str = '', text_budget: int | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Shrink only the exact server-supplied retrieval prefix when context is full.

    Args:
        messages: Assembled prompt, possibly with multimodal user content.
        retrieval_context: Trusted request-scoped prefix previously prepended by
            ConversationContextService. User-authored context tags are not parsed.
        budget: Input allowance after tools, completion and safety reservations.
        conversation_id: Safe correlation ID for numeric budget diagnostics.
        text_budget: Standalone text allowance, before attachment reservation.

    Returns:
        Copied messages and whether all source excerpts were omitted, with the
        current question and attachments intact. If no
        source excerpt fits, an explicit unavailable-evidence marker is used when
        possible. The UI's source inventory is never rewritten.

    Raises:
        ContextBudgetError: Mandatory instructions/user content cannot fit, or
            the trusted prefix does not match the current user text. Never cut
            unknown user text to recover from a broken assembly contract.

    Side Effects:
        INFO retrieval.context_budgeted records only correlation ID, counts and
        serialized sizes; no text, URLs, source titles or credentials are logged.
    """
    if not retrieval_context:
        return list(messages), False
    copied = deepcopy(messages)
    index = next((i for i in range(len(copied) - 1, -1, -1) if copied[i].get('role') == 'user'), None)
    if index is None:
        raise ContextBudgetError('missing_current_turn', budget=budget)
    content = copied[index].get('content')
    part = None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        part = next((p for p in content if isinstance(p, dict) and p.get('type') == 'text'
                     and isinstance(p.get('text'), str) and p['text'].startswith(retrieval_context)), None)
        text = part['text'] if part else ''
    else:
        text = ''
    if not text.startswith(retrieval_context):
        raise ContextBudgetError('retrieval_prefix_mismatch', budget=budget,
                                 retrieval_bytes=token_bound(retrieval_context))
    raw_text = text[len(retrieval_context):]
    if part is not None:
        part['text'] = raw_text
    else:
        copied[index]['content'] = raw_text
    instructions = [m for m in copied if m.get('role') in ('system', 'developer')]
    current = [m for m in copied[index:] if m.get('role') not in ('system', 'developer')]
    sizes = dict(budget=budget, instructions_bytes=token_bound(instructions),
                 current_turn_bytes=token_bound(current), retrieval_bytes=token_bound(retrieval_context))
    mandatory_size = token_bound(instructions + current)
    if mandatory_size > budget:
        reason = 'instructions_too_large' if token_bound(instructions) > budget else 'current_turn_too_large'
        if text_budget is not None and mandatory_size <= text_budget:
            reason = 'combined_context_too_large'
        raise ContextBudgetError(reason, **sizes)
    # Leave room for history/summary rather than letting optional evidence consume it all.
    allowance = (token_bound(retrieval_context) if token_bound(messages) <= budget
                 else max(0, min(budget // 3, budget - mandatory_size - 32)))
    selected, source_count, retained_count = _select_sources(retrieval_context, allowance)
    if not selected:
        unavailable = '<context>\nNo source excerpts fit this turn. Do not cite unavailable evidence.\n</context>\n\n'
        selected = unavailable if token_bound(unavailable) <= allowance else ''
    if part is not None:
        part['text'] = selected + raw_text
    else:
        copied[index]['content'] = selected + raw_text
    # Validate serialized framing too, including escaped newlines and multimodal parts.
    if token_bound(instructions + [m for m in copied[index:] if m.get('role') not in ('system', 'developer')]) > budget:
        raise ContextBudgetError('retrieval_budget', **sizes)
    logger.info(
        'retrieval.context_budgeted conversation_id=%s budget=%d instructions_bytes=%d current_turn_bytes=%d '
        'original_retrieval_bytes=%d selected_retrieval_bytes=%d source_count=%d retained_sources=%d trimmed=%s',
        conversation_id, budget, sizes['instructions_bytes'], sizes['current_turn_bytes'],
        sizes['retrieval_bytes'], token_bound(selected), source_count, retained_count, selected != retrieval_context,
    )
    return copied, retained_count == 0
