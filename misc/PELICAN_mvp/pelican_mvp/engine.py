"""The observable PELICAN state machine used by the CLI and tests."""

from __future__ import annotations

from pathlib import Path

from .curriculum import CURRICULUMS
from .diagnosis import apply_diagnostic_result, classify_response, diagnostic_for, next_diagnostic_node, remediation_signal
from .domain_skill import DomainCategory
from .llm import LlmAdapter, LlmUnavailable
from .models import (
    ActivityEvent,
    KnowledgeStatus,
    LearnerIntakeProfile,
    LearningIntent,
    PlanSource,
    ResponseCategory,
    SessionState,
    TurnOutcome,
    TurnRecord,
    TutoringStrategy,
)
from typing import Any
from .state_store import StateStore
from .tutoring import rule_tutor_message, select_strategy, strategy_for_remediation_signal
from .planner import LearningPlanner
from .edf_simulator import EdfSimulator
from .learning_memory import LearningMemorySimulator
from .curriculum import Curriculum
from .observability import log_event


MAX_ACTIVITY_LOG = 16


class PelicanEngine:
    """Coordinate intake, planning, diagnosis, tutoring, EDF, and memory state.

    Default generated sessions use calibration-first onboarding before a skill is
    compiled into a PELICAN knowledge tree. Explicit fixture sessions keep their
    legacy direct-to-diagnosis behavior for regression compatibility.
    """

    def __init__(self, data_dir: Path | str, learner_id: str = "demo_student", mode: str | None = None, curriculum_id: str | None = None):
        """Load or create one learner session with isolated local persistence."""
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
        """Return the active fixture or compiled generated curriculum."""
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
        """Resume the current phase without consuming learner evidence."""
        if self.state.phase == "onboarding":
            log_event("pelican_intake_progress", learner_id=self.state.learner_id, phase="onboarding", intake_decision="topic")
            if self.state.intake_profile.intake_turns == 1:
                question, _source = self._next_intake_question("goal")
                return TurnOutcome(
                    question,
                    None,
                    None,
                    None,
                    (),
                    "恢復學習目標收集",
                )
            if self.state.intake_profile.intake_turns == 2:
                question, _source = self._next_intake_question("level")
                return TurnOutcome(
                    question,
                    None,
                    None,
                    None,
                    (),
                    "恢復程度與先備經驗收集",
                )
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
        """Advance the state machine from one learner response."""
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
        """Collect topic, intent, and level before compiling a generated plan.

        The transition order is deliberately fixed: topic first, goal/intent
        second, level third. This prevents a broad subject request from being
        treated as evidence of mastery or from immediately triggering an
        implementation-level diagnostic.
        """
        intake = self.state.intake_profile
        if intake.intake_turns == 0:
            from .domain_catalog import resolve_domain_category

            resolution = resolve_domain_category(answer)
            self._record_activity("intake_topic", "接收學習主題", detail="topic_received")
            self._record_activity(
                "domain_resolved",
                "判斷學習領域",
                detail=f"{resolution.category.value}:{resolution.reason_code}",
            )
            self.state.intake_profile = LearnerIntakeProfile(
                topic=answer,
                goal_summary=f"學習 {answer}",
                intent=LearningIntent.UNKNOWN,
                level_hint="unknown",
                domain_category=resolution.category.value,
                model_route=resolution.route_slug,
                intake_turns=1,
            )
            self.store.save(self.state)
            log_event(
                "pelican_intake_progress",
                learner_id=self.state.learner_id,
                phase="onboarding",
                domain_category=resolution.category.value,
                route=resolution.route_slug,
                intake_decision="goal",
                reason_code=resolution.reason_code,
            )
            legal_note = "我可以協助法律知識教育，但不能提供個案法律諮詢。\n" if "法律" in answer else ""
            question, _source = self._next_intake_question("goal")
            return TurnOutcome(
                legal_note + question,
                None,
                None,
                None,
                (),
                "收集學習目標與意圖",
            )
        if intake.intake_turns == 1:
            intent = _infer_learning_intent(answer)
            self._record_activity("intent_detected", "判斷學習方向", detail=intent.value)
            self.state.intake_profile = LearnerIntakeProfile(
                topic=intake.topic,
                goal_summary=answer,
                intent=intent,
                level_hint=intake.level_hint,
                domain_category=intake.domain_category,
                model_route=intake.model_route,
                intake_turns=2,
            )
            self.store.save(self.state)
            log_event(
                "pelican_intake_progress",
                learner_id=self.state.learner_id,
                phase="onboarding",
                domain_category=intake.domain_category,
                route=intake.model_route,
                intake_decision="level",
            )
            question, _source = self._next_intake_question("level")
            return TurnOutcome(
                question,
                None,
                None,
                None,
                (),
                "收集程度與先備經驗",
            )

        level_hint = _infer_level_hint(answer)
        self._record_activity("level_detected", "判斷目前程度", detail=level_hint)
        profile = LearnerIntakeProfile(
            topic=intake.topic,
            goal_summary=intake.goal_summary,
            intent=intake.intent,
            level_hint=level_hint,
            domain_category=intake.domain_category,
            model_route=intake.model_route,
            intake_turns=3,
        )
        plan = self.planner.create_plan_for_profile(profile)
        self.state.learning_plan = plan
        if plan.skill_id:
            self._record_activity("skill_loaded", "載入領域 Skill", detail=plan.skill_id)
            self._record_activity("skill_validated", "驗證 Skill 規則", detail=plan.skill_lifecycle or "validated")
        self._record_activity("plan_compiled", "編譯學習路徑", detail=f"{len(plan.nodes)} nodes")
        self.state.intake_profile = LearnerIntakeProfile(
            topic=profile.topic,
            goal_summary=profile.goal_summary,
            intent=profile.intent,
            level_hint=profile.level_hint,
            domain_category=plan.domain_category or profile.domain_category,
            skill_id=plan.skill_id,
            skill_version=plan.skill_version,
            skill_lifecycle=plan.skill_lifecycle,
            model_route=plan.model_route or profile.model_route,
            intake_turns=3,
        )
        self.state.phase = "diagnosis"
        self.store.save(self.state)
        self.curriculum = self._resolve_curriculum()
        log_event(
            "pelican_phase_transition",
            learner_id=self.state.learner_id,
            phase="diagnosis",
            plan_source=self.state.plan_source.value,
            domain_category=plan.domain_category,
            route=plan.model_route,
            skill_id=plan.skill_id,
        )
        outcome = self._present_next_diagnostic()
        topic = plan.topic if plan else "這個主題"
        friendly_prefix = f"太好了，我們來一起學習「{topic}」吧！\n我會先用一個低負荷的校準問題確認起點。如果不知道，直接說不知道就好：\n\n"
        return TurnOutcome(
            friendly_prefix + outcome.message,
            outcome.node_id,
            outcome.category,
            outcome.strategy,
            outcome.state_changes,
            outcome.next_reason
        )

    def _next_intake_question(self, stage: str) -> tuple[str, str]:
        """Return one domain-aware intake question and its safe source code."""
        intake = self.state.intake_profile
        category = _domain_category_from_value(intake.domain_category)
        if self.state.mode == "llm" and self.llm.available:
            try:
                generated = self.llm.intake_question(
                    topic=intake.topic,
                    domain_category=category,
                    stage=stage,
                )
                if generated:
                    self._record_activity("intake_question_generated", "生成前置校準問題", detail=f"llm:{stage}")
                    log_event(
                        "pelican_intake_question_selected",
                        learner_id=self.state.learner_id,
                        phase=self.state.phase,
                        domain_category=category.value,
                        route=intake.model_route,
                        intake_decision=stage,
                        intake_source="llm",
                        reason_code="llm_generated",
                    )
                    self.store.save(self.state)
                    return generated, "llm"
            except LlmUnavailable:
                log_event(
                    "pelican_intake_question_fallback",
                    learner_id=self.state.learner_id,
                    phase=self.state.phase,
                    domain_category=category.value,
                    route=intake.model_route,
                    intake_decision=stage,
                    intake_source="llm_failed",
                    reason_code="llm_unavailable",
                )
        fallback = _rule_intake_question(category, stage)
        self._record_activity("intake_question_generated", "產生前置校準問題", detail=f"rule:{category.value}:{stage}")
        log_event(
            "pelican_intake_question_selected",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            domain_category=category.value,
            route=intake.model_route,
            intake_decision=stage,
            intake_source=f"rule_{category.value}",
            reason_code="rule_fallback",
        )
        self.store.save(self.state)
        return fallback, "rule"

    def switch_mode(self, mode: str) -> TurnOutcome:
        """Switch between rule and optional LLM modes for this local session."""
        if mode not in {"rule", "llm"}:
            raise ValueError("mode must be 'rule' or 'llm'")
        self.state.mode = mode
        self.store.save(self.state)
        availability = "已啟用 LLM" if mode == "llm" and self.llm.available else "規則模式將作為 fallback"
        return TurnOutcome(f"模式切換為 {mode}；{availability}。", self.state.current_node_id, None, None, (), "模式已更新")

    def reset(self, curriculum_id: str | None = None) -> TurnOutcome:
        """Reset the current learner into onboarding or an explicit fixture."""
        self.state = self.store.reset(self.state.learner_id, self.state.mode, curriculum_id)
        self.curriculum = self._resolve_curriculum()
        return self.start()

    def tree_summary(self) -> str:
        """Render a compact CLI-oriented knowledge-state summary."""
        if not self.curriculum:
            return "尚無知識狀態樹（收集意圖中）。"
        lines = ["知識狀態樹（綠=mastered，紅=not_mastered，灰=undiagnosed）"]
        for node in sorted(self.curriculum.nodes.values(), key=lambda item: item.priority, reverse=True):
            status = self.state.nodes[node.node_id].status.value
            prefix = "  " if node.prerequisites else ""
            lines.append(f"{prefix}- {node.label}: {status}")
        return "\n".join(lines)

    def tree_state(self) -> list[dict[str, Any]]:
        """Return API-safe tree metadata without prompts or learner answers."""
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
        """Render a compact CLI-oriented turn history summary."""
        if not self.state.history:
            return "尚無互動紀錄。"
        return "\n".join(
            f"{index}. [{record.phase}] {record.node_id} -> {record.category} / {record.strategy or '-'}"
            for index, record in enumerate(self.state.history, start=1)
        )

    def _present_next_diagnostic(self) -> TurnOutcome:
        """Present the next successor-first diagnostic for the active curriculum."""
        node_id = next_diagnostic_node(self.state, self.curriculum)
        if node_id is None:
            self.state.phase = "tutoring"
            step = self.curriculum.first_task_step()
            self._set_current_step(step)
            self._record_activity("tutoring_started", "進入教學引導", detail=step["node_id"])
            self.store.save(self.state)
            return self._present_current_step("診斷完成，依未掌握概念開始原題引導")
        question = diagnostic_for(node_id, self.curriculum)
        skill_question_locked = self._uses_generated_skill_plan() and question.source == "skill"
        if self.state.mode == "llm" and not skill_question_locked:
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
        self._record_activity("diagnostic_selected", "選擇診斷概念", detail=f"{question.source}:{node_id}")
        log_event(
            "pelican_diagnostic_source_selected",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            domain_category=self.state.learning_plan.domain_category if self.state.learning_plan else None,
            skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
            diagnostic_source=question.source,
            node_id=node_id,
            reason_code="skill_locked" if skill_question_locked else "mode_selected",
        )
        self.store.save(self.state)
        return TurnOutcome(question.prompt, node_id, None, None, (), "successor-first：先診斷尚未確認的葉節點")

    def _handle_diagnostic(self, answer: str) -> TurnOutcome:
        """Handle a diagnostic answer with generated-skill remediation precedence."""
        node_id = self._require_current_node()
        signal = remediation_signal(answer)
        # Remediation signals are control evidence, not mastery evidence; handle
        # them before normal answer classification can advance successor-first.
        if self.state.plan_source is PlanSource.GENERATED and signal in {"too_detailed", "too_difficult"}:
            return self._handle_scope_mismatch(answer, signal)
        if self.state.plan_source is PlanSource.GENERATED and signal == "too_easy":
            return self._handle_acceleration_request(answer)
        category = self._classify(answer)
        self._record_activity("response_classified", "分類學習者回應", detail=category.value)
        if self.state.plan_source is PlanSource.GENERATED and category is ResponseCategory.INABILITY:
            return self._handle_scaffold_request(answer, category)
        changes = apply_diagnostic_result(self.state, node_id, answer, category, self.curriculum)
        self._record_activity("evidence_applied", "更新概念掌握狀態", detail=node_id)
        self._record(answer, category, None, changes)
        self._refresh_learning_context(answer, category)
        if self._uses_generated_skill_plan() and category in (ResponseCategory.INCORRECT, ResponseCategory.DIFFICULTY):
            return self._remediate_current_skill_diagnostic(answer, category, changes)
        self.store.save(self.state)
        next_outcome = self._present_next_diagnostic()
        
        category_msg_map = {
            ResponseCategory.CORRECT: "答對了，看來你對這個概念有基本掌握！",
            ResponseCategory.INCORRECT: "這個答案不太對喔，我們晚點再詳細探討。",
            ResponseCategory.DIFFICULTY: "這部分確實比較進階，不用擔心。",
            ResponseCategory.INABILITY: "沒關係，學習本來就是一步步來的。",
            ResponseCategory.OTHER: "收到你的回覆了。"
        }
        prefix = category_msg_map.get(category, f"診斷結果：{category.value}。")
        message = f"{prefix}\n\n{next_outcome.message}"
        
        return TurnOutcome(message, next_outcome.node_id, category, None, tuple(changes), next_outcome.next_reason)

    def _uses_generated_skill_plan(self) -> bool:
        """Return whether this session is backed by a validated generated skill."""
        return self.state.plan_source is PlanSource.GENERATED and bool(
            self.state.learning_plan and self.state.learning_plan.skill_id
        )

    def _remediate_current_skill_diagnostic(
        self,
        answer: str,
        category: ResponseCategory,
        changes: list[str],
    ) -> TurnOutcome:
        """Keep generated-skill learners on the current concept after missed evidence."""
        node_id = self._require_current_node()
        label = self.curriculum.nodes[node_id].label
        strategy = (
            TutoringStrategy.CORRECTION
            if category is ResponseCategory.INCORRECT
            else TutoringStrategy.SIMPLIFICATION
        )
        self._record_activity("remediation_selected", "停在當前概念補架", detail=node_id)
        log_event(
            "pelican_remediation_selected",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
            node_id=node_id,
            remediation_reason=category.value,
            reason_code="stay_on_current_concept",
        )
        self.state.phase = "tutoring"
        self.state.current_prompt = self._remediation_prompt(node_id, label)
        self.state.current_prompt_source = "rule"
        self.store.save(self.state)
        return TurnOutcome(
            self.state.current_prompt,
            node_id,
            category,
            strategy,
            tuple(changes),
            "skill remediation：回答未通過，停在目前概念補架，不跳下一題",
        )

    def _handle_scope_mismatch(self, answer: str, signal: str) -> TurnOutcome:
        """Record scope mismatch as direct evidence without treating it as mastery."""
        node_id = self._require_current_node()
        strategy = strategy_for_remediation_signal(signal) or TutoringStrategy.SIMPLIFICATION
        self._record_activity("scope_mismatch", "偵測題目層級不合", detail=signal)
        self._record(answer, ResponseCategory.DIFFICULTY, strategy, [])
        self._refresh_learning_context(answer, ResponseCategory.DIFFICULTY, signal)
        self.state.current_prompt = (
            "收到，剛才那題對目前起點太細了。\n\n"
            + self._remediation_prompt(node_id, self.curriculum.nodes[node_id].label)
        )
        self.state.current_prompt_source = "rule"
        self.store.save(self.state)
        log_event(
            "pelican_scope_mismatch",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            reason_code=signal,
            remediation_reason=signal,
        )
        return TurnOutcome(
            self.state.current_prompt,
            node_id,
            ResponseCategory.DIFFICULTY,
            strategy,
            (),
            "scope mismatch：重新校準抽象層級，不前進到無關節點",
        )

    def _handle_scaffold_request(self, answer: str, category: ResponseCategory) -> TurnOutcome:
        """Scaffold the current prerequisite path instead of advancing diagnostics."""
        node_id = self._require_current_node()
        self._record_activity("scaffold_selected", "選擇前置概念補架", detail=node_id)
        self.state.nodes[node_id].update(
            KnowledgeStatus.NOT_MASTERED,
            evidence=self._evidence(answer, category),
        )
        changes = [f"{self.curriculum.nodes[node_id].label}: not_mastered（直接證據）"]
        strategy = strategy_for_remediation_signal("unknown") or TutoringStrategy.DECOMPOSITION
        self._record(answer, category, strategy, changes)
        self._refresh_learning_context(answer, category, "unknown")
        prerequisite_id = self.curriculum.nodes[node_id].prerequisites[0] if self.curriculum.nodes[node_id].prerequisites else node_id
        self.state.phase = "tutoring"
        self.state.current_node_id = prerequisite_id
        self.state.current_prompt = (
            f"沒關係，我們先補「{self.curriculum.nodes[prerequisite_id].label}」。\n\n"
            + self._remediation_prompt(prerequisite_id, self.curriculum.nodes[prerequisite_id].label)
        )
        self.state.current_prompt_source = "rule"
        self.store.save(self.state)
        log_event(
            "pelican_scaffold_selected",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            reason_code="unknown",
            remediation_reason="unknown",
        )
        return TurnOutcome(
            self.state.current_prompt,
            prerequisite_id,
            category,
            strategy,
            tuple(changes),
            "unknown：先 scaffold prerequisite，不跳到下一個診斷題",
        )

    def _handle_acceleration_request(self, answer: str) -> TurnOutcome:
        """Handle a too-easy signal by marking current concept as mastered evidence."""
        node_id = self._require_current_node()
        self._record_activity("acceleration_selected", "加快學習節奏", detail=node_id)
        self.state.nodes[node_id].update(
            KnowledgeStatus.MASTERED,
            evidence=self._evidence(answer, ResponseCategory.CORRECT),
        )
        changes = [f"{self.curriculum.nodes[node_id].label}: mastered（學生要求加速的直接證據）"]
        strategy = strategy_for_remediation_signal("too_easy") or TutoringStrategy.CONFIRMATION
        self._record(answer, ResponseCategory.CORRECT, strategy, changes)
        self._refresh_learning_context(answer, ResponseCategory.CORRECT, "too_easy")
        self.store.save(self.state)
        next_outcome = self._present_next_diagnostic()
        return TurnOutcome(
            "了解，我會加快節奏。\n\n" + next_outcome.message,
            next_outcome.node_id,
            ResponseCategory.CORRECT,
            strategy,
            tuple(changes),
            "too_easy：加速到下一個仍需確認的概念",
        )

    def _handle_tutoring(self, answer: str) -> TurnOutcome:
        """Handle practice-step tutoring after diagnosis has selected a path."""
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

    def _refresh_learning_context(self, answer: str, category: ResponseCategory, signal: str | None = None) -> None:
        """Update bounded direct evidence and keep EDF inference separate."""
        previous_edf = self.state.edf_snapshot
        self.memory.record_direct_evidence(self.state, answer, category, signal=signal)
        log_event(
            "pelican_memory_evidence_recorded",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            node_id=self.state.current_node_id,
            category=category.value,
            memory_event="direct_evidence",
            reason_code=signal or category.value,
        )
        self._record_activity("memory_updated", "保存直接學習證據", detail=signal or category.value)
        self.state.edf_snapshot = self.edf.evaluate(self.state)
        self._record_activity(
            "edf_evaluated",
            "更新 EDF 教學策略",
            detail=self.state.edf_snapshot.pedagogical_strategy,
        )
        log_event(
            "pelican_diagnosis_updated",
            learner_id=self.state.learner_id,
            category=category.value,
            learner_state=self.state.edf_snapshot.learner_state,
            strategy=self.state.edf_snapshot.pedagogical_strategy,
            edf_transition=f"{previous_edf.learner_state}->{self.state.edf_snapshot.learner_state}",
            reason_code=f"{previous_edf.learner_state}->{self.state.edf_snapshot.learner_state}",
        )

    def _remediation_prompt(self, node_id: str, label: str) -> str:
        """Return a skill-authored remediation prompt when available."""
        if self.state.learning_plan:
            template = self.state.learning_plan.remediation_templates.get(node_id)
            if template:
                return template.format(label=label)
        return (
            f"我們先停在「{label}」。剛才那題先不往下推。\n\n"
            f"我換成更清楚的方式：請用一句話說，{label} 在整個學習中主要幫我們做什麼？"
        )

    def _present_current_step(self, reason: str) -> TurnOutcome:
        """Return the already persisted tutoring prompt."""
        return TurnOutcome(self.state.current_prompt, self.state.current_node_id, None, None, (), reason)

    def _set_current_step(self, step: dict[str, str]) -> None:
        """Persist the active task step as the current tutor prompt."""
        self.state.current_step_id = step["step_id"]
        self.state.current_node_id = step["node_id"]
        self.state.current_prompt = step["prompt"]
        self.state.current_expected_answer = step["expected"]
        self.state.current_prompt_source = "llm" if self.state.plan_source.value == "llm" else "rule"

    def _classify(self, answer: str) -> ResponseCategory:
        """Classify a learner answer with optional LLM fallback to rules."""
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
        """Generate or select a tutor response without changing mastery state."""
        if self.state.mode == "llm":
            try:
                generated = self.llm.tutor_response(strategy, self.state.current_prompt, self.curriculum.nodes[node_id].label)
                if generated:
                    return generated, "llm"
            except LlmUnavailable:
                pass
        return rule_tutor_message(strategy, node_id, self.state.current_prompt, self.curriculum), "rule"

    def _show_answer(self) -> TurnOutcome:
        """Reveal the expected answer without writing mastery evidence."""
        return TurnOutcome("提示答案：請直接輸入 expected answer 來通過測試。這是教師直接揭示，不會更新 mastery。", self.state.current_node_id, None, None, (), "教師揭示不等同學生掌握")

    def _record(self, answer: str, category: ResponseCategory, strategy: TutoringStrategy | None, changes: list[str]) -> None:
        """Append a local turn record for auditability inside the MVP only."""
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
        """Return the selected node or fail when the state machine is inconsistent."""
        if not self.state.current_node_id:
            raise RuntimeError("No current knowledge node is selected")
        return self.state.current_node_id

    @staticmethod
    def _evidence(answer: str, category: ResponseCategory):
        """Create direct node evidence from a learner answer."""
        from .models import Evidence

        return Evidence(response=answer, category=category.value, direct=True)

    def _record_activity(self, code: str, label: str, *, status: str = "done", detail: str = "") -> None:
        """Append a safe system activity entry and emit the matching log event."""
        event = ActivityEvent(code=code, label=label, status=status, detail=detail)
        self.state.activity_log.append(event)
        if len(self.state.activity_log) > MAX_ACTIVITY_LOG:
            self.state.activity_log = self.state.activity_log[-MAX_ACTIVITY_LOG:]
        log_event(
            "pelican_activity",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            plan_source=self.state.plan_source.value,
            activity_code=code,
            activity_status=status,
            node_id=self.state.current_node_id,
            detail_code=detail,
            skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else self.state.intake_profile.skill_id,
            skill_version=self.state.learning_plan.skill_version if self.state.learning_plan else self.state.intake_profile.skill_version,
            skill_lifecycle=self.state.learning_plan.skill_lifecycle if self.state.learning_plan else self.state.intake_profile.skill_lifecycle,
            domain_category=(
                self.state.learning_plan.domain_category
                if self.state.learning_plan and self.state.learning_plan.domain_category
                else self.state.intake_profile.domain_category
            ),
            route=self.state.learning_plan.model_route if self.state.learning_plan else self.state.intake_profile.model_route,
        )


