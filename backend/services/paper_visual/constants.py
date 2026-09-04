"""Constants and regexes for paper visual planning.

These values define deterministic section, caption, and fallback-ranking policy
for PDF paper explanation visuals. They contain no user data and are safe to use
as implementation policy across planner modules.
"""

from __future__ import annotations

import re

_FIGURE_CAPTION_PATTERN = re.compile(
    r"\b(?:fig(?:ure)?\.?|table)\s*\d+[A-Za-z]?\b[^\n]{0,220}|(?:圖|表)\s*\d+[^\n]{0,220}",
    re.IGNORECASE,
)
_SECTION_PATTERN = re.compile(
    r"\b(?:abstract|introduction|related work|background|method|methodology|model|architecture|"
    r"experiments?|evaluation|results?|discussion|conclusion|limitations?)\b",
    re.IGNORECASE,
)
_RESULT_TERMS = (
    "result",
    "results",
    "experiment",
    "experiments",
    "evaluation",
    "bleu",
    "accuracy",
    "benchmark",
    "table",
    "ablation",
    "performance",
    "結果",
    "實驗",
    "实验",
    "評估",
    "评估",
)
_METHOD_TERMS = (
    "method",
    "model",
    "architecture",
    "attention",
    "algorithm",
    "framework",
    "diagram",
    "figure",
    "方法",
    "模型",
    "架構",
    "架构",
    "注意力",
)
_SECTION_LABELS = (
    "研究動機與目的",
    "研究方法",
    "實驗設計與過程",
    "實驗結果",
    "限制與結論",
    "論文重點圖解",
)
_SECTION_KEYWORDS = (
    (
        "研究動機與目的",
        ("motivation", "purpose", "objective", "introduction", "abstract", "background", "動機", "目的", "背景"),
    ),
    (
        "研究方法",
        (
            "method",
            "methodology",
            "model",
            "architecture",
            "framework",
            "mechanism",
            "approach",
            "方法",
            "模型",
            "架構",
            "机制",
            "機制",
        ),
    ),
    (
        "實驗設計與過程",
        (
            "experiment setup",
            "experimental setup",
            "design",
            "process",
            "simulation",
            "pipeline",
            "procedure",
            "dataset",
            "實驗設計",
            "過程",
            "流程",
            "資料集",
            "数据集",
        ),
    ),
    (
        "實驗結果",
        (
            "result",
            "results",
            "evaluation",
            "benchmark",
            "performance",
            "table",
            "chart",
            "accuracy",
            "結果",
            "評估",
            "评估",
            "效能",
            "表現",
        ),
    ),
    (
        "限制與結論",
        ("limitation", "limitations", "conclusion", "discussion", "future work", "限制", "結論", "讨论", "討論"),
    ),
)
_OVERVIEW_CAPTION_TERMS = (
    "pipeline",
    "framework",
    "architecture",
    "overview",
    "model architecture",
    "generative sequence",
    "method",
    "mechanism",
    "workflow",
    "流程",
    "架構",
    "框架",
    "方法",
    "機制",
)
_DATASET_CAPTION_TERMS = (
    "dataset",
    "composition",
    "breakdown",
    "statistics",
    "distribution",
    "distributions",
    "sample",
    "identity",
    "region",
    "資料集",
    "數據集",
    "组成",
    "組成",
    "分布",
)
_RESULT_CAPTION_TERMS = (
    "result",
    "results",
    "aggregate",
    "performance",
    "quality",
    "score",
    "accuracy",
    "benchmark",
    "tdq",
    "3h",
    "bleu",
    "評估",
    "結果",
    "表現",
)
_MAIN_RESULT_CAPTION_TERMS = (
    "main result",
    "main results",
    "performance",
    "predicting",
    "human judges",
    "overall quality",
    "rmse",
    "pearson",
    "correlation",
    "結果",
    "表現",
)
_ABLATION_CAPTION_TERMS = (
    "ablation",
    "w/o",
    "design decision",
    "rubric dimension",
    "消融",
)
_FALLBACK_SECTION_ORDER = {
    "研究方法": 0,
    "實驗設計與過程": 1,
    "實驗結果": 2,
    "論文重點圖解": 3,
}
_REQUIRED_FALLBACK_SECTIONS = ("研究方法", "實驗設計與過程", "實驗結果")
