"""Answer language follows the learner's words, not quoted passages or client prompt text."""

import re
from pathlib import Path

import pytest

from services.conversation.language import (
    CLIENT_QUOTE_PROMPTS,
    detect_reply_language,
    resolve_answer_language,
)

FRONTEND_PROMPTS = Path(__file__).resolve().parents[2] / "frontend/src/contexts/UserPreferencesContext.tsx"


@pytest.mark.parametrize(("interface", "message", "expected"), [
    # Explain button in an English UI on a Chinese passage (the reported case).
    ("en", "Please explain this passage:\n\n> 《尼各馬可倫理學》", "繁體中文"),
    ("en", "Please explain this passage:\n\n> 请解释这一段关于学习的话", "簡體中文"),
    ("en", "Please explain this passage:\n\n> It is the mark of an educated mind.", "English"),
    # Quote flow with the default prompt.
    ("en", "> 尼各馬可倫理學是亞里斯多德的著作\n\nPlease answer this quoted passage.", "繁體中文"),
    # The learner's own words decide when they wrote some.
    ("en", "> 尼各馬可倫理學是亞里斯多德的著作\n\nWhat is this book mainly about?", "English"),
    ("en", "> It is the mark of an educated mind.\n\n這句話是什麼意思？", "繁體中文"),
    # A Chinese UI still keeps its Chinese preference for an English passage.
    ("zh-TW", "請幫我解釋這段文字：\n\n> It is the mark of an educated mind.", "繁體中文"),
])
def test_answer_language_ignores_client_prompt_text(interface, message, expected):
    assert resolve_answer_language(interface, message) == expected


def test_language_named_inside_a_quote_is_not_a_request():
    message = "> Students practised English every morning before class.\n\n這段在描述什麼？"

    assert resolve_answer_language("en", message) == "繁體中文"


def test_messages_without_quotes_are_unchanged():
    assert resolve_answer_language("en", "Please answer in Chinese: what is Bayes theorem?") == "繁體中文"
    assert resolve_answer_language("en", "Explain Bayes theorem simply") == "English"
    assert resolve_answer_language("zh-TW", "請解釋貝氏定理") == "繁體中文"


def test_short_replies_follow_the_quoted_passage():
    assert detect_reply_language("en", "Please explain this passage:\n\n> 你好") == "zh-TW"
    assert detect_reply_language("zh-TW", "請幫我解釋這段文字：\n\n> hello") == "en"


def test_client_prompts_match_the_frontend_strings():
    """Keeps the backend list in sync when the frontend changes its wording."""

    source = FRONTEND_PROMPTS.read_text(encoding="utf-8")
    explain = re.findall(r"textSelectionExplainPrompt: '(.+?)\\n\\n\{text\}'", source)
    default = re.findall(r"quotedTextDefaultPrompt: '(.+?)'", source)

    assert len(explain) == 3 and len(default) == 3
    assert set(explain) | set(default) == CLIENT_QUOTE_PROMPTS
