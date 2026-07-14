"""The observable PELICAN state machine used by the CLI and tests."""

from __future__ import annotations

from pathlib import Path

from .curriculum import NODES, first_task_step, next_task_step
from .diagnosis import apply_diagnostic_result, classify_response, diagnostic_for, next_diagnostic_node
from .llm import LlmAdapter, LlmUnavailable
from .models import (
    KnowledgeStatus,
    ResponseCategory,
    SessionState,
    TurnOutcome,
    TurnRecord,
    TutoringStrategy,
)
from .state_store import StateStore
from .tutoring import rule_tutor_message, select_strategy


class PelicanEngine:
    def __init__(self, data_dir: Path | str, learner_id: str = "demo_student", mode: str = "rule"):
        if mode not in {"rule", "llm"}:
            raise ValueError("mode must be 'rule' or 'llm'")
        self.store = StateStore(data_dir)
        self.state = self.store.load_or_create(learner_id, mode)
        self.state.mode = mode
        self.llm = LlmAdapter()

    def start(self) -> TurnOutcome:
        if self.state.completed:
            return TurnOutcome("此學習者已完成原題；輸入 reset 可重新開始。", None, None, None, (), "已完成")
        if self.state.phase == "diagnosis":
            return self._present_next_diagnostic()
        return self._present_current_step("延續先前保存的學習路徑")

    def respond(self, answer: str) -> TurnOutcome:
        answer = answer.strip()
        if answer.lower() == "show answer":
            return self._show_answer()
        if not answer:
            return TurnOutcome("請輸入你的答案、困難點，或使用 CLI 指令。", self.state.current_node_id, None, None, (), "等待學生回應")
        if self.state.phase == "diagnosis":
            return self._handle_diagnostic(answer)
        return self._handle_tutoring(answer)

    def switch_mode(self, mode: str) -> TurnOutcome:
        if mode not in {"rule", "llm"}:
            raise ValueError("mode must be 'rule' or 'llm'")
        self.state.mode = mode
        self.store.save(self.state)
        availability = "已啟用 LLM" if mode == "llm" and self.llm.available else "規則模式將作為 fallback"
        return TurnOutcome(f"模式切換為 {mode}；{availability}。", self.state.current_node_id, None, None, (), "模式已更新")

    def reset(self) -> TurnOutcome:
        self.state = self.store.reset(self.state.learner_id, self.state.mode)
        return self.start()

    def tree_summary(self) -> str:
        lines = ["知識狀態樹（綠=mastered，紅=not_mastered，灰=undiagnosed）"]
        for node in sorted(NODES.values(), key=lambda item: item.priority, reverse=True):
            status = self.state.nodes[node.node_id].status.value
            prefix = "  " if node.prerequisites else ""
            lines.append(f"{prefix}- {node.label}: {status}")
        return "\n".join(lines)

    def history_summary(self) -> str:
        if not self.state.history:
            return "尚無互動紀錄。"
        return "\n".join(
            f"{index}. [{record.phase}] {record.node_id} -> {record.category} / {record.strategy or '-'}"
            for index, record in enumerate(self.state.history, start=1)
        )

    def _present_next_diagnostic(self) -> TurnOutcome:
        node_id = next_diagnostic_node(self.state)
        if node_id is None:
            self.state.phase = "tutoring"
            step = first_task_step()
            self._set_current_step(step)
            self.store.save(self.state)
            return self._present_current_step("診斷完成，依未掌握概念開始原題引導")
        question = diagnostic_for(node_id)
        if self.state.mode == "llm":
            try:
                generated = self.llm.verified_diagnostic(NODES[node_id].label)
                if generated:
                    question = generated.__class__(node_id, generated.prompt, generated.expected_answer, generated.source)
            except LlmUnavailable:
                pass
        self.state.current_node_id = node_id
        self.state.current_prompt = question.prompt
        self.state.current_expected_answer = question.expected_answer
        self.state.current_prompt_source = question.source
        self.store.save(self.state)
        return TurnOutcome(question.prompt, node_id, None, None, (), "successor-first：先診斷尚未確認的葉節點")

    def _handle_diagnostic(self, answer: str) -> TurnOutcome:
        node_id = self._require_current_node()
        category = self._classify(answer)
        changes = apply_diagnostic_result(self.state, node_id, answer, category)
        self._record(answer, category, None, changes)
        self.store.save(self.state)
        next_outcome = self._present_next_diagnostic()
        message = f"診斷結果：{category.value}。\n" + next_outcome.message
        return TurnOutcome(message, next_outcome.node_id, category, None, tuple(changes), next_outcome.next_reason)

    def _handle_tutoring(self, answer: str) -> TurnOutcome:
        node_id = self._require_current_node()
        step_id = self.state.current_step_id or ""
        category = self._classify(answer)
        changes: list[str] = []
        if category is ResponseCategory.CORRECT:
            self.state.nodes[node_id].update(
                KnowledgeStatus.MASTERED,
                evidence=self._evidence(answer, category),
            )
            changes.append(f"{NODES[node_id].label}: mastered（原題直接證據）")
            self._record(answer, category, TutoringStrategy.CONFIRMATION, changes)
            step = next_task_step(step_id)
            if step is None:
                self.state.completed = True
                self.store.save(self.state)
                return TurnOutcome(
                    "答對了：A ∩ B = {0, 1, 2, 3}。原題完成。",
                    node_id,
                    category,
                    TutoringStrategy.CONFIRMATION,
                    tuple(changes),
                    "全部子任務完成",
                )
            self._set_current_step(step)
            self.store.save(self.state)
            next_outcome = self._present_current_step("前一子任務已完成，解鎖下一步")
            return TurnOutcome(next_outcome.message, next_outcome.node_id, category, TutoringStrategy.CONFIRMATION, tuple(changes), next_outcome.next_reason)
        rounds = self.state.step_rounds.get(step_id, 0) + 1
        self.state.step_rounds[step_id] = rounds
        if category in (ResponseCategory.INCORRECT, ResponseCategory.INABILITY):
            self.state.nodes[node_id].update(
                KnowledgeStatus.NOT_MASTERED,
                evidence=self._evidence(answer, category),
            )
            changes.append(f"{NODES[node_id].label}: not_mastered（原題直接證據）")
        strategy, reason = select_strategy(category, rounds)
        message = self._tutor_message(strategy, node_id)
        self._record(answer, category, strategy, changes)
        self.store.save(self.state)
        return TurnOutcome(message, node_id, category, strategy, tuple(changes), reason)

    def _present_current_step(self, reason: str) -> TurnOutcome:
        return TurnOutcome(self.state.current_prompt, self.state.current_node_id, None, None, (), reason)

    def _set_current_step(self, step: dict[str, str]) -> None:
        self.state.current_step_id = step["step_id"]
        self.state.current_node_id = step["node_id"]
        self.state.current_prompt = step["prompt"]
        self.state.current_expected_answer = step["expected"]
        self.state.current_prompt_source = "rule"

    def _classify(self, answer: str) -> ResponseCategory:
        if self.state.mode == "llm" and self.state.current_prompt_source == "llm":
            try:
                category = self.llm.classify(
                    self.state.current_prompt, self.state.current_expected_answer, answer
                )
                if category:
                    return category
            except LlmUnavailable:
                pass
        return classify_response(answer, self.state.current_expected_answer)

    def _tutor_message(self, strategy: TutoringStrategy, node_id: str) -> str:
        if self.state.mode == "llm":
            try:
                generated = self.llm.tutor_response(strategy, self.state.current_prompt, NODES[node_id].label)
                if generated:
                    return generated
            except LlmUnavailable:
                pass
        return rule_tutor_message(strategy, node_id, self.state.current_prompt)

    def _show_answer(self) -> TurnOutcome:
        answers = {
            "solve_a": "提示答案：A = [-1, 3]。這是教師直接揭示，不會更新 mastery。",
            "solve_b": "提示答案：B = {0, 1, ..., 16}。這是教師直接揭示，不會更新 mastery。",
            "intersect": "提示答案：A ∩ B = {0, 1, 2, 3}。這是教師直接揭示，不會更新 mastery。",
        }
        return TurnOutcome(answers.get(self.state.current_step_id or "", "診斷題沒有直接答案指令。"), self.state.current_node_id, None, None, (), "教師揭示不等同學生掌握")

    def _record(self, answer: str, category: ResponseCategory, strategy: TutoringStrategy | None, changes: list[str]) -> None:
        self.state.history.append(
            TurnRecord(
                prompt=self.state.current_prompt,
                response=answer,
                phase=self.state.phase,
                node_id=self._require_current_node(),
                category=category.value,
                strategy=strategy.value if strategy else None,
                state_changes=changes,
            )
        )

    def _require_current_node(self) -> str:
        if not self.state.current_node_id:
            raise RuntimeError("No current knowledge node is selected")
        return self.state.current_node_id

    @staticmethod
    def _evidence(answer: str, category: ResponseCategory):
        from .models import Evidence

        return Evidence(response=answer, category=category.value, direct=True)
