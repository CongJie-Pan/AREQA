"""The observable PELICAN state machine used by the CLI and tests."""

from __future__ import annotations

from pathlib import Path

from .curriculum import CURRICULUMS
from .diagnosis import apply_diagnostic_result, classify_response, diagnostic_for, next_diagnostic_node
from .llm import LlmAdapter, LlmUnavailable
from .models import (
    KnowledgeStatus,
    PlanSource,
    ResponseCategory,
    SessionState,
    TurnOutcome,
    TurnRecord,
    TutoringStrategy,
)
from typing import Any
from .state_store import StateStore
from .tutoring import rule_tutor_message, select_strategy
from .planner import LearningPlanner
from .edf_simulator import EdfSimulator
from .learning_memory import LearningMemorySimulator
from .curriculum import Curriculum
from .observability import log_event


class PelicanEngine:
    def __init__(self, data_dir: Path | str, learner_id: str = "demo_student", mode: str | None = None, curriculum_id: str | None = None):
        if mode is not None and mode not in {"rule", "llm"}:
            raise ValueError("mode must be 'rule' or 'llm'")
        self.store = StateStore(data_dir)
        # Session defaults to onboarding if no curriculum_id is provided
        self.state = self.store.load_or_create(learner_id, mode or "rule", curriculum_id)
        if mode is not None:
            self.state.mode = mode
            self.store.save(self.state)
        self.curriculum = self._resolve_curriculum()
        self.llm = LlmAdapter()
        self.planner = LearningPlanner(self.llm)
        self.edf = EdfSimulator()
        self.memory = LearningMemorySimulator()

    def _resolve_curriculum(self) -> Curriculum | None:
        if self.state.plan_source == PlanSource.FIXTURE and self.state.curriculum_id:
            return CURRICULUMS.get(self.state.curriculum_id)
        if self.state.learning_plan:
            plan = self.state.learning_plan
            return Curriculum(
                name=plan.topic,
                nodes={n.node_id: n for n in plan.nodes},
                diagnostics={d.node_id: d for d in plan.diagnostics},
                task_steps=plan.task_steps,
                answer_aliases={},
                tutor_hints={},
                completion_message=f"答對了！{plan.topic} 原題完成。"
            )
        return None

    def start(self) -> TurnOutcome:
        if self.state.phase == "onboarding":
            log_event("pelican_intake_received", learner_id=self.state.learner_id, phase="onboarding")
            return TurnOutcome(
                "歡迎！你想學什麼？（例如：我想了解二元搜尋法、我的 Python 字典一直用錯...）",
                None, None, None, (), "開始學習意圖收集"
            )
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

        if self.state.phase == "onboarding":
            return self._handle_onboarding(answer)
        if self.state.phase == "diagnosis":
            return self._handle_diagnostic(answer)
        return self._handle_tutoring(answer)

    def _handle_onboarding(self, answer: str) -> TurnOutcome:
        log_event("pelican_intake_received", learner_id=self.state.learner_id, phase="onboarding")
        plan = self.planner.create_plan(answer)
        self.state.learning_plan = plan
        self.state.phase = "diagnosis"
        self.store.save(self.state)
        self.curriculum = self._resolve_curriculum()
        log_event(
            "pelican_phase_transition",
            learner_id=self.state.learner_id,
            phase="diagnosis",
            plan_source=self.state.plan_source.value,
        )
        outcome = self._present_next_diagnostic()
        topic = plan.topic if plan else "這個主題"
        friendly_prefix = f"太好了，我們來一起學習「{topic}」吧！\n為了能更好地根據你目前的程度來安排教學，我會先問你一個前測問題。如果你還不知道答案，完全沒關係，直接告訴我「不知道」就好：\n\n"
        return TurnOutcome(
            friendly_prefix + outcome.message,
            outcome.node_id,
            outcome.category,
            outcome.strategy,
            outcome.state_changes,
            outcome.next_reason
        )

    def switch_mode(self, mode: str) -> TurnOutcome:
        if mode not in {"rule", "llm"}:
            raise ValueError("mode must be 'rule' or 'llm'")
        self.state.mode = mode
        self.store.save(self.state)
        availability = "已啟用 LLM" if mode == "llm" and self.llm.available else "規則模式將作為 fallback"
        return TurnOutcome(f"模式切換為 {mode}；{availability}。", self.state.current_node_id, None, None, (), "模式已更新")

    def reset(self, curriculum_id: str | None = None) -> TurnOutcome:
        self.state = self.store.reset(self.state.learner_id, self.state.mode, curriculum_id)
        self.curriculum = self._resolve_curriculum()
        return self.start()

    def tree_summary(self) -> str:
        if not self.curriculum:
            return "尚無知識狀態樹（收集意圖中）。"
        lines = ["知識狀態樹（綠=mastered，紅=not_mastered，灰=undiagnosed）"]
        for node in sorted(self.curriculum.nodes.values(), key=lambda item: item.priority, reverse=True):
            status = self.state.nodes[node.node_id].status.value
            prefix = "  " if node.prerequisites else ""
            lines.append(f"{prefix}- {node.label}: {status}")
        return "\n".join(lines)

    def tree_state(self) -> list[dict[str, Any]]:
        if not self.curriculum:
            return []
        return [
            {
                "id": node.node_id,
                "label": node.label,
                "status": self.state.nodes[node.node_id].status.value,
                "prerequisites": list(node.prerequisites),
            }
            for node in sorted(self.curriculum.nodes.values(), key=lambda item: item.priority, reverse=True)
        ]

    def history_summary(self) -> str:
        if not self.state.history:
            return "尚無互動紀錄。"
        return "\n".join(
            f"{index}. [{record.phase}] {record.node_id} -> {record.category} / {record.strategy or '-'}"
            for index, record in enumerate(self.state.history, start=1)
        )

    def _present_next_diagnostic(self) -> TurnOutcome:
        node_id = next_diagnostic_node(self.state, self.curriculum)
        if node_id is None:
            self.state.phase = "tutoring"
            step = self.curriculum.first_task_step()
            self._set_current_step(step)
            self.store.save(self.state)
            return self._present_current_step("診斷完成，依未掌握概念開始原題引導")
        question = diagnostic_for(node_id, self.curriculum)
        if self.state.mode == "llm":
            try:
                generated = self.llm.verified_diagnostic(self.curriculum.nodes[node_id].label)
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
        changes = apply_diagnostic_result(self.state, node_id, answer, category, self.curriculum)
        self._record(answer, category, None, changes)
        self._refresh_learning_context(answer, category)
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
            changes.append(f"{self.curriculum.nodes[node_id].label}: mastered（原題直接證據）")
            self._record(answer, category, TutoringStrategy.CONFIRMATION, changes)
            self._refresh_learning_context(answer, category)
            step = self.curriculum.next_task_step(step_id)
            if step is None:
                self.state.completed = True
                self.store.save(self.state)
                return TurnOutcome(
                    self.curriculum.completion_message,
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
            changes.append(f"{self.curriculum.nodes[node_id].label}: not_mastered（原題直接證據）")
        strategy, reason = select_strategy(category, rounds, self.state.edf_snapshot.pedagogical_strategy)
        message, source = self._tutor_message(strategy, node_id)
        self._record(answer, category, strategy, changes)
        self._refresh_learning_context(answer, category)
        self.state.current_prompt = message
        self.state.current_prompt_source = source
        self.store.save(self.state)
        return TurnOutcome(message, node_id, category, strategy, tuple(changes), reason)

    def _refresh_learning_context(self, answer: str, category: ResponseCategory) -> None:
        self.memory.record_direct_evidence(self.state, answer, category)
        self.state.edf_snapshot = self.edf.evaluate(self.state)
        log_event(
            "pelican_diagnosis_updated",
            learner_id=self.state.learner_id,
            category=category.value,
        )

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
        return classify_response(answer, self.state.current_expected_answer, self.curriculum)

    def _tutor_message(self, strategy: TutoringStrategy, node_id: str) -> tuple[str, str]:
        if self.state.mode == "llm":
            try:
                generated = self.llm.tutor_response(strategy, self.state.current_prompt, self.curriculum.nodes[node_id].label)
                if generated:
                    return generated, "llm"
            except LlmUnavailable:
                pass
        return rule_tutor_message(strategy, node_id, self.state.current_prompt, self.curriculum), "rule"

    def _show_answer(self) -> TurnOutcome:
        return TurnOutcome("提示答案：請直接輸入 expected answer 來通過測試。這是教師直接揭示，不會更新 mastery。", self.state.current_node_id, None, None, (), "教師揭示不等同學生掌握")

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