def _infer_learning_intent(answer: str) -> LearningIntent:
    """Infer a coarse intent label from onboarding text using deterministic rules."""
    if any(token in answer for token in ("專案", "project", "作品")):
        return LearningIntent.PROJECT
    if any(token in answer for token in ("考試", "面試", "測驗", "assessment")):
        return LearningIntent.ASSESSMENT
    if any(token in answer for token in ("實作", "程式", "coding", "code")):
        return LearningIntent.IMPLEMENTATION
    if any(token in answer for token in ("商業", "決策", "finance", "business")):
        return LearningIntent.BUSINESS_DECISION
    if any(token in answer for token in ("語言", "口說", "寫作")):
        return LearningIntent.LANGUAGE_PRACTICE
    if any(token in answer for token in ("背景", "解釋", "歷史")):
        return LearningIntent.EXPLANATORY
    return LearningIntent.CONCEPTUAL


def _infer_level_hint(answer: str) -> str:
    """Infer a coarse level hint without treating it as mastery evidence."""
    if any(token in answer for token in ("完全沒有", "零基礎", "沒有基礎", "beginner")):
        return "beginner"
    if any(token in answer for token in ("實作經驗", "做過", "熟", "advanced")):
        return "advanced"
    if any(token in answer for token in ("學過", "一點", "簡單題", "intermediate")):
        return "intermediate"
    return "unknown"


