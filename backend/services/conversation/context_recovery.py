"""One bounded provider-context recovery without changing the current question."""
from copy import deepcopy
import re
from typing import Any

from services.conversation.attachment_budget import is_attachment


_CODES = {'context_length_exceeded', 'context_window_exceeded', 'max_context_length_exceeded', 'prompt_too_long'}


def is_provider_context_error(error: Exception) -> bool:
    """Recognize explicit context codes or capacity phrases on 400/413 only.

    Provider bodies are inspected locally and never logged; unrelated rate-limit,
    auth, transport and server errors must not trigger context retries.
    """
    status = getattr(error, 'status_code', None)
    if status not in (400, 413):
        return False
    body = getattr(error, 'body', None)
    if not isinstance(body, dict):
        return False
    detail = body.get('error', body)
    if not isinstance(detail, dict):
        return False
    if str(detail.get('code')) in _CODES or str(detail.get('type')) in _CODES:
        return True
    message = str(detail.get('message', ''))[:8192].lower()
    return any(phrase in message for phrase in (
        'maximum context length', 'context length exceeded', 'context window exceeded',
        'exceeds the context window', 'too many input tokens',
    ))


def minimal_retry_context(selected: list[dict[str, Any]], original: list[dict[str, Any]],
                          retrieval_prefix: str) -> tuple[list[dict[str, Any]], bool]:
    """Keep instructions and the entire current turn; remove only trusted evidence.

    The original assembly supplies the exact user text after the server retrieval
    prefix. A trimmed prefix is removed only if that original suffix still matches.
    Attachments, tool pairs and user-authored context tags remain unchanged.
    """
    start = next((i for i in range(len(selected) - 1, -1, -1) if selected[i].get('role') == 'user'), 0)
    kept = [m for m in selected[:start] if m.get('role') in ('system', 'developer')] + selected[start:]
    result = deepcopy(kept)
    original_user = next((m for m in reversed(original) if m.get('role') == 'user'), {})
    retry_user = next((m for m in reversed(result) if m.get('role') == 'user'), {})

    def text_parts(message):
        content = message.get('content')
        if isinstance(content, str):
            return [(message, 'content')]
        return [(part, 'text') for part in content or [] if isinstance(part, dict) and part.get('type') == 'text' and not is_attachment(part)]

    removed = False
    if retrieval_prefix:
        for source, key in text_parts(original_user):
            if not source[key].startswith(retrieval_prefix):
                continue
            raw = source[key][len(retrieval_prefix):]
            for target, target_key in text_parts(retry_user):
                current = target[target_key]
                if current.endswith(raw) and current != raw:
                    target[target_key] = raw
                    removed = True
                    break
            break
    return result, removed


class UnavailableCitationFilter:
    """Remove source citation markers across chunk boundaries when no evidence remains."""

    def __init__(self):
        self.pending = ''

    def feed(self, text: str) -> str:
        """Release ordinary text, buffering a bounded potentially split citation."""
        self.pending += text
        text = re.sub(r'[【\[]文獻\s*\d+(?:\s*[,、]\s*\d+)*[】\]]', '', self.pending)
        start = max(text.rfind('【'), text.rfind('['))
        if start >= 0 and len(text) - start < 64 and not any(c in text[start:] for c in ('】', ']')):
            self.pending = text[start:]
            return text[:start]
        self.pending = ''
        return text

    def finish(self) -> str:
        """Flush ordinary trailing text; discard an unfinished source citation."""
        text, self.pending = self.pending, ''
        return '' if re.match(r'^[【\[]文獻', text) else text
