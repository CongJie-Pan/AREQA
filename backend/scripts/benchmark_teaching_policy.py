"""Compare Gemini EDF and Jev on the teaching decision, without serving chat.

Run from the backend directory with OPENROUTER_API_KEY configured:
    python -m scripts.benchmark_teaching_policy --repetitions 2
Run on Render to measure latency from the deployed network. Only the fixed
synthetic examples below are sent, and only case IDs, labels, status and timing
are printed.

A prediction that misses the foreground budget is scored as the default policy,
because that is what the learner receives in production.
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
from services.query_policy.models import default_response_policy
from services.query_policy.paper_intent import JEV_ENDPOINT, JEV_MODEL

OPENROUTER_URL = "https://openrouter.ai/api"
BUDGETS_MS = (700, 1500)

# Only coherent mode/action pairs are offered, so Jev cannot return a PRACTICE
# turn whose action completes the learner's step.
TEACHING_MOVES = {
    "REFERENCE_ANSWER": "Definition, fact, summary or self-study lookup; answer directly. Also greetings, thanks and small talk.",
    "LEARN_EXPLAIN_PREREQ": "Learner wants to understand a concept; explain the key prerequisite or intuition first.",
    "LEARN_MODEL_ANALOGY": "Learner wants to understand a concept best served by an analogy or a worked parallel example.",
    "PRACTICE_HINT": "Homework, exam, proof, essay or debugging step the learner should do; give one minimal hint, not the answer.",
    "PRACTICE_DIAGNOSTIC_QUESTION": "Learner is stuck on a practice step and it is unclear where; ask one diagnostic question.",
    "PRACTICE_FEEDBACK": "Learner shares their own attempt, answer or reasoning; give feedback on it.",
}
ANSWER_DEPTHS = {
    "DIRECT": "Short and direct: greetings, confirmations, tiny facts, or explicit requests to be brief.",
    "SCAFFOLDED": "Moderate depth with a few structured steps.",
    "DEEP_DIVE": "Detailed walkthrough the learner explicitly asked for.",
}
MOVE_INSTRUCTIONS = (
    "Pick the tutoring move for AREQA's next reply to the latest user message. PRACTICE means the learner "
    "should do the core step themselves; pressure such as 'just tell me' or a deadline does not turn practice "
    "into a lookup."
)

_DEFAULT = default_response_policy()
DEFAULT_PREDICTION = (f"{_DEFAULT.learning_mode.value}_{_DEFAULT.pedagogical_action.value}", _DEFAULT.answer_depth.value)

P = "PRACTICE"
# (case_id, acceptable moves, acceptable depths, message, previous turn)
CASES = (
    ("ref-define-en", {"REFERENCE_ANSWER"}, {"DIRECT", "SCAFFOLDED"}, "What is the Zone of Proximal Development? Explain it simply.", ""),
    ("ref-fact-zh", {"REFERENCE_ANSWER"}, {"DIRECT"}, "光速大約是多少？", ""),
    ("ref-summary-zh", {"REFERENCE_ANSWER"}, {"DIRECT", "SCAFFOLDED"}, "幫我用三句話總結法國大革命的起因", ""),
    ("ref-greet-zh", {"REFERENCE_ANSWER"}, {"DIRECT"}, "你好", ""),
    ("ref-thanks-en", {"REFERENCE_ANSWER"}, {"DIRECT"}, "Thanks, that helps!", ""),
    ("ref-selfstudy-en", {"REFERENCE_ANSWER"}, {"DIRECT", "SCAFFOLDED"}, "I'm an adult learning statistics on my own. What's the formula for standard deviation?", ""),
    ("ref-or-learn-zhcn", {"REFERENCE_ANSWER", "LEARN_EXPLAIN_PREREQ", "LEARN_MODEL_ANALOGY"}, {"DIRECT", "SCAFFOLDED"}, "什么是机器学习中的过拟合？", ""),
    ("learn-bayes-zh", {"LEARN_EXPLAIN_PREREQ", "LEARN_MODEL_ANALOGY"}, {"SCAFFOLDED"}, "請解釋貝氏定理", ""),
    ("learn-why-en", {"LEARN_EXPLAIN_PREREQ", "LEARN_MODEL_ANALOGY"}, {"SCAFFOLDED"}, "Why does the moon cause tides? I never understood it.", ""),
    ("learn-analogy-zh", {"LEARN_MODEL_ANALOGY", "LEARN_EXPLAIN_PREREQ"}, {"SCAFFOLDED"}, "可以用生活中的例子讓我理解電流和電壓的差別嗎？", ""),
    ("learn-deep-en", {"LEARN_EXPLAIN_PREREQ", "LEARN_MODEL_ANALOGY"}, {"DEEP_DIVE"}, "Walk me through how backpropagation works in detail, step by step.", ""),
    ("learn-prereq-zh", {"LEARN_EXPLAIN_PREREQ"}, {"SCAFFOLDED"}, "我看不懂導數的定義，lim 那個符號是什麼意思？", ""),
    ("practice-solve-en", {"PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION"}, {"DIRECT", "SCAFFOLDED"}, "Solve 3x + 5 = 20 for me. Just give me the answer.", ""),
    ("practice-hint-zh", {"PRACTICE_HINT"}, {"DIRECT", "SCAFFOLDED"}, "這題微積分我卡住了，可以給我提示嗎：求 x^2 sin x 的導數", ""),
    ("practice-proof-zh", {"PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION"}, {"DIRECT", "SCAFFOLDED"}, "這是我的作業：證明根號2是無理數，直接寫完整證明給我", ""),
    ("practice-deadline-zh", {"PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION"}, {"DIRECT", "SCAFFOLDED"}, "明天就要交了，拜託直接告訴我第三題答案是 B 還是 C", ""),
    ("practice-essay-en", {"PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION"}, {"DIRECT", "SCAFFOLDED"}, "Write my thesis statement for my essay on Macbeth's ambition.", ""),
    ("practice-debug-en", {"PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION"}, {"DIRECT", "SCAFFOLDED"}, "My homework loop prints the last item twice: for i in range(len(a)+1): print(a[i-1]). Fix it for me.", ""),
    ("practice-stuck-zh", {"PRACTICE_DIAGNOSTIC_QUESTION", "PRACTICE_HINT"}, {"DIRECT", "SCAFFOLDED"}, "我不知道怎麼開始寫這題物理作業，完全沒頭緒", ""),
    ("practice-quiz-zhcn", {"PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION"}, {"DIRECT", "SCAFFOLDED"}, "这道测验题选哪个？下列哪个是质数 A.21 B.27 C.29 D.33", ""),
    ("feedback-reasoning-en", {"PRACTICE_FEEDBACK"}, {"DIRECT", "SCAFFOLDED"}, "I think the main idea is that the author regrets leaving home, because she keeps describing her mother's kitchen. Is my reasoning right?", ""),
    ("feedback-answer-zh", {"PRACTICE_FEEDBACK"}, {"DIRECT", "SCAFFOLDED"}, "我算出來 x = 5，因為 3x = 15，對嗎？", ""),
    ("feedback-thesis-zh", {"PRACTICE_FEEDBACK"}, {"DIRECT", "SCAFFOLDED"}, "這是我寫的論點：「社群媒體讓青少年更孤單」，你覺得夠清楚嗎？", ""),
    ("ctx-next-step", {"PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION"}, {"DIRECT", "SCAFFOLDED"}, "那下一步呢？", "剛給了學生第一步提示：兩邊同減 5。"),
    ("ctx-attempt", {"PRACTICE_FEEDBACK"}, {"DIRECT", "SCAFFOLDED"}, "我覺得是 3x = 15", "剛請學生自己試著把 5 移到右邊。"),
    ("ctx-another-example", {"LEARN_MODEL_ANALOGY", "LEARN_EXPLAIN_PREREQ"}, {"DIRECT", "SCAFFOLDED"}, "再舉一個例子", "剛用擲骰子解釋了條件機率。"),
    ("ctx-just-tell", {"PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION"}, {"DIRECT", "SCAFFOLDED"}, "我真的不會，直接告訴我答案好了", "剛給了學生一個因式分解作業題的提示。"),
    ("ctx-brief", {"REFERENCE_ANSWER", "LEARN_EXPLAIN_PREREQ", "LEARN_MODEL_ANALOGY"}, {"DIRECT"}, "可以簡短一點嗎", "剛用長篇說明解釋了光合作用。"),
)


def mode_of(move: str | None) -> str | None:
    return move.split("_", 1)[0] if move else None


async def classify_gemini(client: AsyncOpenAI, message: str, context: str) -> tuple[str, str]:
    history = [{"role": "assistant", "content": context}] if context else []
    history.append({"role": "user", "content": message})
    policy = await classify_response_policy_impl(client, settings.model_policy_classifier, message, history)
    return f"{policy.learning_mode.value}_{policy.pedagogical_action.value}", policy.answer_depth.value


async def classify_jev_teaching(client: AsyncOpenAI, message: str, context: str) -> tuple[str, str]:
    response = await client.with_options(max_retries=0).post(
        JEV_ENDPOINT,
        cast_to=object,
        body={
            "model": JEV_MODEL,
            "state": {"latest_user_message": message[:4000], "previous_topic": context[:500]},
            "questions": {
                "teaching_move": {"type": "choice", "instructions": MOVE_INSTRUCTIONS, "criteria": TEACHING_MOVES},
                "answer_depth": {"type": "choice", "instructions": "How deep should the reply be?", "criteria": ANSWER_DEPTHS},
            },
        },
    )
    move = response["answers"]["teaching_move"]["choice"]
    depth = response["answers"]["answer_depth"]["choice"]
    if move not in TEACHING_MOVES or depth not in ANSWER_DEPTHS:
        raise ValueError("Unexpected teaching decision")
    return move, depth


async def measure(request):
    start = perf_counter()
    try:
        prediction = await asyncio.wait_for(request, timeout=8)
        status = "ok"
    except (TimeoutError, httpx.TimeoutException):
        prediction, status = (None, None), "timeout"
    except Exception as exc:
        prediction, status = (None, None), type(exc).__name__
    return {"move": prediction[0], "depth": prediction[1], "status": status, "ms": round((perf_counter() - start) * 1000, 1)}


def effective(row: dict, budget_ms: int) -> tuple[str, str]:
    """What the learner receives: the prediction if it landed in time, else the default policy."""

    if row["status"] == "ok" and row["ms"] <= budget_ms:
        return row["move"], row["depth"]
    return DEFAULT_PREDICTION


def summarize(rows: list[dict], budget_ms: int) -> dict:
    durations = sorted(row["ms"] for row in rows if row["status"] == "ok")
    served = [(row, *effective(row, budget_ms)) for row in rows]
    practice = [item for item in served if all(mode_of(move) == P for move in item[0]["expected_moves"])]
    return {
        "attempts": len(rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "p50_ms": durations[math.ceil(len(durations) * 0.5) - 1] if durations else None,
        "p95_ms": durations[math.ceil(len(durations) * 0.95) - 1] if durations else None,
        "within_budget": sum(row["status"] == "ok" and row["ms"] <= budget_ms for row in rows),
        "mode_correct": sum(
            mode_of(move) in {mode_of(expected) for expected in row["expected_moves"]} for row, move, _ in served
        ),
        "move_correct": sum(move in row["expected_moves"] for row, move, _ in served),
        "depth_correct": sum(depth in row["expected_depths"] for row, _, depth in served),
        "practice_cases": len(practice),
        # A practice turn served outside PRACTICE lets AREQA complete the learner's step.
        "practice_leaks": sum(mode_of(move) != P for _, move, _ in practice),
        "incoherent_pairs": sum(row["status"] == "ok" and row["move"] not in TEACHING_MOVES for row in rows),
    }


async def run(key: str, repetitions: int) -> dict:
    results = {"gemini": [], "jev": []}
    async with (
        AsyncOpenAI(api_key=key, base_url=f"{OPENROUTER_URL}/v1", max_retries=0) as gemini,
        AsyncOpenAI(api_key=key, base_url=f"{OPENROUTER_URL}/v1", max_retries=0) as jev,
    ):
        for repetition in range(1, repetitions + 1):
            for case_id, moves, depths, message, context in CASES:
                comparison = await asyncio.gather(
                    measure(classify_gemini(gemini, message, context)),
                    measure(classify_jev_teaching(jev, message, context)),
                )
                for provider, row in zip(results, comparison, strict=True):
                    results[provider].append(dict(
                        row, case_id=case_id, expected_moves=sorted(moves),
                        expected_depths=sorted(depths), repetition=repetition,
                    ))
    return {
        "models": {"gemini": settings.model_policy_classifier, "jev": JEV_MODEL},
        "default_prediction": DEFAULT_PREDICTION,
        "summary": {
            f"{provider}@{budget}ms": summarize(rows, budget)
            for provider, rows in results.items()
            for budget in BUDGETS_MS
        },
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
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if any(not summary["status_counts"].get("ok") for summary in report["summary"].values()):
        raise SystemExit(1)