def _domain_category_from_value(value: str) -> DomainCategory:
    """Convert persisted category text into a safe enum for routing decisions."""
    try:
        return DomainCategory(value)
    except ValueError:
        return DomainCategory.UNKNOWN


def _rule_intake_question(category: DomainCategory, stage: str) -> str:
    """Return a domain-aware fallback question when no LLM route is available."""
    questions = {
        DomainCategory.STEM: {
            "goal": "你這次比較想怎麼學？請選一個方向回答：理解概念、程式實作、做小專案、準備考試/面試，或先解釋背景。",
            "level": "你目前的基礎大概在哪裡？可以回答：完全沒有基礎、學過一點、能做簡單題、或已經有實作經驗。",
        },
        DomainCategory.HUMANITIES: {
            "goal": "你想從哪個角度切入？可以回答：時代脈絡、人物事件、制度文化、思想觀念、史料閱讀，或考試整理。",
            "level": "你目前對這個主題的熟悉度如何？可以回答：完全不熟、知道一些名詞、讀過入門內容、或能分析文本/事件。",
        },
        DomainCategory.BUSINESS: {
            "goal": "你想用這個主題解決哪類問題？可以回答：理解概念、分析案例、做決策、看財務數字，或準備報告/面試。",
            "level": "你目前相關經驗大概在哪裡？可以回答：完全沒有背景、看過一些案例、能做基本分析，或有實務經驗。",
        },
        DomainCategory.LANGUAGE: {
            "goal": "你想優先練哪個能力？可以回答：聽力、口說、閱讀、寫作、文法、考試，或工作/旅遊情境。",
            "level": "你目前程度大概在哪裡？可以回答：初學、能看簡單句、能日常溝通，或想修正進階表達。",
        },
    }
    fallback = {
        "goal": "你想從哪個角度學這個主題？可以說明目標、用途、想解決的困難，或是否為了考試/工作。",
        "level": "你目前對這個主題的熟悉度如何？可以回答：完全不熟、學過一點、能做簡單應用，或已有實務經驗。",
    }
    return questions.get(category, fallback).get(stage, fallback["goal"])
