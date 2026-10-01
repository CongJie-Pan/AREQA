"""Deterministic marker constants for memory ingestion rules.

These constants drive narrow normalization and learning-preference matching.
They contain no secrets and should not be expanded into broad semantic matching
without tests that protect provenance and privacy boundaries.
"""

from __future__ import annotations

_CONCRETE_EXAMPLE_MARKERS = ("具體例子", "具體案例", "實際例子", "實際情境")
_ABSTRACT_CONCEPT_MARKERS = ("抽象概念", "抽象原理")
_NEGATIVE_PREFERENCE_MARKERS = ("不喜歡", "討厭", "不希望", "不想要")
_CONCRETE_ABSTRACT_PREFERENCE_KEY = (
    "learning_preference:abstract_concepts:concrete_examples"
)
_GOAL_MATCH_NOISE = (
    "請在這段期間協助我安排練習",
    "請不要再提醒我",
    "不要再提醒我",
    "不用再提醒我",
    "停止提醒",
    "我已經",
    "我想",
    "這個月",
    "這週",
    "下週",
    "目前",
    "已經",
    "完成了",
    "完成",
    "複習目標",
    "學習目標",
    "讀書計畫",
    "目標",
    "複習",
    "請",
    "的",
)
