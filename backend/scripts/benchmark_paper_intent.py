"""Compare Gemini and Jev with synthetic paper requests, without serving chat.

Run from the backend directory with OPENROUTER_API_KEY configured:
    python -m scripts.benchmark_paper_intent --repetitions 5
Run on Render to measure latency from the deployed network. Only the fixed
examples below are sent, and only case IDs, labels, status and timing are printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from collections import Counter
from time import perf_counter

import httpx
from openai import AsyncOpenAI

from config import settings
from services.query_policy.classifier import classify_response_policy_impl
from services.query_policy.models import AttachmentTask, default_response_policy
from services.query_policy.paper_intent import JEV_MODEL, classify_jev
from services.query_policy.pdf_guardrails import apply_pdf_auto_explain_guardrail

OPENROUTER_URL = "https://openrouter.ai/api"
GEMINI_LABELS = {
    AttachmentTask.PAPER_AUTO_EXPLAIN: "overview",
    AttachmentTask.PAPER_TARGETED_QA: "targeted",
    AttachmentTask.NONE: "other",
}
# Stable IDs allow an output row to be reproduced without logging the input.
CASES = (
    ("overview-explicit", "overview", "請幫我解釋這一篇論文", ""),
    ("overview-generic", "overview", "請分析我附加的檔案。", ""),
    ("overview-simple", "overview", "帮我解释这一篇论文", ""),
    ("overview-mixed", "overview", "可以幫我看一下這個 paper 嗎？", ""),
    ("overview-implicit", "overview", "可以帶我看一下作者在做什麼嗎？", ""),
    ("overview-first-time", "overview", "我第一次讀這個領域，你能幫我抓個全貌嗎？", ""),
    ("overview-beginner", "overview", "假設我完全沒背景，你會怎麼帶我讀完？", ""),
    ("overview-scope", "overview", "從研究動機到實驗結果都想了解，可以給我完整導讀嗎？", ""),
    ("targeted-method", "targeted", "好，繼續第二步的研究方法部分吧", "剛介紹了論文的研究動機。"),
    ("targeted-figure", "targeted", "解釋圖 2", ""),
    ("targeted-translation", "targeted", "只翻譯摘要，保留原文術語", ""),
    ("targeted-translation-short", "targeted", "摘要翻成英文就好", ""),
    ("targeted-page", "targeted", "Explain this paper on page 3 only.", ""),
    ("targeted-result", "targeted", "所以這個差距是怎麼算出來的？", "剛解釋論文主實驗的兩組正確率。"),
    ("targeted-continue", "targeted", "好，下一個", "剛約定接下來只講論文的消融實驗。"),
    ("targeted-citations", "targeted", "請幫我列出作者引用的兩個基準模型及其文獻", ""),
    ("other-unrelated", "other", "換個話題，晚餐要煮什麼？", "剛介紹了論文的研究背景。"),
    ("other-no-context", "other", "再看一下", ""),
    ("other-negation", "other", "不用解釋這一篇論文，我只是想問怎麼匯出對話。", ""),
)


async def classify_gemini(client: AsyncOpenAI, message: str, context: str) -> str:
    history = [{"role": "assistant", "content": context}] if context else []
    history.append({"role": "user", "content": message})
    policy = await classify_response_policy_impl(
        client, settings.model_policy_classifier, message, history,
        has_pdf_attachment=True, pdf_attachment_count=1,
    )
    return GEMINI_LABELS[policy.attachment_task]


async def measure(request):
    start = perf_counter()
    try:
        label = await asyncio.wait_for(request, timeout=8)
        status = "ok"
    except (TimeoutError, httpx.TimeoutException):
        label, status = None, "timeout"
    except Exception as exc:
        label, status = None, type(exc).__name__
    return {"prediction": label, "status": status, "ms": round((perf_counter() - start) * 1000, 1)}


def summarize(rows: list[dict], budget_ms: int) -> dict:
    durations = sorted(row["ms"] for row in rows if row["status"] == "ok")
    within = [row for row in rows if row["status"] == "ok" and row["ms"] <= budget_ms]
    overview = [row for row in rows if row["expected"] == "overview"]
    other = [row for row in rows if row["expected"] != "overview"]
    return {
        "attempts": len(rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "p50_ms": durations[math.ceil(len(durations) * 0.5) - 1] if durations else None,
        "p95_ms": durations[math.ceil(len(durations) * 0.95) - 1] if durations else None,
        "within_budget": len(within),
        "correct_within_budget": sum(row["expected"] == row["prediction"] for row in within),
        "overview_cases": len(overview),
        "overview_missed_within_budget": sum(
            row["prediction"] != "overview" or row["ms"] > budget_ms for row in overview
        ),
        "non_overview_cases": len(other),
        "false_overview_within_budget": sum(
            row["prediction"] == "overview" and row["ms"] <= budget_ms for row in other
        ),
    }


async def run(key: str, repetitions: int) -> dict:
    results = {"gemini": [], "jev": []}
    async with (
        AsyncOpenAI(api_key=key, base_url=f"{OPENROUTER_URL}/v1", max_retries=0) as gemini,
        AsyncOpenAI(api_key=key, base_url=f"{OPENROUTER_URL}/v1", max_retries=0) as jev,
    ):
        for repetition in range(1, repetitions + 1):
            for case_id, expected, message, context in CASES:
                local = apply_pdf_auto_explain_guardrail(
                    default_response_policy(), user_msg=message, has_pdf_attachment=True,
                )
                if local.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN:
                    continue
                comparison = await asyncio.gather(
                    measure(classify_gemini(gemini, message, context)),
                    measure(classify_jev(jev, message, context)),
                )
                for provider, row in zip(results, comparison, strict=True):
                    results[provider].append(dict(row, case_id=case_id, expected=expected, repetition=repetition))
    budget_ms = settings.policy_classifier_timeout_ms
    return {
        "budget_ms": budget_ms,
        "models": {"gemini": settings.model_policy_classifier, "jev": JEV_MODEL},
        "summary": {provider: summarize(rows, budget_ms) for provider, rows in results.items()},
        "rows": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, choices=range(1, 21), default=1)
    args = parser.parse_args()
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        parser.exit(2, "OPENROUTER_API_KEY must be set in the environment.\n")
    report = asyncio.run(run(key, args.repetitions))
    print(json.dumps(report, indent=2))
    if any(not summary["status_counts"].get("ok") for summary in report["summary"].values()):
        raise SystemExit(1)
