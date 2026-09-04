"""Shared constants for visual answer retrieval and caching.

This module centralizes stable visual-answer constants so service facades and
helper mixins can share cache versions, provider priority, and safety allowlists
without importing each other. Constants here are operational policy, not user
content, and must remain safe to reference in structured logs.
"""

from __future__ import annotations

import re

_VISUAL_KEYWORDS = (
    "圖",
    "圖片",
    "圖解",
    "示意圖",
    "範例圖",
    "diagram",
    "image",
    "visual",
    "chart",
    "plot",
)

_IMAGE_META_PATTERN = re.compile(
    r'<meta\s+(?:property|name)=["\'](?:og:image|twitter:image)["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_NEGATIVE_CACHE_SENTINEL = {"status": "negative"}
_VISUAL_CACHE_VERSION = "v6"
_VISUAL_CACHE_CAPABILITY_SCHEMA = "capability_v1"
_NEGATIVE_CACHE_TTL_SECONDS = 21600
_POSITIVE_CACHE_TTL_SECONDS = 2592000
_INACCESSIBLE_IMAGE_DOMAIN_TTL_SECONDS = 21600
_INACCESSIBLE_IMAGE_DOMAIN_CACHE: dict[str, int] = {}
_PROVIDER_PRIORITY = {
    "perplexity_images": 0.3,
    "serpapi_images": 0.28,
    "tavily_images": 0.26,
    "wikimedia": 0.25,
    "openverse": 0.2,
    "og_image": 0.05,
}
_PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
}
_IMAGE_CDN_DOMAIN_SUFFIXES = (
    "gstatic.com",
    "googleusercontent.com",
    "ggpht.com",
)
_PURPOSE_TERMS = {
    "diagram",
    "chart",
    "schematic",
    "plot",
    "graph",
    "illustration",
    "示意圖",
    "圖解",
}
_VISUAL_TYPE_HINTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "map",
        ("地圖", "地图", "戰場", "战场", "戰況", "战况", "map", "battlefield"),
        "educational labeled map",
    ),
    ("chart", ("圖表", "图表", "統計", "统计", "chart", "graph", "plot"), "educational chart"),
    (
        "diagram",
        ("流程", "架構", "结构", "示意", "圖解", "图解", "diagram", "flow"),
        "educational explanatory diagram",
    ),
)
_TRUSTED_SOURCE_DOMAINS = (
    "commons.wikimedia.org",
    "wikimedia.org",
    "wikipedia.org",
    "worldhistory.org",
    "loc.gov",
    "archives.gov",
    "iwm.org.uk",
    "ushmm.org",
    ".edu",
    ".museum",
)
_LOW_QUALITY_SOURCE_DOMAINS = (
    "pinterest.",
    "reddit.com",
    "taobao.com",
    "tmall.",
    "carousell.",
    "quizlet.com",
    "teacherspayteachers.com",
    "studocu.com",
)
_UNSTABLE_IMAGE_INPUT_DOMAINS = {
    "researchgate.net",
}
_NEGATIVE_TERMS = {
    "logo",
    "icon",
    "placeholder",
    "avatar",
    "watermark",
    "sprite",
}
_DEFAULT_VISUAL_USER_AGENT = "AREQA/0.1 visual-answer-retrieval"
_VISUAL_QUERY_REWRITE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "chinese_temple_church_comparison",
        re.compile(r"(寺廟.*教會|教會.*寺廟|temple.*church|church.*temple)", re.IGNORECASE),
        "Chinese temple folk religion Christian church social organization comparison diagram",
    ),
)
