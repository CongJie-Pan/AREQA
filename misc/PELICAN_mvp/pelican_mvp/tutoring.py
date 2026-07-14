"""Adaptive tutoring and the bounded fast/slow strategy selector."""

from __future__ import annotations

from .curriculum import NODES
from .models import ResponseCategory, TutoringStrategy


FAST_STRATEGIES = {
    ResponseCategory.CORRECT: TutoringStrategy.CONFIRMATION,
    ResponseCategory.INCORRECT: TutoringStrategy.CORRECTION,
    ResponseCategory.INABILITY: TutoringStrategy.EXPLANATION,
    ResponseCategory.DIFFICULTY: TutoringStrategy.EXPLANATION,
    ResponseCategory.OTHER: TutoringStrategy.OPEN_QUESTION,
}


def select_strategy(category: ResponseCategory, rounds: int) -> tuple[TutoringStrategy, str]:
    if rounds < 2:
        return FAST_STRATEGIES[category], "fast-thinking：依本回合回答類別選擇策略"
    candidates = _slow_candidates(category)
    scored = [(strategy, _simulation_score(strategy, category)) for strategy in candidates]
    strategy, score = max(scored, key=lambda item: item[1])
    return strategy, f"slow-thinking：模擬 {len(candidates)} 條策略路徑後選擇最高分 {score:.2f}"


def _slow_candidates(category: ResponseCategory) -> tuple[TutoringStrategy, TutoringStrategy]:
    if category in (ResponseCategory.INABILITY, ResponseCategory.DIFFICULTY):
        return (TutoringStrategy.DECOMPOSITION, TutoringStrategy.SIMPLIFICATION)
    if category is ResponseCategory.INCORRECT:
        return (TutoringStrategy.CORRECTION, TutoringStrategy.DECOMPOSITION)
    return (TutoringStrategy.OPEN_QUESTION, TutoringStrategy.CONFIRMATION)


def _simulation_score(strategy: TutoringStrategy, category: ResponseCategory, discount: float = 0.2) -> float:
    """A deterministic two-depth approximation of PELICAN's simulation tree."""
    success_probability = {
        (ResponseCategory.INABILITY, TutoringStrategy.DECOMPOSITION): 0.85,
        (ResponseCategory.INABILITY, TutoringStrategy.SIMPLIFICATION): 0.75,
        (ResponseCategory.DIFFICULTY, TutoringStrategy.DECOMPOSITION): 0.82,
        (ResponseCategory.DIFFICULTY, TutoringStrategy.SIMPLIFICATION): 0.78,
        (ResponseCategory.INCORRECT, TutoringStrategy.CORRECTION): 0.80,
        (ResponseCategory.INCORRECT, TutoringStrategy.DECOMPOSITION): 0.70,
    }.get((category, strategy), 0.60)
    return success_probability + (1.0 - discount)


def rule_tutor_message(strategy: TutoringStrategy, node_id: str, prompt: str) -> str:
    label = NODES[node_id].label
    if strategy is TutoringStrategy.CORRECTION:
        return f"你的答案還沒有符合「{label}」的條件。先回到題目的限制：{prompt}"
    if strategy is TutoringStrategy.DECOMPOSITION:
        if node_id == "absolute_value":
            return "我們拆成兩邊：-2 ≤ x - 1 ≤ 2。每一邊同時加 1 後，x 的範圍是什麼？"
        if node_id == "sqrt_integer":
            return "先找根號有意義的範圍，再把 √x ≤ 4 兩邊平方。最後記得 x 必須是整數；你得到哪個範圍？"
        return "先分別列出兩個集合的元素，再找兩邊都出現的元素。你先能列出其中一個集合嗎？"
    if strategy is TutoringStrategy.SIMPLIFICATION:
        return "先用較小的例子練習：{1, 2, 3} 和 {2, 3, 4} 的交集是什麼？再把同一個方法用回原題。"
    if strategy is TutoringStrategy.EXPLANATION:
        return f"目前要處理的是「{label}」。先不要急著求最後答案，請看這個條件：{prompt}"
    if strategy is TutoringStrategy.CONFIRMATION:
        return "這一步正確。接下來請把這個結果帶入下一個條件。"
    return f"請只聚焦「{label}」：{prompt}"

