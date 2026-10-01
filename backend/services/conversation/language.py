"""Resolve answer language and language-specific example instructions."""

import re

ANSWER_LANGUAGE_RULES = {
    "zh-TW": "繁體中文",
    "zh-CN": "簡體中文",
    "en": "English",
}

LANGUAGE_REQUEST_PATTERNS = (
    ("zh-CN", re.compile(r"(簡體中文|简体中文|簡中|简中|simplified chinese|zh-cn)", re.IGNORECASE)),
    ("zh-TW", re.compile(r"(繁體中文|繁中|用中文|中文回答|以中文|in chinese|chinese|traditional chinese|zh-tw)", re.IGNORECASE)),
    ("en", re.compile(r"(english|英文|英語|英语|in english)", re.IGNORECASE)),
)

SIMPLIFIED_CHINESE_HINTS = set(
    "请释贝叶这为个学习体汉语数据问题后应对话时会么说认门见过与现"
    "简体话级无论实线图历广义狭义"
)
TRADITIONAL_CHINESE_HINTS = set(
    "請釋貝葉這為個學習體漢語數據問題後應對話時會麼說認門見過與現"
    "繁體話級無論實線圖歷廣義狹義"
)


def _looks_predominantly_english(text: str) -> bool:
    """Return whether user-authored text is primarily English.

    Args:
        text: Latest user message after application-level normalization.

    Returns:
        True when Latin letters dominate over CJK characters and there are
        enough alphabetic characters to avoid classifying short symbols or URLs
        as English.

    Side effects:
        None.
    """
    latin_count = len(re.findall(r"[A-Za-z]", text))
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    if cjk_count > 0:
        return latin_count >= 12 and latin_count >= cjk_count * 2
    return latin_count >= 3


def _detect_query_language(text: str) -> str | None:
    """Detect the latest query's primary supported answer language.

    The UI language is a fallback only. Any user-authored Chinese or English
    signal in the current query should choose the answer language for this turn.
    """
    if _looks_predominantly_english(text):
        return "en"

    han_chars = re.findall(r"[\u3400-\u9fff]", text)
    if not han_chars:
        return None

    simplified_score = sum(1 for char in han_chars if char in SIMPLIFIED_CHINESE_HINTS)
    traditional_score = sum(1 for char in han_chars if char in TRADITIONAL_CHINESE_HINTS)
    return "zh-CN" if simplified_score > traditional_score else "zh-TW"


def _explicit_language_request(text: str) -> str | None:
    """Detect explicit answer-language requests in the latest user message.

    Args:
        text: Latest user-authored message.

    Returns:
        A supported interface-language key when the user explicitly requests
        one; otherwise None.

    Side effects:
        None.
    """
    for language, pattern in LANGUAGE_REQUEST_PATTERNS:
        if pattern.search(text):
            return language
    return None


def resolve_answer_language(
    interface_language: str, latest_user_message: str, *, prefer_query_language: bool = False,
) -> str:
    """Resolve final answer language from explicit request, query language, and UI.

    Args:
        interface_language: Persisted UI language sent by the frontend.
        latest_user_message: Current user-authored message.
        prefer_query_language: Use the request's detected language before the UI
            fallback for image generation. Existing chat callers retain their
            Chinese-interface preference by default.

    Returns:
        Human-readable language label for prompt instructions.

    Side effects:
        None.
    """
    explicit_language = _explicit_language_request(latest_user_message)
    if explicit_language:
        return ANSWER_LANGUAGE_RULES[explicit_language]
    query_language = _detect_query_language(latest_user_message)
    if prefer_query_language and query_language:
        return ANSWER_LANGUAGE_RULES[query_language]
    if query_language in {"zh-TW", "zh-CN"}:
        return ANSWER_LANGUAGE_RULES[query_language]
    if interface_language in {"zh-TW", "zh-CN"}:
        return ANSWER_LANGUAGE_RULES[interface_language]
    if query_language:
        return ANSWER_LANGUAGE_RULES[query_language]
    return ANSWER_LANGUAGE_RULES.get(interface_language, ANSWER_LANGUAGE_RULES["zh-TW"])


def _answer_language_instruction(interface_language: str, latest_user_message: str = "") -> str:
    answer_language = resolve_answer_language(interface_language, latest_user_message)
    return (
        f"\n\n【回答語言規則】本回合正式回答必須使用{answer_language}。"
        "語言判斷優先序為：使用者最新訊息的明確語言要求 > 最新訊息中的中文語系訊號 > 介面語言 > 最新訊息主要語言。"
        "圖片導讀、表格說明、清單標題與結尾建議都必須使用同一種回答語言。"
    )


def _example_instruction(interface_language: str, latest_user_message: str = "") -> str:
    """Return a language-matched rule for grounding answers with examples."""
    answer_language = resolve_answer_language(interface_language, latest_user_message)
    if answer_language == "English":
        return (
            "\n【Example requirement】When the user asks about a concept, method, "
            "comparison, process, cause, or abstract idea, include at least one "
            "concrete example that directly illustrates the answer. Keep the "
            "example concise and relevant; do not force an example for simple "
            "factual, translation, formatting, or purely transactional requests."
        )
    if answer_language == "簡體中文":
        return (
            "\n【案例说明要求】当使用者询问概念、方法、比较、流程、原因或抽象想法时，"
            "请至少加入一个能直接说明答案的具体案例。案例要简洁、贴近问题；"
            "若问题只是简单事实、翻译、格式调整或纯操作请求，不要强行加入案例。"
        )
    return (
        "\n【案例說明要求】當使用者詢問概念、方法、比較、流程、原因或抽象想法時，"
        "請至少加入一個能直接說明答案的具體案例。案例要簡潔、貼近問題；"
        "若問題只是簡單事實、翻譯、格式調整或純操作請求，不要強行加入案例。"
    )
