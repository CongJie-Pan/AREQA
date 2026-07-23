"""The observable PELICAN state machine used by the CLI and tests."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .curriculum import CURRICULUMS
from .agents import (
    AgentExecutionContext,
    AgentExecutionResult,
    DiagnosisAgent,
    FastTutorAgent,
    IntakeAgent,
    PolicyAgent,
    SkillAgent,
    SkillAgentInput,
    SlowSimulatorAgent,
    StateAgent,
)
from .diagnosis import apply_diagnostic_result, classify_response, diagnostic_for, next_diagnostic_node, remediation_signal
from .domain_skill import DomainCategory
from .llm import IntakeSemanticSignal, LlmAdapter, LlmUnavailable
from .models import (
    ActivityEvent,
    AgentProposal,
    AgentRole,
    BoundedTutorProposal,
    KnowledgeStatus,
    LearnerIntakeProfile,
    LearnerProgressNode,
    LearnerProgressSnapshot,
    LearningIntent,
    MethodologyEvent,
    MethodologyEventType,
    MethodologyRef,
    MethodologyStage,
    MethodologyStatus,
    PlanSource,
    ProposalValidationStatus,
    ResponseCategory,
    SessionState,
    TutoringContext,
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
from .skill_generator import DomainSkillGenerator


MAX_ACTIVITY_LOG = 16
MAX_METHODOLOGY_EVENTS = 64
MAX_AGENT_PROPOSALS = 48


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
        self.intake_agent = IntakeAgent()
        self.skill_agent = SkillAgent(DomainSkillGenerator(self.llm))
        self.diagnosis_agent = DiagnosisAgent(self.llm)
        self.state_agent = StateAgent()
        self.fast_tutor_agent = FastTutorAgent(self.llm)
        self.slow_simulator_agent = SlowSimulatorAgent(self.llm)
        self.edf = EdfSimulator()
        self.policy_agent = PolicyAgent(self.edf)
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

        self._begin_turn()
        if self.state.phase == "onboarding":
            return self._handle_onboarding(answer)
        if self.state.phase == "diagnosis":
            return self._handle_diagnostic(answer)
        return self._handle_tutoring(answer)

    def _begin_turn(self) -> None:
        """Allocate correlation IDs for one accepted learner message.

        This method is intentionally called only from ``respond()`` after empty
        input validation. Resume paths such as ``start()`` can present existing
        prompts, but they must not create a new learner turn or duplicate
        methodology records for a historical cycle.
        """
        token = uuid.uuid4().hex[:12]
        self.state.turn_id = f"turn_{token}"
        self.state.cycle_id = f"cycle_{token}"
        log_event(
            "pelican_turn_started",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            sequence=self.state.methodology_sequence,
            reason_code="learner_message_accepted",
        )
        self._record_methodology_event(
            MethodologyEventType.LEARNER_INTERACTION,
            source="respond",
            input_ref=MethodologyRef("learner_turn", self.state.turn_id, "accepted learner message"),
            output_ref=MethodologyRef("cycle", self.state.cycle_id, "active tutoring cycle"),
            reason_code="learner_message_accepted",
        )

    def _next_methodology_sequence(self) -> int:
        """Return the next monotonic methodology sequence number."""
        self.state.methodology_sequence += 1
        return self.state.methodology_sequence

    def _bounded_append(self, collection_name: str, item: Any, limit: int) -> None:
        """Append one bounded methodology record to a named session collection."""
        collection = getattr(self.state, collection_name)
        collection.append(item)
        if len(collection) > limit:
            setattr(self.state, collection_name, collection[-limit:])

    def _record_agent_proposal(
        self,
        role: AgentRole,
        stage: MethodologyStage,
        artifact_type: str,
        payload_ref: MethodologyRef,
        *,
        validation_status: ProposalValidationStatus = ProposalValidationStatus.ACCEPTED,
        reason_code: str = "accepted",
        node_id: str | None = None,
        strategy: str | None = None,
        skill_id: str | None = None,
        display_summary: str = "",
        pedagogical_move: str = "",
        final_message_preview: str = "",
    ) -> AgentProposal:
        """Record a bounded proposal before the engine applies its effect.

        The record is proposal metadata only. It never contains raw learner text,
        prompts, or model output; state mutation remains owned by ``PelicanEngine``.
        """
        proposal = AgentProposal(
            proposal_id=f"proposal_{uuid.uuid4().hex[:12]}",
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            sequence=self._next_methodology_sequence(),
            role=role,
            stage=stage,
            artifact_type=artifact_type,
            payload_ref=payload_ref,
            validation_status=validation_status,
            reason_code=reason_code,
            node_id=node_id,
            strategy=strategy,
            skill_id=skill_id,
            display_summary=display_summary,
            pedagogical_move=pedagogical_move,
            final_message_preview=final_message_preview,
        )
        self._bounded_append("agent_proposals", proposal, MAX_AGENT_PROPOSALS)
        log_event(
            "pelican_agent_proposal_recorded",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            sequence=proposal.sequence,
            proposal_id=proposal.proposal_id,
            agent_role=role.value,
            validation_status=validation_status.value,
            reason_code=reason_code,
        )
        return proposal

    def _record_agent_result(
        self,
        result: AgentExecutionResult,
        *,
        node_id: str | None = None,
        strategy: str | None = None,
        skill_id: str | None = None,
    ) -> AgentProposal:
        """Record an executor result after the engine validates adoption scope."""
        return self._record_agent_proposal(
            result.role,
            result.stage,
            result.artifact_type,
            result.artifact_ref,
            validation_status=result.validation_status,
            reason_code=result.reason_code,
            node_id=node_id,
            strategy=strategy,
            skill_id=skill_id,
            display_summary=result.display_summary,
            pedagogical_move=result.pedagogical_move,
            final_message_preview=result.final_message_preview,
        )

    def _record_methodology_event(
        self,
        event_type: MethodologyEventType,
        *,
        stage: MethodologyStage | None = None,
        status: MethodologyStatus = MethodologyStatus.COMPLETED,
        source: str = "engine",
        input_ref: MethodologyRef | None = None,
        output_ref: MethodologyRef | None = None,
        node_id: str | None = None,
        strategy: str | None = None,
        reason_code: str = "recorded",
    ) -> MethodologyEvent:
        """Record a safe, cycle-grouped methodology event.

        Pipeline events are limited to the six Figure 1 stages. GUM updates and
        learner messages use separate event types so UI rendering cannot inflate
        the core methodology graph.
        """
        event = MethodologyEvent(
            event_id=f"event_{uuid.uuid4().hex[:12]}",
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            sequence=self._next_methodology_sequence(),
            event_type=event_type,
            stage=stage,
            status=status,
            source=source,
            input_ref=input_ref,
            output_ref=output_ref,
            node_id=node_id,
            strategy=strategy,
            reason_code=reason_code,
        )
        self._bounded_append("methodology_events", event, MAX_METHODOLOGY_EVENTS)
        log_event(
            "pelican_methodology_event_recorded",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            sequence=event.sequence,
            event_type=event_type.value,
            methodology_status=status.value,
            node_id=node_id,
            strategy=strategy,
            reason_code=reason_code,
        )
        return event

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

            topic_interpretation = self.intake_agent.propose_topic(answer, context=self._agent_execution_context())
            resolution = topic_interpretation.domain_resolution or resolve_domain_category(answer)
            self._record_agent_result(topic_interpretation.result)
            self._record_methodology_event(
                MethodologyEventType.PIPELINE_STAGE,
                stage=MethodologyStage.GOAL_FRAMING,
                input_ref=MethodologyRef("learner_turn", self.state.turn_id or "turn", "topic answer"),
                output_ref=MethodologyRef("intake_profile", "topic", "scoped topic"),
                reason_code=resolution.reason_code,
            )
            self._record_activity("intake_topic", "接收學習主題", detail="topic_received")
            self._record_activity(
                "domain_resolved",
                "判斷學習領域",
                detail=f"{resolution.category.value}:{resolution.reason_code}",
            )
            self.state.intake_profile = LearnerIntakeProfile(
                topic=topic_interpretation.topic or answer,
                goal_summary=f"學習 {topic_interpretation.topic or answer}",
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
            semantic_signal = self._classify_intake_semantics(answer, "goal")
            if semantic_signal.intent == "topic_revision" and semantic_signal.confidence >= 0.72 and semantic_signal.new_topic:
                return self._handle_topic_revision(semantic_signal)
            intent = _infer_learning_intent(answer)
            goal_interpretation = self.intake_agent.propose_goal(answer, intent, context=self._agent_execution_context())
            self._record_agent_result(goal_interpretation.result)
            self._record_methodology_event(
                MethodologyEventType.PIPELINE_STAGE,
                stage=MethodologyStage.GOAL_FRAMING,
                input_ref=MethodologyRef("learner_turn", self.state.turn_id or "turn", "goal answer"),
                output_ref=MethodologyRef("intake_profile", "goal", "goal interpretation"),
                reason_code=intent.value,
            )
            self._record_activity("intent_detected", "判斷學習方向", detail=intent.value)
            self.state.intake_profile = LearnerIntakeProfile(
                topic=intake.topic,
                goal_summary=goal_interpretation.goal_summary or answer,
                intent=goal_interpretation.intent,
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

        semantic_signal = self._classify_intake_semantics(answer, "level")
        if semantic_signal.intent == "topic_revision" and semantic_signal.confidence >= 0.72 and semantic_signal.new_topic:
            return self._handle_topic_revision(semantic_signal)

        level_interpretation = self.intake_agent.propose_level(
            _infer_level_hint(answer),
            context=self._agent_execution_context(),
        )
        level_hint = level_interpretation.level_hint
        self._record_agent_result(level_interpretation.result)
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.GOAL_FRAMING,
            input_ref=MethodologyRef("learner_turn", self.state.turn_id or "turn", "level answer"),
            output_ref=MethodologyRef("intake_profile", "level", "level interpretation"),
            reason_code=level_hint,
        )
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
        skill_proposal = self.skill_agent.propose_skill(
            SkillAgentInput(profile),
            context=self._agent_execution_context(),
        )
        plan = self.planner.compile_validated_skill(skill_proposal.skill, profile, skill_proposal.route)
        for attempt in skill_proposal.attempts:
            self._record_agent_proposal(
                attempt.role,
                attempt.stage,
                attempt.artifact_type,
                attempt.artifact_ref,
                validation_status=attempt.validation_status,
                reason_code=attempt.reason_code,
                skill_id=skill_proposal.skill.skill_id,
                display_summary=attempt.display_summary,
            )
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.SKILL_CONSTRUCTION,
            input_ref=MethodologyRef("intake_profile", "profile", "scoped learning goal"),
            output_ref=MethodologyRef("learning_plan", plan.plan_id, "validated learning plan"),
            reason_code=plan.skill_id or "fallback_plan",
        )
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

    def _agent_execution_context(self) -> AgentExecutionContext:
        """Build safe metadata for agent executor calls.

        Returns:
            Context containing correlation IDs and current safe strategy/state
            labels. Raw learner answers, prompts, model output, and provider
            payloads are intentionally excluded because agents must return only
            bounded proposal metadata to the engine.
        """
        return AgentExecutionContext(
            learner_id=self.state.learner_id,
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            phase=self.state.phase,
            mode=self.state.mode,
            node_id=self.state.current_node_id,
            skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
            edf_state=self.state.edf_snapshot.learner_state,
            edf_policy=self.state.edf_snapshot.pedagogical_strategy,
            recent_safe_signals=self.memory.recent_safe_signals(self.state),
        )

    def _classify_intake_semantics(self, answer: str, stage: str) -> IntakeSemanticSignal:
        """Classify onboarding replies before deterministic state transitions.

        The LLM only returns a bounded semantic signal; it never mutates session
        state or decides the next engine phase. The stable structured event
        ``pelican_intake_semantic_classified`` logs the signal intent,
        confidence, source, and reason code without raw learner text or model
        output. If LLM classification is unavailable, a narrow rule fallback only
        catches explicit correction patterns so the system remains usable
        offline without becoming a hard-coded semantic engine.
        """
        intake = self.state.intake_profile
        category = _domain_category_from_value(intake.domain_category)
        source = "rule"
        if self.state.mode == "llm" and self.llm.available and hasattr(self.llm, "classify_intake_semantics"):
            try:
                signal = self.llm.classify_intake_semantics(
                    current_topic=intake.topic,
                    answer=answer,
                    stage=stage,
                    domain_category=category,
                )
                source = "llm"
            except LlmUnavailable as exc:
                log_event(
                    "pelican_intake_semantic_fallback",
                    learner_id=self.state.learner_id,
                    phase=self.state.phase,
                    domain_category=category.value,
                    route=intake.model_route,
                    intake_decision=stage,
                    intake_source="llm_failed",
                    reason_code="|".join(exc.reason_codes or ("llm_unavailable",)),
                    api_status_code=exc.api_status_code,
                    api_error_type=exc.api_error_type,
                )
                signal = _rule_intake_semantic_signal(answer)
        else:
            signal = _rule_intake_semantic_signal(answer)
        log_event(
            "pelican_intake_semantic_classified",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            domain_category=category.value,
            route=intake.model_route,
            intake_decision=stage,
            intake_source=source,
            semantic_intent=signal.intent,
            semantic_confidence=round(signal.confidence, 3),
            reason_code=signal.reason_code,
        )
        return signal

    def _handle_topic_revision(self, signal: IntakeSemanticSignal) -> TurnOutcome:
        """Apply a confirmed topic correction and restart goal calibration.

        Topic revisions reset only onboarding-derived topic/goal/level metadata.
        They do not let the model mutate the knowledge tree, phase, or learning
        evidence. The previous partial intake is discarded because keeping a goal
        or level answer collected for the wrong topic would compile a misleading
        skill plan.
        """
        from .domain_catalog import resolve_domain_category

        new_topic = signal.new_topic.strip()[:100]
        resolution = resolve_domain_category(new_topic)
        self._record_activity("topic_revised", "更新學習主題", detail=resolution.category.value)
        self._record_activity(
            "domain_resolved",
            "判斷學習領域",
            detail=f"{resolution.category.value}:{resolution.reason_code}",
        )
        self.state.intake_profile = LearnerIntakeProfile(
            topic=new_topic,
            goal_summary=f"學習 {new_topic}",
            intent=LearningIntent.UNKNOWN,
            level_hint="unknown",
            domain_category=resolution.category.value,
            model_route=resolution.route_slug,
            intake_turns=1,
        )
        self.store.save(self.state)
        log_event(
            "pelican_topic_revised",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            domain_category=resolution.category.value,
            route=resolution.route_slug,
            intake_decision="topic_revision",
            semantic_intent=signal.intent,
            semantic_confidence=round(signal.confidence, 3),
            reason_code=signal.reason_code,
        )
        question, _source = self._next_intake_question("goal")
        return TurnOutcome(
            f"了解，我把主題改成「{new_topic}」。\n\n{question}",
            None,
            None,
            None,
            (),
            "topic revision：重新收集學習目標與意圖",
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
        diagnostic_proposal = self.diagnosis_agent.propose_next_diagnostic(
            self.state,
            self.curriculum,
            context=self._agent_execution_context(),
        )
        node_id = diagnostic_proposal.node_id
        if node_id is None or diagnostic_proposal.question is None:
            self.state.phase = "tutoring"
            step = self.curriculum.first_task_step()
            self._set_current_step(step)
            self._record_activity("tutoring_started", "進入教學引導", detail=step["node_id"])
            self._record_methodology_event(
                MethodologyEventType.PIPELINE_STAGE,
                stage=MethodologyStage.TUTOR_RESPONSE,
                input_ref=MethodologyRef("task_step", step["step_id"], "first tutor step"),
                output_ref=MethodologyRef("tutor_message", "rule", "tutor prompt"),
                node_id=step["node_id"],
                reason_code="diagnosis_complete",
            )
            self.store.save(self.state)
            return self._present_current_step("診斷完成，依未掌握概念開始原題引導")
        question = diagnostic_proposal.question
        skill_question_locked = self._uses_generated_skill_plan() and question.source == "skill"
        self._record_agent_result(diagnostic_proposal.result, node_id=node_id)
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.COGNITIVE_DIAGNOSIS,
            input_ref=MethodologyRef("learning_plan", self.state.learning_plan.plan_id if self.state.learning_plan else self.state.curriculum_id or "fixture", "active curriculum"),
            output_ref=MethodologyRef("diagnostic_node", node_id, "selected diagnostic"),
            node_id=node_id,
            reason_code=diagnostic_proposal.reason_code,
        )
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
        state_proposal = self.state_agent.propose_diagnostic_update(
            node_id,
            category,
            context=self._agent_execution_context(),
        )
        self._record_agent_result(state_proposal, node_id=node_id)
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.KNOWLEDGE_STATE_UPDATE,
            input_ref=MethodologyRef("diagnostic_evidence", node_id, "classified evidence"),
            output_ref=MethodologyRef("knowledge_state", node_id, "state update proposal"),
            node_id=node_id,
            reason_code=category.value,
        )
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
        base_message = self._scope_mismatch_prompt(node_id, self.curriculum.nodes[node_id].label)
        message, source, validation_status, proposal_reason, pedagogical_move, display_summary, tutor_result = self._tutor_message(
            strategy,
            node_id,
            evidence_signal=signal,
            base_message=base_message,
            tutor_role=AgentRole.FAST_TUTOR_AGENT,
        )
        self.state.current_prompt = message
        self.state.current_prompt_source = source
        self._record_agent_result(
            tutor_result,
            node_id=node_id,
            strategy=strategy.value,
            skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
        )
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.TUTOR_RESPONSE,
            input_ref=MethodologyRef("strategy", strategy.value, "scope remediation strategy"),
            output_ref=MethodologyRef("tutor_message", source, "scope remediation response"),
            node_id=node_id,
            strategy=strategy.value,
            reason_code=signal,
        )
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
        self._record_agent_proposal(
            AgentRole.STATE_AGENT,
            MethodologyStage.KNOWLEDGE_STATE_UPDATE,
            "scaffold_state_update",
            MethodologyRef("diagnostic_evidence", node_id, "unknown diagnostic evidence"),
            node_id=node_id,
            reason_code=category.value,
        )
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.KNOWLEDGE_STATE_UPDATE,
            input_ref=MethodologyRef("diagnostic_evidence", node_id, "unknown evidence"),
            output_ref=MethodologyRef("knowledge_state", node_id, "scaffold state update"),
            node_id=node_id,
            reason_code=category.value,
        )
        changes: list[str] = []
        current_status = self.state.nodes[node_id].status
        if current_status not in (KnowledgeStatus.MASTERED, KnowledgeStatus.INFERRED_MASTERED):
            self.state.nodes[node_id].update(
                KnowledgeStatus.NOT_MASTERED,
                evidence=self._evidence(answer, category),
            )
            changes.append(f"{self.curriculum.nodes[node_id].label}: not_mastered（直接證據）")
        strategy = strategy_for_remediation_signal("unknown") or TutoringStrategy.DECOMPOSITION
        self._record(answer, category, None, changes)
        self._refresh_learning_context(answer, category, "unknown")
        prerequisite_id = self.curriculum.nodes[node_id].prerequisites[0] if self.curriculum.nodes[node_id].prerequisites else node_id
        self.state.phase = "tutoring"
        self.state.current_node_id = prerequisite_id
        base_message = self._scaffold_prompt(
            prerequisite_id,
            self.curriculum.nodes[prerequisite_id].label,
        )
        message, source, validation_status, proposal_reason, pedagogical_move, display_summary, tutor_result = self._tutor_message(
            strategy,
            prerequisite_id,
            evidence_signal="unknown",
            base_message=base_message,
            tutor_role=AgentRole.SLOW_SIMULATOR_AGENT,
        )
        self.state.current_prompt = message
        self.state.current_prompt_source = source
        self._record_agent_result(
            tutor_result,
            node_id=prerequisite_id,
            strategy=strategy.value,
            skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
        )
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.TUTOR_RESPONSE,
            input_ref=MethodologyRef("strategy", strategy.value, "scaffold strategy"),
            output_ref=MethodologyRef("tutor_message", source, "scaffold response"),
            node_id=prerequisite_id,
            strategy=strategy.value,
            reason_code="unknown",
        )
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
        self._record_agent_proposal(
            AgentRole.STATE_AGENT,
            MethodologyStage.KNOWLEDGE_STATE_UPDATE,
            "acceleration_state_update",
            MethodologyRef("diagnostic_evidence", node_id, "too easy signal"),
            node_id=node_id,
            reason_code="too_easy",
        )
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.KNOWLEDGE_STATE_UPDATE,
            input_ref=MethodologyRef("diagnostic_evidence", node_id, "acceleration evidence"),
            output_ref=MethodologyRef("knowledge_state", node_id, "accelerated state update"),
            node_id=node_id,
            reason_code="too_easy",
        )
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
        signal = remediation_signal(answer)
        # Learner control signals remain remediation requests after tutoring
        # begins; they are not ordinary practice evidence and must not overwrite
        # a previously mastered node.
        if self.state.plan_source is PlanSource.GENERATED and signal in {"too_detailed", "too_difficult"}:
            return self._handle_scope_mismatch(answer, signal)
        if self.state.plan_source is PlanSource.GENERATED and signal == "too_easy":
            return self._handle_acceleration_request(answer)
        category = self._classify(answer)
        if self.state.plan_source is PlanSource.GENERATED and category is ResponseCategory.INABILITY:
            return self._handle_scaffold_request(answer, category)
        changes: list[str] = []
        if category is ResponseCategory.CORRECT:
            self._record_agent_proposal(
                AgentRole.STATE_AGENT,
                MethodologyStage.KNOWLEDGE_STATE_UPDATE,
                "tutoring_state_update",
                MethodologyRef("practice_evidence", node_id, "correct practice evidence"),
                node_id=node_id,
                reason_code=category.value,
            )
            self._record_methodology_event(
                MethodologyEventType.PIPELINE_STAGE,
                stage=MethodologyStage.KNOWLEDGE_STATE_UPDATE,
                input_ref=MethodologyRef("practice_evidence", node_id, "correct practice evidence"),
                output_ref=MethodologyRef("knowledge_state", node_id, "practice state update"),
                node_id=node_id,
                reason_code=category.value,
            )
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
            self._record_methodology_event(
                MethodologyEventType.PIPELINE_STAGE,
                stage=MethodologyStage.TUTOR_RESPONSE,
                input_ref=MethodologyRef("task_step", step["step_id"], "next tutor step"),
                output_ref=MethodologyRef("tutor_message", "rule", "next tutor prompt"),
                node_id=step["node_id"],
                strategy=TutoringStrategy.CONFIRMATION.value,
                reason_code="next_step_unlocked",
            )
            self.store.save(self.state)
            next_outcome = self._present_current_step("前一子任務已完成，解鎖下一步")
            return TurnOutcome(next_outcome.message, next_outcome.node_id, category, TutoringStrategy.CONFIRMATION, tuple(changes), next_outcome.next_reason)
        rounds = self.state.step_rounds.get(step_id, 0) + 1
        self.state.step_rounds[step_id] = rounds
        if category in (ResponseCategory.INCORRECT, ResponseCategory.INABILITY):
            self._record_agent_proposal(
                AgentRole.STATE_AGENT,
                MethodologyStage.KNOWLEDGE_STATE_UPDATE,
                "tutoring_state_update",
                MethodologyRef("practice_evidence", node_id, "practice evidence"),
                node_id=node_id,
                reason_code=category.value,
            )
            self._record_methodology_event(
                MethodologyEventType.PIPELINE_STAGE,
                stage=MethodologyStage.KNOWLEDGE_STATE_UPDATE,
                input_ref=MethodologyRef("practice_evidence", node_id, "practice evidence"),
                output_ref=MethodologyRef("knowledge_state", node_id, "practice state update"),
                node_id=node_id,
                reason_code=category.value,
            )
            self.state.nodes[node_id].update(
                KnowledgeStatus.NOT_MASTERED,
                evidence=self._evidence(answer, category),
            )
            changes.append(f"{self.curriculum.nodes[node_id].label}: not_mastered（原題直接證據）")
        self._record(answer, category, None, changes)
        self._refresh_learning_context(answer, category)
        context = self._tutoring_context(category, rounds)
        strategy, reason = select_strategy(context)
        signal = self.state.direct_evidence[-1].signal if self.state.direct_evidence else category.value
        tutor_role = AgentRole.SLOW_SIMULATOR_AGENT if "slow-thinking" in reason else AgentRole.FAST_TUTOR_AGENT
        message, source, validation_status, proposal_reason, pedagogical_move, display_summary, tutor_result = self._tutor_message(
            strategy,
            node_id,
            evidence_signal=signal,
            tutor_role=tutor_role,
        )
        self._record_agent_result(
            tutor_result,
            node_id=node_id,
            strategy=strategy.value,
            skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
        )
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.TUTOR_RESPONSE,
            input_ref=MethodologyRef("strategy", strategy.value, "selected strategy"),
            output_ref=MethodologyRef("tutor_message", source, "tutor response"),
            node_id=node_id,
            strategy=strategy.value,
            reason_code="slow_strategy" if tutor_role is AgentRole.SLOW_SIMULATOR_AGENT else "fast_strategy",
        )
        self.state.current_prompt = message
        self.state.current_prompt_source = source
        self.store.save(self.state)
        return TurnOutcome(message, node_id, category, strategy, tuple(changes), reason)

    def _refresh_learning_context(self, answer: str, category: ResponseCategory, signal: str | None = None) -> None:
        """Update bounded direct evidence and keep EDF inference separate."""
        previous_edf = self.state.edf_snapshot
        self.memory.record_direct_evidence(self.state, answer, category, signal=signal)
        self._record_methodology_event(
            MethodologyEventType.GUM_SUBSYSTEM,
            input_ref=MethodologyRef("learner_evidence", self.state.turn_id or "turn", "direct evidence"),
            output_ref=MethodologyRef("memory_snapshot", self.state.current_node_id or "node", "GUM memory snapshot"),
            node_id=self.state.current_node_id,
            reason_code=signal or category.value,
        )
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
        proposed_snapshot, policy_proposal = self.policy_agent.propose_strategy(
            self.state,
            context=self._agent_execution_context(),
        )
        self.state.edf_snapshot = proposed_snapshot
        self._refresh_learner_progress()
        self._record_agent_result(policy_proposal, node_id=self.state.current_node_id)
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.EDF_STRATEGY_SELECTION,
            input_ref=MethodologyRef("knowledge_state", self.state.current_node_id or "node", "updated state and GUM"),
            output_ref=MethodologyRef("edf_snapshot", self.state.edf_snapshot.reason_code, "current EDF policy"),
            node_id=self.state.current_node_id,
            strategy=self.state.edf_snapshot.pedagogical_strategy,
            reason_code=self.state.edf_snapshot.reason_code,
        )
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

    def _refresh_learner_progress(self) -> None:
        """Refresh learner-visible progress from current knowledge state.

        The snapshot is derived metadata. It distinguishes direct evidence from
        inferred prerequisite state and carries confidence values without adding
        new mastery facts.
        """
        if not self.curriculum:
            self.state.learner_progress = LearnerProgressSnapshot(self.state.cycle_id, None, ())
            return
        progress_nodes: list[LearnerProgressNode] = []
        for node in sorted(self.curriculum.nodes.values(), key=lambda item: item.priority, reverse=True):
            node_state = self.state.nodes[node.node_id]
            direct_count = sum(1 for item in node_state.evidence if item.direct)
            inferred_from = tuple(
                evidence.response[:0] or node.node_id
                for evidence in node_state.evidence
                if not evidence.direct
            )
            if node_state.status is KnowledgeStatus.MASTERED:
                confidence = 0.9
                source = "direct" if direct_count else "inferred"
            elif node_state.status is KnowledgeStatus.INFERRED_MASTERED:
                confidence = 0.65
                source = "inferred_prerequisite"
            elif node_state.status is KnowledgeStatus.NOT_MASTERED:
                confidence = 0.75
                source = "direct"
            elif node_state.status is KnowledgeStatus.FRAGILE:
                confidence = 0.45
                source = "mixed"
            elif node_state.status is KnowledgeStatus.PARTIALLY_MASTERED:
                confidence = 0.55
                source = "partial"
            else:
                confidence = 0.0
                source = "none"
            progress_nodes.append(
                LearnerProgressNode(
                    node_id=node.node_id,
                    label=node.label,
                    status=node_state.status,
                    confidence=confidence,
                    evidence_source=source,
                    direct_evidence_count=direct_count,
                    inferred_from=inferred_from,
                )
            )
        self.state.learner_progress = LearnerProgressSnapshot(
            cycle_id=self.state.cycle_id,
            current_node_id=self.state.current_node_id,
            nodes=tuple(progress_nodes),
        )

    def _tutoring_context(self, category: ResponseCategory, rounds: int) -> TutoringContext:
        """Build current-turn tutoring context after state, GUM, and EDF updates."""
        node_id = self.state.current_node_id
        label = self.curriculum.nodes[node_id].label if self.curriculum and node_id else ""
        return TutoringContext(
            category=category,
            rounds=rounds,
            pedagogical_policy=self.state.edf_snapshot.pedagogical_strategy,
            learner_state=self.state.edf_snapshot.learner_state,
            node_id=node_id,
            node_label=label,
            recent_signals=self.memory.recent_safe_signals(self.state),
            plan_source=self.state.plan_source,
            skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
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

    def _scaffold_prompt(self, node_id: str, label: str) -> str:
        """Render an unknown-answer scaffold without reusing mismatch wording."""
        return (
            f"沒關係，我們先補「{label}」。\n\n"
            + self._remediation_prompt(node_id, label)
        )

    def _scope_mismatch_prompt(self, node_id: str, label: str) -> str:
        """Render a simpler level-recalibration prompt for too-detailed feedback."""
        if node_id == "math_intuition":
            return (
                "收到，剛才那題對目前起點還是太細了。我們先降到更粗的生活比喻。\n\n"
                "先不要想模型、公式或梯度。想像你在猜明天會不會下雨：猜完以後，"
                "你需要先知道「猜得準不準」。請只回答：我們為什麼需要先知道猜得準不準？"
            )
        if node_id == "vectors_tensors":
            return (
                "收到，剛才那題太細、太像技術細節了。我們先改成資料表達的直覺。\n\n"
                "先不要管 tensor 或維度。想像你要把一張圖片交給只懂數字的機器，"
                "第一步是不是要把圖片變成它看得懂的數字？請用一句話說說看。"
            )
        return (
            f"收到，剛才那題對目前起點太細了。我們先把「{label}」降成更高層的直覺問題。\n\n"
            f"先不要管術語，請只說：{label} 在這段學習裡大概想幫我們理解哪一件事？"
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

    def _tutor_message(
        self,
        strategy: TutoringStrategy,
        node_id: str,
        *,
        evidence_signal: str | None = None,
        base_message: str | None = None,
        tutor_role: AgentRole | None = None,
    ) -> tuple[str, str, ProposalValidationStatus, str, str, str, AgentExecutionResult]:
        """Generate or select a bounded tutor response without mastery mutation.

        Args:
            strategy: EDF-selected tutoring move.
            node_id: Current concept node to ground the response.
            evidence_signal: Safe current-turn signal used for proposal trace.
            base_message: Optional deterministic remediation message. Remediation
                handlers pass their already-rendered prompt here so rule-mode
                behavior and existing tests remain stable.

        Returns:
            Tuple of final message, source, validation status, safe reason code,
            pedagogical move, and display summary.

        Side Effects:
            Emits safe tutor proposal logs. The stable event names are
            ``pelican_tutor_proposal_generated`` and
            ``pelican_tutor_proposal_validated``. Metadata is limited to node,
            strategy, source, status, and bounded move labels; raw learner text,
            prompts, model output, provider bodies, and credentials are outside
            this logging boundary.
        """
        prompt = self._base_tutor_prompt(node_id)
        signal = evidence_signal or self.state.edf_snapshot.reason_code or strategy.value
        agent = (
            self.slow_simulator_agent
            if tutor_role is AgentRole.SLOW_SIMULATOR_AGENT
            else self.fast_tutor_agent
        )
        agent.llm = self.llm
        agent_response = agent.propose_response(
            state=self.state,
            curriculum=self.curriculum,
            strategy=strategy,
            node_id=node_id,
            base_prompt=prompt,
            evidence_signal=signal,
            recent_safe_signals=self.memory.recent_safe_signals(self.state),
            base_message=base_message,
            context=self._agent_execution_context(),
        )
        proposal = agent_response.proposal
        log_event(
            "pelican_tutor_proposal_validated",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            node_id=node_id,
            strategy=strategy.value,
            agent_role=agent_response.result.role.value,
            proposal_source=proposal.source,
            validation_status=agent_response.validation_status.value,
            reason_code=agent_response.reason_code,
            pedagogical_move=proposal.pedagogical_move,
        )
        return (
            proposal.response,
            proposal.source,
            agent_response.validation_status,
            agent_response.reason_code,
            proposal.pedagogical_move,
            proposal.summary,
            agent_response.result,
        )

    def _validate_tutor_proposal(
        self,
        proposal: BoundedTutorProposal | None,
        node_id: str,
        strategy: TutoringStrategy,
    ) -> tuple[ProposalValidationStatus, str]:
        """Validate one bounded tutor proposal before exposing it to the learner.

        Args:
            proposal: Candidate returned by the optional tutor model.
            node_id: Required grounding concept.
            strategy: Required EDF-selected strategy.

        Returns:
            Validation status and safe reason code.

        Safety:
            The validator fails closed. It accepts only non-empty, bounded,
            node-grounded proposals whose strategy matches the local EDF
            decision. Rejections trigger deterministic fallback and are recorded
            as safe metadata rather than raw model output.
        """
        if proposal is None:
            return ProposalValidationStatus.REJECTED, "empty_tutor_proposal"
        if proposal.node_id != node_id:
            return ProposalValidationStatus.REJECTED, "off_node_tutor_proposal"
        if proposal.strategy != strategy.value:
            return ProposalValidationStatus.REJECTED, "strategy_mismatch"
        if len(proposal.response) > 900:
            return ProposalValidationStatus.REJECTED, "tutor_response_too_long"
        if len(proposal.response.strip()) < 8:
            return ProposalValidationStatus.REJECTED, "tutor_response_too_short"
        return ProposalValidationStatus.ACCEPTED, "accepted"

    def _fallback_tutor_proposal(
        self,
        strategy: TutoringStrategy,
        node_id: str,
        evidence_signal: str,
        *,
        base_message: str | None = None,
        reason_code: str,
    ) -> BoundedTutorProposal:
        """Build a deterministic bounded proposal for rule/fallback paths.

        Args:
            strategy: EDF-selected tutoring strategy.
            node_id: Current grounded concept.
            evidence_signal: Safe current-turn signal.
            base_message: Optional remediation prompt already rendered by the
                caller.
            reason_code: Safe fallback reason code.

        Returns:
            Safe proposal carrying the deterministic final response and summary.

        Rationale:
            Rule fallback remains explicit in the trace so manual experiments do
            not mistake deterministic baseline behavior for accepted agentic LLM
            generation.
        """
        prompt = self._base_tutor_prompt(node_id)
        message = base_message or rule_tutor_message(strategy, node_id, prompt, self.curriculum)
        label = self.curriculum.nodes[node_id].label
        move = {
            "unknown": "scaffold",
            "too_detailed": "scope_recalibration",
            "too_difficult": "scope_recalibration",
        }.get(evidence_signal, strategy.value)
        return BoundedTutorProposal(
            response=message,
            pedagogical_move=move,
            summary=f"{reason_code}: {strategy.value} grounded on {label}",
            node_id=node_id,
            strategy=strategy.value,
            evidence_signal=evidence_signal,
            source="rule",
        )

    def _base_tutor_prompt(self, node_id: str) -> str:
        """Return the stable learning prompt for tutor rendering.

        Tutor responses are persisted as ``current_prompt`` for continuity, so
        repeated failures must render from the active task or diagnostic prompt
        instead of wrapping the previously rendered tutor message.
        """
        if self.state.current_step_id:
            for step in self.curriculum.task_steps:
                if step.get("step_id") == self.state.current_step_id and step.get("node_id") == node_id:
                    return step.get("prompt", self.state.current_prompt)
        if node_id in self.curriculum.diagnostics:
            return self.curriculum.diagnostics[node_id].prompt
        return self.state.current_prompt

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


def _rule_intake_semantic_signal(answer: str) -> IntakeSemanticSignal:
    """Return a conservative offline semantic signal for explicit corrections.

    This fallback intentionally handles only high-precision correction language.
    Rich interpretation belongs to ``LlmAdapter.classify_intake_semantics`` so
    the rule path does not become an ever-growing hard-coded language parser.
    """
    normalized = answer.strip()
    patterns = (
        r"(?:我說錯了|說錯了|其實是|應該是|改成|換成)(?P<topic>.+)",
        r"不是.+?是(?P<topic>.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        topic = match.group("topic").strip(" ，。,.：:「」")
        topic = re.sub(r"^(?:是|為|成為)", "", topic).strip(" ，。,.：:「」")
        if topic:
            return IntakeSemanticSignal(
                intent="topic_revision",
                confidence=0.78,
                reason_code="explicit_correction_rule",
                new_topic=topic[:100],
            )
    return IntakeSemanticSignal(
        intent="normal_answer",
        confidence=0.55,
        reason_code="rule_no_revision",
    )


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
