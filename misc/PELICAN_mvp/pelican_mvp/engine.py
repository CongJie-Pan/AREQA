"""The observable PELICAN state machine used by the CLI and tests."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .curriculum import CURRICULUMS
from .agents import (
    AgentExecutionContext,
    AgentExecutionResult,
    CapabilityPolicy,
    CapabilityRegistry,
    CapabilityRequest,
    DiagnosisAgent,
    DialogueActAgent,
    FastTutorAgent,
    IntakeAgent,
    LearningCapability,
    LearningManagerAction,
    LearningManagerDecision,
    LearningManagerOrchestrator,
    LearningManagerTurnContext,
    PolicyAgent,
    SkillAgent,
    SkillAgentInput,
    SlowSimulatorAgent,
    StateAgent,
    repair_capability_policy,
)
from .diagnosis import apply_diagnostic_result, classify_response, diagnostic_for, next_diagnostic_node, remediation_signal
from .domain_skill import DomainCategory
from .llm import IntakeSemanticSignal, LlmAdapter, LlmUnavailable
from .models import (
    ActivityEvent,
    AgentProposal,
    AgentRole,
    BoundedTutorProposal,
    DialogueControlDecision,
    DialogueActSignal,
    KnowledgeStatus,
    LearnerDialogueAct,
    LearnerIntakeProfile,
    LearnerProgressNode,
    LearnerProgressSnapshot,
    LearningIntent,
    MethodologyEvent,
    MethodologyEventType,
    MethodologyRef,
    MethodologyStage,
    MethodologyStatus,
    OrchestrationTraceRecord,
    PlanSource,
    ProposalValidationStatus,
    ResponseCategory,
    SessionState,
    TutoringContext,
    TurnInterpretation,
    TurnOutcome,
    TurnRecord,
    TutoringStrategy,
)
from typing import Any
from .state_store import StateStore
from .tutoring import rule_tutor_message, select_strategy, strategy_for_dialogue_act, strategy_for_remediation_signal
from .planner import LearningPlanner
from .edf_simulator import EdfSimulator
from .learning_memory import LearningMemorySimulator
from .curriculum import Curriculum
from .observability import log_event
from .progress import record_progress
from .skill_generator import DomainSkillGenerator


MAX_ACTIVITY_LOG = 16
MAX_METHODOLOGY_EVENTS = 64
MAX_AGENT_PROPOSALS = 48
MAX_ORCHESTRATION_TRACE = 32


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
        self.dialogue_act_agent = DialogueActAgent()
        self.intake_agent = IntakeAgent()
        self.skill_agent = SkillAgent(DomainSkillGenerator(self.llm))
        self.diagnosis_agent = DiagnosisAgent(self.llm)
        self.state_agent = StateAgent()
        self.fast_tutor_agent = FastTutorAgent(self.llm)
        self.slow_simulator_agent = SlowSimulatorAgent(self.llm)
        self.edf = EdfSimulator()
        self.policy_agent = PolicyAgent(self.edf, self.llm)
        self.memory = LearningMemorySimulator()
        self._applied_orchestration_keys: set[str] = set()
        self.learning_capabilities = self._build_learning_capabilities()
        self.learning_manager_orchestrator = LearningManagerOrchestrator(
            self.llm,
            capability_names=self.learning_capabilities.names(),
            capability_policies=self.learning_capabilities.policy_manifest(),
        )

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
        decision = self._orchestrate_current_turn(answer)
        orchestrated = self._dispatch_orchestrator_decision(answer, decision)
        if orchestrated is not None:
            return orchestrated
        return self._legacy_phase_handler(answer, decision.turn_interpretation)

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

    def _legacy_phase_handler(
        self,
        answer: str,
        turn_interpretation: TurnInterpretation | None = None,
    ) -> TurnOutcome:
        """Run the pre-orchestrator phase handler for exact fallback behavior.

        Args:
            answer: Current learner answer. This is passed only to legacy
                handlers and is never included in structured logs.
            turn_interpretation: Optional safe Learning Manager interpretation
                that guides diagnosis and tutor response without owning state
                mutation.

        Returns:
            The same outcome the engine would have produced before
            ``LearningManagerOrchestrator`` was introduced.
        """
        if self.state.phase == "onboarding":
            return self._handle_onboarding(answer)
        if self.state.phase == "diagnosis":
            return self._handle_diagnostic(answer, turn_interpretation=turn_interpretation)
        return self._handle_tutoring(answer, turn_interpretation=turn_interpretation)

    def _build_learning_capabilities(self) -> CapabilityRegistry:
        """Create the engine-owned manifest of orchestratable capabilities.

        The registry stores capability metadata and policy boundaries. Concrete
        state mutation still happens only in ``_dispatch_orchestrator_decision``
        after the engine validates phase legality and the current turn snapshot.
        """
        registry = CapabilityRegistry()
        registry.register(
            LearningCapability(
                name="conversation_control",
                allowed_policies=frozenset({CapabilityPolicy.NONE}),
                can_write_mastery=False,
                emits_learner_text=True,
                description="Handle social or meta-conversation turns without advancing the learning pipeline.",
            )
        )
        registry.register(
            LearningCapability(
                name="onboarding_intake",
                allowed_policies=frozenset({CapabilityPolicy.WRITE_PROPOSED}),
                can_write_mastery=False,
                emits_learner_text=True,
                description="Advance topic, goal, or level onboarding through engine-owned intake handlers.",
            )
        )
        registry.register(
            LearningCapability(
                name="diagnose_answer",
                allowed_policies=frozenset({CapabilityPolicy.WRITE_PROPOSED}),
                can_write_mastery=True,
                emits_learner_text=True,
                description="Classify the active learner answer and update mastery only after engine validation.",
            )
        )
        registry.register(
            LearningCapability(
                name="clarify_current_prompt",
                allowed_policies=frozenset({CapabilityPolicy.NONE, CapabilityPolicy.SPECIALIST}),
                can_write_mastery=False,
                emits_learner_text=True,
                description="Answer a learner clarification without recording mastery evidence.",
            )
        )
        registry.register(
            LearningCapability(
                name="tutor_response",
                allowed_policies=frozenset({CapabilityPolicy.SPECIALIST}),
                can_write_mastery=False,
                emits_learner_text=True,
                description="Generate a teaching response through existing tutor agents.",
            )
        )
        registry.register(
            LearningCapability(
                name="edf_policy",
                allowed_policies=frozenset({CapabilityPolicy.SPECIALIST}),
                can_write_mastery=False,
                emits_learner_text=False,
                description="Select an EDF-informed tutoring policy.",
            )
        )
        registry.register(
            LearningCapability(
                name="slow_simulator",
                allowed_policies=frozenset({CapabilityPolicy.SPECIALIST}),
                can_write_mastery=False,
                emits_learner_text=True,
                description="Run slow teaching-strategy simulation for complex tutor-response choices.",
            )
        )
        registry.register(
            LearningCapability(
                name="resume_pipeline",
                allowed_policies=frozenset({CapabilityPolicy.READ, CapabilityPolicy.SPECIALIST}),
                can_write_mastery=False,
                emits_learner_text=True,
                description="Resume the current legal pipeline prompt without learner-evidence writes.",
            )
        )
        return registry

    def _learning_manager_turn_context(self, answer: str) -> LearningManagerTurnContext:
        """Build the immutable turn snapshot consumed by the orchestrator.

        Args:
            answer: Raw current learner turn used by the model only for
                interpretation. The returned context can serialize this text for
                the LLM, but safe logs and decision metadata must not include it.

        Returns:
            ``LearningManagerTurnContext`` tied to the current turn id, cycle id,
            phase, prompt source, active node, and bounded memory signals.
        """
        pending_intake_stage = self._pending_intake_stage()
        expected_shape = self._expected_response_shape(pending_intake_stage)
        prompt_kind = self.state.current_prompt_source or "unknown"
        pending_prompt_kind = f"onboarding_{pending_intake_stage}" if pending_intake_stage else prompt_kind
        snapshot_id = ":".join(
            (
                self.state.turn_id or "turn",
                self.state.cycle_id or "cycle",
                self.state.phase,
                self.state.current_node_id or "none",
                pending_prompt_kind,
            )
        )
        return LearningManagerTurnContext(
            snapshot_id=snapshot_id,
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            phase=self.state.phase,
            current_node_id=self.state.current_node_id,
            current_prompt_kind=prompt_kind,
            expected_response_shape=expected_shape,
            edf_state=self.state.edf_snapshot.learner_state,
            edf_policy=self.state.edf_snapshot.pedagogical_strategy,
            recent_safe_signals=self.memory.recent_safe_signals(self.state),
            recent_messages=self._recent_turn_messages(),
            last_assistant_prompt=self._last_assistant_prompt(),
            pending_intake_stage=pending_intake_stage,
            pending_prompt_kind=pending_prompt_kind,
            pending_choices=self._pending_intake_choices(pending_intake_stage),
            learner_text=answer,
        )

    def _pending_intake_stage(self) -> str | None:
        """Return the onboarding slot that is currently waiting for a learner answer."""
        if self.state.phase != "onboarding":
            return None
        turns = self.state.intake_profile.intake_turns
        if turns <= 0:
            return "topic"
        if turns == 1:
            return "goal"
        if turns == 2:
            return "level"
        return None

    def _expected_response_shape(self, pending_intake_stage: str | None) -> str:
        """Return a safe high-level response-shape label for orchestration."""
        if self.state.current_expected_answer:
            return "active_answer"
        if pending_intake_stage == "topic":
            return "learning_topic_or_social"
        if pending_intake_stage == "goal":
            return "goal_choice_revision_or_no_preference"
        if pending_intake_stage == "level":
            return "experience_level_or_no_preference"
        return "control_or_freeform"

    def _recent_turn_messages(self) -> tuple[dict[str, str], ...]:
        """Return bounded recent visible turns for current-turn interpretation only."""
        messages: list[dict[str, str]] = []
        for entry in self.state.transcript[-6:]:
            messages.append({"role": entry.role[:32], "text": entry.text[:800]})
        return tuple(messages)

    def _last_assistant_prompt(self) -> str:
        """Return the latest assistant-visible prompt text without logging it."""
        for entry in reversed(self.state.transcript):
            if entry.role == "assistant" and entry.text:
                return entry.text[:1200]
        return self.state.current_prompt[:1200]

    def _pending_intake_choices(self, pending_intake_stage: str | None) -> tuple[str, ...]:
        """Return safe option labels for the current onboarding prompt."""
        if pending_intake_stage == "goal":
            return ("military", "economy", "society", "politics", "no_preference")
        if pending_intake_stage == "level":
            return ("beginner", "intermediate", "advanced", "no_preference")
        return ()

    def _orchestrate_current_turn(self, answer: str) -> LearningManagerDecision:
        """Return an orchestrator proposal or deterministic legacy fallback.

        Rule mode keeps historical behavior and avoids accidental live model
        calls during local tests. LLM mode uses the orchestrator, and all model
        failures are converted to fallback by the orchestrator contract.
        """
        context = self._learning_manager_turn_context(answer)
        if self.state.mode != "llm":
            conversation_reason = _conversation_control_reason(answer)
            if conversation_reason:
                return LearningManagerDecision(
                    action=LearningManagerAction.CALL_CAPABILITY,
                    capability="conversation_control",
                    policy=CapabilityPolicy.NONE,
                    target_phase=self.state.phase,
                    confidence=0.95,
                    reason_code=conversation_reason,
                    proposal_source="fallback",
                    snapshot_id=context.snapshot_id,
                )
            return LearningManagerDecision(
                action=LearningManagerAction.FALLBACK_LEGACY_PIPELINE,
                capability="",
                policy=CapabilityPolicy.NONE,
                target_phase=self.state.phase,
                confidence=0.0,
                reason_code="rule_mode_legacy",
                proposal_source="fallback",
                snapshot_id=context.snapshot_id,
            )
        if getattr(self.learning_manager_orchestrator, "llm", self.llm) is not self.llm:
            self.learning_manager_orchestrator = LearningManagerOrchestrator(
                self.llm,
                capability_names=self.learning_capabilities.names(),
                capability_policies=self.learning_capabilities.policy_manifest(),
            )
        return self.learning_manager_orchestrator.interpret_turn(context)

    def _validate_orchestrator_decision(
        self,
        decision: LearningManagerDecision,
        *,
        expected_snapshot_id: str,
    ) -> CapabilityRequest | None:
        """Validate an orchestrator proposal before any capability dispatch.

        Args:
            decision: Read-only proposal returned by the orchestrator.
            expected_snapshot_id: Snapshot id from the current immutable turn.

        Returns:
            A validated capability request, or ``None`` when the decision must
            fall back to the legacy pipeline.
        """
        if decision.snapshot_id != expected_snapshot_id:
            return None
        if decision.action in {
            LearningManagerAction.FALLBACK_LEGACY_PIPELINE,
            LearningManagerAction.REJECT_ILLEGAL_ACTION,
        }:
            return None
        if decision.action in {LearningManagerAction.RESUME_PIPELINE, LearningManagerAction.CONTINUE_PIPELINE}:
            return CapabilityRequest(
                name="resume_pipeline",
                policy=CapabilityPolicy.READ,
                turn_id=self.state.turn_id,
                cycle_id=self.state.cycle_id,
                target_phase=self.state.phase,
            )
        if decision.action is LearningManagerAction.ANSWER_DIRECTLY:
            return CapabilityRequest(
                name="clarify_current_prompt",
                policy=CapabilityPolicy.NONE,
                turn_id=self.state.turn_id,
                cycle_id=self.state.cycle_id,
                target_phase=decision.target_phase,
            )
        if decision.action in {LearningManagerAction.CALL_CAPABILITY, LearningManagerAction.DELEGATE_CAPABILITY}:
            return CapabilityRequest(
                name=decision.capability,
                policy=decision.policy,
                turn_id=self.state.turn_id,
                cycle_id=self.state.cycle_id,
                target_phase=decision.target_phase,
            )
        return None

    def _dispatch_orchestrator_decision(
        self,
        answer: str,
        decision: LearningManagerDecision,
    ) -> TurnOutcome | None:
        """Apply a validated orchestration decision through engine-owned paths.

        Args:
            answer: Current learner answer. It is passed only to existing
                handlers and not emitted as structured metadata.
            decision: Read-only orchestrator proposal.

        Returns:
            ``TurnOutcome`` when a safe orchestrated path handled the turn, or
            ``None`` to execute exact legacy fallback.
        """
        context = self._learning_manager_turn_context(answer)
        request = self._validate_orchestrator_decision(decision, expected_snapshot_id=context.snapshot_id)
        if request is None:
            if decision.action is not LearningManagerAction.FALLBACK_LEGACY_PIPELINE:
                self._record_orchestration_trace(decision, outcome="rejected")
                log_event(
                    "pelican_learning_orchestrator_action_rejected",
                    learner_id=self.state.learner_id,
                    phase=self.state.phase,
                    turn_id=self.state.turn_id,
                    cycle_id=self.state.cycle_id,
                    action=decision.action.value,
                    capability=decision.capability,
                    policy=decision.policy.value,
                    target_phase=decision.target_phase,
                    outcome="rejected",
                    reason_code=decision.reason_code,
                )
            else:
                self._record_orchestration_trace(decision, outcome="fallback")
            return None
        if request.name == "conversation_control" and self._should_guard_conversation_control(answer):
            self._record_orchestration_trace(
                decision,
                outcome="rejected",
                reason_code="pending_pipeline_answer_guard",
            )
            log_event(
                "pelican_learning_orchestrator_action_rejected",
                learner_id=self.state.learner_id,
                phase=self.state.phase,
                turn_id=self.state.turn_id,
                cycle_id=self.state.cycle_id,
                action=decision.action.value,
                capability=decision.capability,
                policy=decision.policy.value,
                target_phase=decision.target_phase,
                outcome="rejected",
                reason_code="pending_pipeline_answer_guard",
            )
            return None
        idempotency_key = f"{self.state.turn_id}:{decision.snapshot_id}:{decision.action.value}:{decision.capability}"
        if idempotency_key in self._applied_orchestration_keys:
            self._record_orchestration_trace(
                decision,
                outcome="rejected",
                reason_code="duplicate_orchestrator_decision",
            )
            log_event(
                "pelican_learning_orchestrator_action_rejected",
                learner_id=self.state.learner_id,
                phase=self.state.phase,
                turn_id=self.state.turn_id,
                cycle_id=self.state.cycle_id,
                action=decision.action.value,
                capability=decision.capability,
                policy=decision.policy.value,
                target_phase=decision.target_phase,
                idempotency_key=idempotency_key,
                outcome="rejected",
                reason_code="duplicate_orchestrator_decision",
            )
            return None
        capability_result = self.learning_capabilities.validate(request)
        if not capability_result.accepted and capability_result.reason_code == "policy_denied":
            repair = repair_capability_policy(
                request.name,
                request.policy,
                self.learning_capabilities.policy_manifest(),
            )
            if repair.accepted and repair.repaired:
                log_event(
                    "pelican_learning_capability_policy_repaired",
                    learner_id=self.state.learner_id,
                    phase=self.state.phase,
                    turn_id=self.state.turn_id,
                    cycle_id=self.state.cycle_id,
                    capability=repair.capability,
                    policy=repair.effective_policy.value,
                    target_phase=request.target_phase,
                    outcome="accepted",
                    reason_code=repair.reason_code,
                    requested_policy=repair.requested_policy.value,
                    allowed_policy_count=repair.allowed_policy_count,
                )
                request = CapabilityRequest(
                    name=request.name,
                    policy=repair.effective_policy,
                    turn_id=request.turn_id,
                    cycle_id=request.cycle_id,
                    target_phase=request.target_phase,
                    payload=request.payload,
                )
                capability_result = self.learning_capabilities.validate(request)
        if not capability_result.accepted:
            self._record_orchestration_trace(
                decision,
                outcome="rejected",
                reason_code=capability_result.reason_code,
            )
            return None
        if capability_result.can_write_mastery and request.policy is not CapabilityPolicy.WRITE_PROPOSED:
            self._record_orchestration_trace(
                decision,
                outcome="rejected",
                reason_code="mastery_write_requires_write_proposed",
            )
            return None
        self._applied_orchestration_keys.add(idempotency_key)
        if not capability_result.can_write_mastery:
            log_event(
                "pelican_learning_capability_no_write_guarded",
                learner_id=self.state.learner_id,
                phase=self.state.phase,
                turn_id=self.state.turn_id,
                cycle_id=self.state.cycle_id,
                action=decision.action.value,
                capability=request.name,
                policy=request.policy.value,
                target_phase=request.target_phase,
                idempotency_key=idempotency_key,
                outcome="guarded",
                reason_code="no_mastery_write_capability",
            )
        if request.name == "conversation_control":
            outcome = self._handle_conversation_control(answer, decision.reason_code)
            self._log_orchestrated_capability_completed(request, outcome, idempotency_key)
            self._record_orchestration_trace(decision, outcome="accepted")
            log_event(
                "pelican_learning_conversation_control_handled",
                learner_id=self.state.learner_id,
                phase=self.state.phase,
                turn_id=self.state.turn_id,
                cycle_id=self.state.cycle_id,
                action=decision.action.value,
                capability=request.name,
                policy=request.policy.value,
                target_phase=request.target_phase,
                idempotency_key=idempotency_key,
                outcome="accepted",
                reason_code=decision.reason_code,
            )
            return outcome
        if request.name == "onboarding_intake":
            if self.state.phase != "onboarding":
                self._record_orchestration_trace(
                    decision,
                    outcome="rejected",
                    reason_code="onboarding_intake_wrong_phase",
                )
                return None
            outcome = self._handle_onboarding(answer)
            self._log_orchestrated_capability_completed(request, outcome, idempotency_key)
            self._record_orchestration_trace(decision, outcome="accepted")
            return outcome
        if request.name == "diagnose_answer":
            if self.state.phase == "diagnosis":
                outcome = self._handle_diagnostic(answer, turn_interpretation=decision.turn_interpretation)
                self._log_orchestrated_capability_completed(request, outcome, idempotency_key)
                self._record_orchestration_trace(decision, outcome="accepted")
                return outcome
            if self.state.phase == "tutoring":
                outcome = self._handle_tutoring(answer, turn_interpretation=decision.turn_interpretation)
                self._log_orchestrated_capability_completed(request, outcome, idempotency_key)
                self._record_orchestration_trace(decision, outcome="accepted")
                return outcome
            return None
        if request.name == "clarify_current_prompt":
            if not self.state.current_node_id or not self.curriculum:
                return None
            dialogue_outcome = self._route_dialogue_act(
                answer,
                self.state.current_node_id,
                turn_interpretation=decision.turn_interpretation,
                force=True,
            )
            if dialogue_outcome is not None:
                self._log_orchestrated_capability_completed(request, dialogue_outcome, idempotency_key)
                self._record_orchestration_trace(decision, outcome="accepted")
                return dialogue_outcome
            return None
        if request.name == "tutor_response":
            if not self.state.current_node_id or not self.curriculum:
                return None
            strategy = (
                self.state.strategy_decision.selected_strategy
                if self.state.strategy_decision.selected_strategy
                else TutoringStrategy.EXPLANATION
            )
            (
                message,
                source,
                _validation_status,
                proposal_reason,
                _pedagogical_move,
                _display_summary,
                tutor_result,
            ) = self._tutor_message(
                strategy,
                self.state.current_node_id,
                evidence_signal=decision.turn_interpretation.understanding_status or decision.reason_code,
                learner_answer=answer,
                tutor_role=AgentRole.FAST_TUTOR_AGENT,
                turn_interpretation=decision.turn_interpretation,
            )
            self._record_agent_result(
                tutor_result,
                node_id=self.state.current_node_id,
                strategy=strategy.value,
                skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
            )
            self._record_methodology_event(
                MethodologyEventType.PIPELINE_STAGE,
                stage=MethodologyStage.TUTOR_RESPONSE,
                input_ref=MethodologyRef("turn_interpretation", decision.reason_code, "orchestrated tutor response"),
                output_ref=MethodologyRef("tutor_message", source, "tutor response"),
                node_id=self.state.current_node_id,
                strategy=strategy.value,
                reason_code=proposal_reason,
            )
            self.state.current_prompt = message
            self.state.current_prompt_source = source
            self.store.save(self.state)
            outcome = TurnOutcome(
                message,
                self.state.current_node_id,
                None,
                strategy,
                (),
                proposal_reason,
            )
            self._log_orchestrated_capability_completed(request, outcome, idempotency_key)
            self._record_orchestration_trace(decision, outcome="accepted")
            return outcome
        if request.name == "resume_pipeline":
            outcome = self.start()
            self._log_orchestrated_capability_completed(request, outcome, idempotency_key)
            self._record_orchestration_trace(decision, outcome="accepted")
            return outcome
        return None

    def _should_guard_conversation_control(self, answer: str) -> bool:
        """Reject no-write control when the learner is answering a pending pipeline prompt."""
        if _conversation_control_reason(answer):
            return False
        if self._pending_intake_stage() is not None:
            return True
        return bool(self.state.current_expected_answer)

    def _record_orchestration_trace(
        self,
        decision: LearningManagerDecision,
        *,
        outcome: str,
        reason_code: str | None = None,
    ) -> None:
        """Append one safe Learning Manager trace row and emit a matching log.

        The stable log event is ``pelican_learning_orchestration_trace_recorded``.
        It contains only bounded orchestration labels and correlation IDs; raw
        learner text, prompts, and model output remain outside this boundary.
        """
        record = OrchestrationTraceRecord(
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            phase=self.state.phase,
            action=decision.action.value,
            capability=decision.capability,
            policy=decision.policy.value,
            target_phase=decision.target_phase,
            confidence_bucket=_orchestration_confidence_bucket(decision.confidence),
            proposal_source=decision.proposal_source,
            reason_code=reason_code or decision.reason_code,
            outcome=outcome,
            learner_act=decision.turn_interpretation.learner_act,
            understanding_status=decision.turn_interpretation.understanding_status,
            teaching_move=decision.turn_interpretation.teaching_move,
        )
        self.state.orchestration_trace.append(record)
        if len(self.state.orchestration_trace) > MAX_ORCHESTRATION_TRACE:
            self.state.orchestration_trace = self.state.orchestration_trace[-MAX_ORCHESTRATION_TRACE:]
        self.store.save(self.state)
        log_event(
            "pelican_learning_orchestration_trace_recorded",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            action=record.action,
            capability=record.capability,
            policy=record.policy,
            target_phase=record.target_phase,
            confidence_bucket=record.confidence_bucket,
            proposal_source=record.proposal_source,
            outcome=record.outcome,
            reason_code=record.reason_code,
            learner_act=record.learner_act,
            understanding_status=record.understanding_status,
            teaching_move=record.teaching_move,
        )

    def _handle_conversation_control(self, learner_text: str, reason_code: str) -> TurnOutcome:
        """Generate a no-write conversational control response.

        Args:
            learner_text: Current learner turn used only for bounded response
                generation. It must not be logged or persisted by this path.
            reason_code: Safe stable reason supplied by the orchestrator or the
                deterministic rule-mode classifier.

        Returns:
            Learner-facing outcome that preserves the current phase, intake
            profile, mastery evidence, and active learning state.

        Side Effects:
            None. The caller owns structured logging so this method cannot
            accidentally emit learner text or mutate session state.
        """
        message_source = "fallback"
        message = ""
        try:
            generated = self.llm.conversation_control_response(
                learner_text=learner_text,
                phase=self.state.phase,
                current_topic=self.state.intake_profile.topic,
                current_prompt_kind=self.state.current_prompt_source or "unknown",
                reason_code=reason_code,
            )
            if generated:
                message = generated
                message_source = "llm"
        except LlmUnavailable:
            message_source = "fallback"
        if not message:
            message = "我在。你可以直接告訴我想學什麼，或先說你想確認哪一段。"
        log_event(
            "pelican_learning_conversation_control_response_ready",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            capability="conversation_control",
            policy=CapabilityPolicy.NONE.value,
            outcome=message_source,
            reason_code=reason_code,
        )
        return TurnOutcome(
            message,
            self.state.current_node_id,
            None,
            None,
            (),
            reason_code,
        )

    def _log_orchestrated_capability_completed(
        self,
        request: CapabilityRequest,
        outcome: TurnOutcome,
        idempotency_key: str,
    ) -> None:
        """Emit safe completion metadata for an engine-dispatched capability.

        The event intentionally records labels and correlation IDs only. It does
        not include the learner answer, tutor message, prompt, or model output.
        """
        log_event(
            "pelican_learning_capability_completed",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            turn_id=self.state.turn_id,
            cycle_id=self.state.cycle_id,
            capability=request.name,
            policy=request.policy.value,
            target_phase=request.target_phase,
            idempotency_key=idempotency_key,
            outcome="accepted",
            category=outcome.category.value if outcome.category else None,
            strategy=outcome.strategy.value if outcome.strategy else None,
            reason_code=outcome.next_reason,
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
        if profile.domain_category == DomainCategory.UNKNOWN.value or profile.model_route == "clarify_before_routing":
            self._record_activity(
                "domain_clarification_needed",
                "需要確認學習領域",
                detail=profile.domain_category or "unknown",
            )
            self.state.intake_profile = LearnerIntakeProfile(
                topic=profile.topic,
                goal_summary=profile.goal_summary,
                intent=LearningIntent.UNKNOWN,
                level_hint="unknown",
                domain_category=DomainCategory.UNKNOWN.value,
                model_route="clarify_before_routing",
                intake_turns=0,
            )
            self.store.save(self.state)
            record_progress(
                self.state.learner_id,
                "domain_clarification_needed",
                "需要確認學習領域",
                status="done",
                detail="unknown_domain",
            )
            return TurnOutcome(
                "我目前還無法安全判斷這個主題應該使用哪個領域的 Skill。"
                "請再用一句話描述你想學的主題，例如「中國哲學中的道家思想」或「春秋戰國的諸子百家」。",
                None,
                None,
                None,
                (),
                "未知領域需要重新確認主題",
            )
        record_progress(
            self.state.learner_id,
            "skill_generation",
            "建立領域 Skill",
            status="processing",
            detail=profile.model_route or profile.domain_category or "runtime",
        )
        skill_proposal = self.skill_agent.propose_skill(
            SkillAgentInput(profile),
            context=self._agent_execution_context(),
        )
        record_progress(
            self.state.learner_id,
            "skill_generation",
            "建立領域 Skill",
            status="done",
            detail=skill_proposal.skill.skill_id,
        )
        record_progress(
            self.state.learner_id,
            "skill_validation",
            "驗證 Skill 結構",
            status="processing",
            detail=skill_proposal.route,
        )
        plan = self.planner.compile_validated_skill(skill_proposal.skill, profile, skill_proposal.route)
        record_progress(
            self.state.learner_id,
            "skill_validation",
            "驗證 Skill 結構",
            status="done",
            detail=plan.skill_lifecycle or "validated",
        )
        record_progress(
            self.state.learner_id,
            "plan_compiled",
            "編譯知識地圖",
            status="done",
            detail=f"{len(plan.nodes)} nodes",
        )
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
        record_progress(
            self.state.learner_id,
            "diagnostic_selected",
            "準備診斷問題",
            status="processing",
            detail=plan.skill_id or "learning_plan",
        )
        outcome = self._present_next_diagnostic()
        record_progress(
            self.state.learner_id,
            "diagnostic_selected",
            "準備診斷問題",
            status="done",
            detail=self.state.current_node_id or "selected",
        )
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

    def _handle_diagnostic(
        self,
        answer: str,
        *,
        turn_interpretation: TurnInterpretation | None = None,
    ) -> TurnOutcome:
        """Handle a diagnostic answer with generated-skill remediation precedence."""
        node_id = self._require_current_node()
        signal = remediation_signal(answer)
        # Remediation signals are control evidence, not mastery evidence; handle
        # them before normal answer classification can advance successor-first.
        if self.state.plan_source is PlanSource.GENERATED and signal in {"too_detailed", "too_difficult"}:
            return self._handle_scope_mismatch(answer, signal)
        if self.state.plan_source is PlanSource.GENERATED and signal == "too_easy":
            return self._handle_acceleration_request(answer)
        dialogue_outcome = self._route_dialogue_act(answer, node_id, turn_interpretation=turn_interpretation)
        if dialogue_outcome is not None:
            return dialogue_outcome
        category = self._category_with_turn_interpretation(self._classify(answer), turn_interpretation)
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
        if self._uses_generated_skill_plan() and category in (
            ResponseCategory.INCORRECT,
            ResponseCategory.PARTIAL_CORRECT,
            ResponseCategory.DIFFICULTY,
        ):
            return self._remediate_current_skill_diagnostic(
                answer,
                category,
                changes,
                turn_interpretation=turn_interpretation,
            )
        self.store.save(self.state)
        next_outcome = self._present_next_diagnostic()
        
        category_msg_map = {
            ResponseCategory.CORRECT: "答對了，看來你對這個概念有基本掌握！",
            ResponseCategory.PARTIAL_CORRECT: "你抓到部分線索了，我們把缺口補起來。",
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
        *,
        turn_interpretation: TurnInterpretation | None = None,
    ) -> TurnOutcome:
        """Keep generated-skill learners on the current concept after missed evidence."""
        node_id = self._require_current_node()
        label = self.curriculum.nodes[node_id].label
        strategy = (
            TutoringStrategy.SIMPLIFICATION
            if category is ResponseCategory.DIFFICULTY
            else TutoringStrategy.CORRECTION
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
        base_message = self._interpretation_remediation_prompt(node_id, label, turn_interpretation)
        if base_message is None:
            base_message = self._remediation_prompt(node_id, label, category=category)
        (
            message,
            source,
            _validation_status,
            proposal_reason,
            _pedagogical_move,
            _display_summary,
            tutor_result,
        ) = self._tutor_message(
            strategy,
            node_id,
            evidence_signal=category.value,
            learner_answer=answer,
            base_message=base_message,
            tutor_role=AgentRole.FAST_TUTOR_AGENT,
            turn_interpretation=turn_interpretation,
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
            input_ref=MethodologyRef("strategy", strategy.value, "skill remediation strategy"),
            output_ref=MethodologyRef("tutor_message", source, "skill remediation response"),
            node_id=node_id,
            strategy=strategy.value,
            reason_code=proposal_reason,
        )
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
            learner_answer=answer,
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
        strategy = strategy_for_remediation_signal("unknown") or TutoringStrategy.EXPLANATION
        self._record(answer, category, None, changes)
        self._refresh_learning_context(answer, category, "unknown")
        prerequisite_id = self.curriculum.nodes[node_id].prerequisites[0] if self.curriculum.nodes[node_id].prerequisites else node_id
        self.state.phase = "tutoring"
        self.state.current_node_id = prerequisite_id
        self.state.current_step_id = None
        if prerequisite_id in self.curriculum.diagnostics:
            diagnostic = self.curriculum.diagnostics[prerequisite_id]
            self.state.current_expected_answer = diagnostic.expected_answer
            self.state.current_prompt_source = diagnostic.source
        base_message = self._scaffold_prompt(
            prerequisite_id,
            self.curriculum.nodes[prerequisite_id].label,
        )
        message, source, validation_status, proposal_reason, pedagogical_move, display_summary, tutor_result = self._tutor_message(
            strategy,
            prerequisite_id,
            evidence_signal="unknown",
            learner_answer=answer,
            base_message=base_message,
            tutor_role=AgentRole.FAST_TUTOR_AGENT,
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
            "unknown：先直接講解並 scaffold prerequisite，不跳到下一個診斷題",
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

    def _transition_to_next_diagnostic_message(
        self,
        completed_node_id: str,
        next_outcome: TurnOutcome,
        *,
        learner_answer: str,
        turn_interpretation: TurnInterpretation | None = None,
    ) -> tuple[str, str, str, AgentExecutionResult]:
        """Generate a concept bridge before showing the next diagnostic prompt.

        Args:
            completed_node_id: Knowledge node just confirmed as mastered.
            next_outcome: Diagnostic outcome produced by successor-first
                selection. Its message is the next learner-facing question.
            learner_answer: Latest learner answer passed only to the tutor model
                for acknowledgement grounding. It is not written to safe trace
                metadata by this helper.
            turn_interpretation: Learning Manager interpretation to preserve
                single-owner turn semantics through transition rendering.

        Returns:
            Tuple of bridge message, source, safe reason code, and tutor proposal
            result for methodology tracing.

        Side Effects:
            Emits the same bounded tutor proposal logs as other tutor responses
            through ``_tutor_message``. Raw learner text and prompts are not
            emitted as structured metadata.
        """
        completed_label = self.curriculum.nodes[completed_node_id].label
        next_label = (
            self.curriculum.nodes[next_outcome.node_id].label
            if next_outcome.node_id and next_outcome.node_id in self.curriculum.nodes
            else "下一個知識點"
        )
        understood = ""
        if turn_interpretation and turn_interpretation.understood_points:
            understood = "、".join(turn_interpretation.understood_points[:2])
        understood_text = understood or f"{completed_label} 的核心因果關係"
        base_message = (
            f"你剛剛抓到的重點是：{understood_text}。\n\n"
            f"這表示「{completed_label}」這個知識點可以先視為理解了。\n\n"
            f"接下來我們把時間往後推，看看它如何銜接到「{next_label}」。"
            "也就是說，前面談的是日本如何建立近代國家的基礎；下一步要看的是，"
            "這個近代國家後來為什麼會走向軍方影響力上升。\n\n"
            f"{next_outcome.message}"
        )
        (
            message,
            source,
            _validation_status,
            reason,
            _pedagogical_move,
            _display_summary,
            tutor_result,
        ) = self._tutor_message(
            TutoringStrategy.CONFIRMATION,
            completed_node_id,
            evidence_signal="correct_transition",
            learner_answer=learner_answer,
            base_message=base_message,
            tutor_role=AgentRole.FAST_TUTOR_AGENT,
            turn_interpretation=turn_interpretation,
        )
        return message, source, reason, tutor_result

    def _handle_tutoring(
        self,
        answer: str,
        *,
        turn_interpretation: TurnInterpretation | None = None,
    ) -> TurnOutcome:
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
        dialogue_outcome = self._route_dialogue_act(answer, node_id, turn_interpretation=turn_interpretation)
        if dialogue_outcome is not None:
            return dialogue_outcome
        category = self._category_with_turn_interpretation(self._classify(answer), turn_interpretation)
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
            evidence_label = (
                "複述直接證據"
                if self.state.plan_source is PlanSource.GENERATED and not step_id
                else "原題直接證據"
            )
            changes.append(f"{self.curriculum.nodes[node_id].label}: mastered（{evidence_label}）")
            self._record(answer, category, TutoringStrategy.CONFIRMATION, changes)
            self._refresh_learning_context(answer, category)
            if self.state.plan_source is PlanSource.GENERATED and not step_id:
                self.state.phase = "diagnosis"
                self.store.save(self.state)
                next_outcome = self._present_next_diagnostic()
                bridge_message, bridge_source, bridge_reason, bridge_result = self._transition_to_next_diagnostic_message(
                    node_id,
                    next_outcome,
                    learner_answer=answer,
                    turn_interpretation=turn_interpretation,
                )
                self._record_agent_result(
                    bridge_result,
                    node_id=node_id,
                    strategy=TutoringStrategy.CONFIRMATION.value,
                    skill_id=self.state.learning_plan.skill_id if self.state.learning_plan else None,
                )
                self._record_methodology_event(
                    MethodologyEventType.PIPELINE_STAGE,
                    stage=MethodologyStage.TUTOR_RESPONSE,
                    input_ref=MethodologyRef("diagnostic_node", next_outcome.node_id or "next", "next diagnostic"),
                    output_ref=MethodologyRef("tutor_message", bridge_source, "concept transition"),
                    node_id=node_id,
                    strategy=TutoringStrategy.CONFIRMATION.value,
                    reason_code=bridge_reason,
                )
                self.state.current_prompt = bridge_message
                self.state.current_prompt_source = bridge_source
                self.store.save(self.state)
                next_outcome = TurnOutcome(
                    bridge_message,
                    next_outcome.node_id,
                    next_outcome.category,
                    next_outcome.strategy,
                    next_outcome.state_changes,
                    next_outcome.next_reason,
                )
                return TurnOutcome(
                    f"說得對，這個知識點可以先視為理解了。\n\n{next_outcome.message}",
                    next_outcome.node_id,
                    category,
                    TutoringStrategy.CONFIRMATION,
                    tuple(changes),
                    "restatement confirmed：回到知識地圖並解鎖下一個知識點",
                )
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
        tutor_role = self._select_tutor_role(reason)
        base_message = self._interpretation_remediation_prompt(
            node_id,
            self.curriculum.nodes[node_id].label,
            turn_interpretation,
        )
        if (
            base_message is None
            and self._is_humanities_plan()
            and (self.state.mode != "llm" or not self.llm.available)
            and category in (
                ResponseCategory.INCORRECT,
                ResponseCategory.PARTIAL_CORRECT,
                ResponseCategory.DIFFICULTY,
            )
        ):
            base_message = self._humanities_explanation_check_prompt(
                node_id,
                self.curriculum.nodes[node_id].label,
                category=category,
            )
        message, source, validation_status, proposal_reason, pedagogical_move, display_summary, tutor_result = self._tutor_message(
            strategy,
            node_id,
            evidence_signal=signal,
            learner_answer=answer,
            base_message=base_message,
            tutor_role=tutor_role,
            turn_interpretation=turn_interpretation,
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

    def _route_dialogue_act(
        self,
        answer: str,
        node_id: str,
        *,
        turn_interpretation: TurnInterpretation | None = None,
        force: bool = False,
    ) -> TurnOutcome | None:
        """Route conversational control turns before mastery diagnosis.

        The dialogue-act layer prevents learner clarification questions from
        being recorded as wrong knowledge evidence. It currently intercepts only
        generated humanities sessions because fixture/STEM compatibility relies
        on the legacy diagnosis path.
        """
        if self.state.plan_source is not PlanSource.GENERATED or not self._is_humanities_plan():
            return None
        if not self._should_route_dialogue_act(turn_interpretation, force=force):
            return None
        if not force and self._is_tentative_answer_to_recent_prompt(answer):
            return None
        interpretation = self.dialogue_act_agent.classify(
            answer,
            current_prompt=self.state.current_prompt,
            previous_tutor_message=self.state.current_prompt,
            node_label=self.curriculum.nodes[node_id].label,
            context=self._agent_execution_context(),
        )
        signal = self._dialogue_signal_from_turn_interpretation(
            turn_interpretation,
            fallback_signal=interpretation.signal,
            node_id=node_id,
        )
        self._record_agent_result(interpretation.result, node_id=node_id)
        decision = self._dialogue_control_decision(signal)
        log_event(
            "pelican_dialogue_control_decided",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            node_id=node_id,
            dialogue_act=decision.act.value,
            should_diagnose=decision.should_diagnose,
            memory_kind=decision.memory_kind,
            decision_confidence=decision.confidence,
            reason_code=decision.reason_code,
        )
        if decision.should_diagnose:
            return None
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.COGNITIVE_DIAGNOSIS,
            input_ref=MethodologyRef("dialogue_act", decision.act.value, "learner dialogue control"),
            output_ref=MethodologyRef("dialogue_control", decision.reason_code, "dialogue control decision"),
            node_id=node_id,
            reason_code=decision.reason_code,
        )
        if decision.act is LearnerDialogueAct.MICRO_CHECK_CONFUSION:
            return self._handle_micro_check_confusion(signal, node_id, decision=decision)
        return self._handle_term_clarification(signal, node_id, decision=decision)

    def _dialogue_signal_from_turn_interpretation(
        self,
        turn_interpretation: TurnInterpretation | None,
        *,
        fallback_signal: DialogueActSignal,
        node_id: str,
    ) -> DialogueActSignal:
        """Promote explicit Learning Manager dialogue acts into routeable signals."""
        if not self._has_meaningful_turn_interpretation(turn_interpretation):
            return fallback_signal
        learner_act = turn_interpretation.learner_act.strip().lower()
        if learner_act == "term_definition_request":
            return DialogueActSignal(
                LearnerDialogueAct.TERM_DEFINITION_REQUEST,
                max(fallback_signal.confidence, 0.86),
                target_text=fallback_signal.target_text or self.curriculum.nodes[node_id].label,
                reason_code=turn_interpretation.reason_code or "learning_manager_term_definition",
            )
        if learner_act == "micro_check_confusion":
            return DialogueActSignal(
                LearnerDialogueAct.MICRO_CHECK_CONFUSION,
                max(fallback_signal.confidence, 0.86),
                target_text=fallback_signal.target_text or self.curriculum.nodes[node_id].label,
                reason_code=turn_interpretation.reason_code or "learning_manager_micro_check",
            )
        if learner_act == "clarification_question" and fallback_signal.act is LearnerDialogueAct.CLARIFICATION_QUESTION:
            return DialogueActSignal(
                fallback_signal.act,
                max(fallback_signal.confidence, 0.86),
                target_text=fallback_signal.target_text,
                reason_code=turn_interpretation.reason_code or fallback_signal.reason_code,
            )
        return fallback_signal

    def _should_route_dialogue_act(
        self,
        turn_interpretation: TurnInterpretation | None,
        *,
        force: bool = False,
    ) -> bool:
        """Return whether the legacy dialogue-act gate may reinterpret the turn.

        Learning Manager is the single owner of turn interpretation when it has
        supplied a meaningful act. DialogueActAgent remains a bounded executor
        for explicit learner clarification/control acts and a compatibility
        fallback when no meaningful Learning Manager interpretation exists.
        """
        if force:
            return True
        if not self._has_meaningful_turn_interpretation(turn_interpretation):
            return True
        learner_act = turn_interpretation.learner_act.strip().lower()
        return learner_act in {
            "clarification_question",
            "term_definition_request",
            "micro_check_confusion",
            "too_hard",
            "too_easy",
            "ready_to_continue",
            "topic_shift",
        }

    def _has_meaningful_turn_interpretation(self, turn_interpretation: TurnInterpretation | None) -> bool:
        """Return whether Learning Manager supplied non-default turn semantics."""
        if turn_interpretation is None:
            return False
        if turn_interpretation.reason_code and turn_interpretation.reason_code != "unknown":
            return True
        if turn_interpretation.understood_points or turn_interpretation.missing_points:
            return True
        if turn_interpretation.understanding_status not in {"", "unknown"}:
            return True
        return turn_interpretation.teaching_move not in {"", "resume_pipeline"}

    def _is_tentative_answer_to_recent_prompt(self, answer: str) -> bool:
        """Detect hedged answers to choice/opinion prompts before dialogue routing.

        In humanities tutoring, learners often answer with uncertainty markers
        and a trailing question mark, such as "I think maybe X?". That is still
        an answer attempt when the active prompt asks what they think or asks
        them to choose among reforms.
        """
        text = answer.strip().lower()
        if not text or not text.endswith(("?", "？")):
            return False
        tentative_markers = (
            "我覺得",
            "我觉得",
            "可能是",
            "應該是",
            "应该是",
            "也許是",
            "也许是",
            "大概是",
            "maybe",
            "i think",
            "probably",
        )
        if not any(marker in text for marker in tentative_markers):
            return False
        prompt = " ".join(
            part
            for part in (
                self.state.current_prompt or "",
                self._last_assistant_prompt(),
            )
            if part
        ).lower()
        choice_prompt_markers = (
            "你覺得",
            "你觉得",
            "哪一項",
            "哪一项",
            "哪個",
            "哪个",
            "選",
            "choose",
            "which",
            "why",
            "為什麼",
            "为什么",
            "最關鍵",
            "最关键",
            "影響最深",
            "影响最深",
        )
        return any(marker in prompt for marker in choice_prompt_markers)

    def _dialogue_control_decision(self, signal: DialogueActSignal) -> DialogueControlDecision:
        """Convert a dialogue-act signal into the formal pre-diagnosis gate.

        Args:
            signal: Bounded dialogue-act proposal from ``DialogueActAgent``.

        Returns:
            A dialogue-control decision that either allows normal cognitive
            diagnosis or routes the turn as clarification/control metadata.

        Compatibility:
            Only generated humanities sessions call this helper today. It keeps
            fixture and STEM sessions on the legacy diagnosis path while making
            the humanities clarification path explicit in methodology traces.
        """
        strategy = strategy_for_dialogue_act(signal.act)
        should_route = strategy is not None or (
            signal.act is LearnerDialogueAct.CLARIFICATION_QUESTION and signal.confidence >= 0.72
        )
        if not should_route:
            return DialogueControlDecision(
                act=signal.act,
                should_diagnose=True,
                memory_kind="answer_evidence",
                target_text=signal.target_text,
                reason_code="dialogue_control_diagnose",
                confidence=signal.confidence,
            )
        return DialogueControlDecision(
            act=signal.act,
            should_diagnose=False,
            memory_kind="dialogue_control",
            target_text=signal.target_text,
            reason_code=f"dialogue_control:{signal.reason_code}",
            confidence=signal.confidence,
        )

    def _handle_term_clarification(
        self,
        signal: DialogueActSignal,
        node_id: str,
        *,
        decision: DialogueControlDecision | None = None,
    ) -> TurnOutcome:
        """Clarify one learner-requested term without updating mastery state."""
        decision = decision or self._dialogue_control_decision(signal)
        label = self.curriculum.nodes[node_id].label
        target = decision.target_text or signal.target_text or label
        strategy = strategy_for_dialogue_act(signal.act) or TutoringStrategy.CLARIFY_TERM
        self._refresh_dialogue_context(signal, node_id, strategy, decision=decision)
        message = _term_clarification_message(target, label)
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.TUTOR_RESPONSE,
            input_ref=MethodologyRef("dialogue_act", signal.act.value, "learner clarification"),
            output_ref=MethodologyRef("tutor_message", "rule", "term clarification"),
            node_id=node_id,
            strategy=strategy.value,
            reason_code=decision.reason_code,
        )
        log_event(
            "pelican_dialogue_act_routed",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            node_id=node_id,
            strategy=strategy.value,
            reason_code=decision.reason_code,
        )
        self.state.current_prompt = message
        self.state.current_prompt_source = "dialogue_act"
        self.store.save(self.state)
        return TurnOutcome(
            message,
            node_id,
            None,
            strategy,
            (),
            "dialogue_act:term_clarification_no_mastery_update",
        )

    def _handle_micro_check_confusion(
        self,
        signal: DialogueActSignal,
        node_id: str,
        *,
        decision: DialogueControlDecision | None = None,
    ) -> TurnOutcome:
        """Offer choices for a micro-check without replaying the full lesson."""
        decision = decision or self._dialogue_control_decision(signal)
        label = self.curriculum.nodes[node_id].label
        target = decision.target_text or signal.target_text or "這個檢核問題"
        strategy = strategy_for_dialogue_act(signal.act) or TutoringStrategy.GIVE_CHOICES
        self._refresh_dialogue_context(signal, node_id, strategy, decision=decision)
        message = _micro_check_choice_message(target, label)
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.TUTOR_RESPONSE,
            input_ref=MethodologyRef("dialogue_act", signal.act.value, "micro-check confusion"),
            output_ref=MethodologyRef("tutor_message", "rule", "micro-check choices"),
            node_id=node_id,
            strategy=strategy.value,
            reason_code=decision.reason_code,
        )
        log_event(
            "pelican_dialogue_act_routed",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            node_id=node_id,
            strategy=strategy.value,
            reason_code=decision.reason_code,
        )
        self.state.current_prompt = message
        self.state.current_prompt_source = "dialogue_act"
        self.store.save(self.state)
        return TurnOutcome(
            message,
            node_id,
            None,
            strategy,
            (),
            "dialogue_act:micro_check_confusion_no_mastery_update",
        )

    def _refresh_dialogue_context(
        self,
        signal: DialogueActSignal,
        node_id: str,
        strategy: TutoringStrategy,
        *,
        decision: DialogueControlDecision | None = None,
    ) -> None:
        """Update bounded dialogue memory and EDF policy without mastery evidence."""
        decision = decision or self._dialogue_control_decision(signal)
        self.memory.record_dialogue_act(
            self.state,
            signal,
            node_id=node_id,
            tutor_move=strategy.value,
        )
        self._record_methodology_event(
            MethodologyEventType.GUM_SUBSYSTEM,
            input_ref=MethodologyRef(decision.memory_kind, decision.act.value, "learner dialogue control"),
            output_ref=MethodologyRef("memory_snapshot", node_id, "GUM dialogue snapshot"),
            node_id=node_id,
            strategy=strategy.value,
            reason_code=decision.reason_code,
        )
        self.policy_agent.llm = self.llm
        strategy_decision, policy_proposal = self.policy_agent.propose_strategy(
            self.state,
            context=self._agent_execution_context(),
        )
        self.state.strategy_decision = strategy_decision
        self.state.edf_snapshot = self.edf.snapshot_from_decision(self.state, strategy_decision)
        self._refresh_learner_progress()
        self._record_agent_result(policy_proposal, node_id=node_id, strategy=strategy.value)
        self._record_methodology_event(
            MethodologyEventType.PIPELINE_STAGE,
            stage=MethodologyStage.EDF_STRATEGY_SELECTION,
            input_ref=MethodologyRef("memory_snapshot", node_id, "GUM dialogue snapshot"),
            output_ref=MethodologyRef("edf_snapshot", self.state.edf_snapshot.reason_code, "current EDF policy"),
            node_id=node_id,
            strategy=self.state.edf_snapshot.pedagogical_strategy,
            reason_code=self.state.edf_snapshot.reason_code,
        )
        self._record_activity(
            "edf_dialogue_evaluated",
            "EDF dialogue policy updated",
            detail=self.state.edf_snapshot.pedagogical_strategy,
        )
        log_event(
            "pelican_dialogue_policy_updated",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            node_id=node_id,
            dialogue_act=decision.act.value,
            learner_state=self.state.edf_snapshot.learner_state,
            strategy=self.state.edf_snapshot.pedagogical_strategy,
            route=self.state.edf_snapshot.route,
            reason_code=self.state.edf_snapshot.reason_code,
            proposal_source=policy_proposal.proposal_source,
        )

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
        self.policy_agent.llm = self.llm
        strategy_decision, policy_proposal = self.policy_agent.propose_strategy(
            self.state,
            context=self._agent_execution_context(),
        )
        self.state.strategy_decision = strategy_decision
        self.state.edf_snapshot = self.edf.snapshot_from_decision(self.state, strategy_decision)
        self._refresh_learner_progress()
        self._record_agent_result(policy_proposal, node_id=self.state.current_node_id)
        log_event(
            "pelican_learning_policy_updated",
            learner_id=self.state.learner_id,
            phase=self.state.phase,
            node_id=self.state.current_node_id,
            category=category.value,
            learner_state=self.state.edf_snapshot.learner_state,
            strategy=self.state.edf_snapshot.pedagogical_strategy,
            route=self.state.edf_snapshot.route,
            reason_code=self.state.edf_snapshot.reason_code,
            proposal_source=policy_proposal.proposal_source,
        )
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
            self.state.learner_progress = LearnerProgressSnapshot(
                self.state.cycle_id,
                None,
                (),
                learner_state=self.state.strategy_decision.learner_state,
                recommended_next_action=self.state.strategy_decision.selected_strategy.value,
                strategy_signal=self.state.strategy_decision.reason_code,
            )
            return
        progress_nodes: list[LearnerProgressNode] = []
        fragile_concepts: list[str] = []
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
            if node_state.status in {
                KnowledgeStatus.NOT_MASTERED,
                KnowledgeStatus.FRAGILE,
                KnowledgeStatus.PARTIALLY_MASTERED,
            }:
                fragile_concepts.append(node.node_id)
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
            learner_state=self.state.strategy_decision.learner_state,
            fragile_concepts=tuple(fragile_concepts[:8]),
            recommended_next_action=self.state.strategy_decision.selected_strategy.value,
            strategy_signal=self.state.strategy_decision.reason_code,
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
            dialogue_act=self.state.edf_snapshot.dialogue_act,
            repeated_confusion_count=self.state.memory_snapshot.repeated_confusion_count,
        )

    def _select_tutor_role(self, reason: str) -> AgentRole:
        """Choose fast or slow tutor executor from EDF route plus selector fallback."""
        if self.state.strategy_decision.route == "slow":
            return AgentRole.SLOW_SIMULATOR_AGENT
        if self.state.edf_snapshot.route == "slow":
            return AgentRole.SLOW_SIMULATOR_AGENT
        if "slow-thinking" in reason:
            return AgentRole.SLOW_SIMULATOR_AGENT
        return AgentRole.FAST_TUTOR_AGENT

    def _category_with_turn_interpretation(
        self,
        category: ResponseCategory,
        turn_interpretation: TurnInterpretation | None,
    ) -> ResponseCategory:
        """Use Learning Manager interpretation to avoid over-penalizing broad humanities answers."""
        if not turn_interpretation or not self._is_humanities_plan():
            return category
        if turn_interpretation.understanding_status in {
            "partial",
            "partial_correct",
            "broad_but_incomplete",
            "mechanism_missing",
            "context_correct_detail_missing",
        }:
            return ResponseCategory.PARTIAL_CORRECT
        if turn_interpretation.understanding_status == "correct" and turn_interpretation.should_advance_pipeline:
            return ResponseCategory.CORRECT
        return category

    def _interpretation_remediation_prompt(
        self,
        node_id: str,
        label: str,
        turn_interpretation: TurnInterpretation | None,
    ) -> str | None:
        """Build a fallback tutor message from safe Learning Manager teaching points."""
        if (
            not turn_interpretation
            or not self._is_humanities_plan()
            or turn_interpretation.teaching_move != "acknowledge_then_clarify"
        ):
            return None
        understood = "、".join(turn_interpretation.understood_points[:3]).strip()
        missing = "、".join(turn_interpretation.missing_points[:3]).strip()
        if not understood and not missing:
            return None
        understood_text = understood or "你已經抓到這個概念的一部分方向"
        missing_text = missing or f"{label} 的關鍵機制"
        concept_text = self._concept_description(node_id)
        remediation_text = self._safe_remediation_template(node_id, label)
        detail = remediation_text or concept_text or f"{label} 不只是在描述一個大方向，也要說清楚它如何改變制度、關係或結構。"
        return (
            f"你抓到一個重要方向：{understood_text}。\n\n"
            f"不過這個知識點想確認的是「{label}」背後的具體變化。現在還可以補上：{missing_text}。\n"
            f"{detail}\n\n"
            "你可以試著把剛剛那句話再補一點：加上這些具體變化是怎麼發生的就好。"
        )

    def _remediation_prompt(
        self,
        node_id: str,
        label: str,
        *,
        category: ResponseCategory | None = None,
    ) -> str:
        """Return a bounded remediation seed, not a final tutor response.

        Skill-authored remediation templates are useful as strategy hints, but
        generated-skill missed diagnostics must still pass through the tutor
        proposal layer. The returned text is therefore treated as fallback
        ``base_message`` for ``FastTutorAgent``.
        """
        if self.state.learning_plan:
            template = self.state.learning_plan.remediation_templates.get(node_id)
            if template:
                rendered = template.format(label=label)
                if category is ResponseCategory.PARTIAL_CORRECT:
                    return (
                        "你抓到一個重要線索，但還缺關鍵人物、事件位置或因果鏈。\n\n"
                        f"{rendered}\n\n"
                        f"下一步請聚焦：把「{label}」的背景、關鍵變化和後續影響補成一條完整脈絡。"
                    )
                return rendered
        if category is ResponseCategory.PARTIAL_CORRECT:
            return (
                f"你抓到「{label}」的一部分線索了，我們先把缺口補齊。\n\n"
                "請用一句話補上：關鍵人物或概念、發生的變化，以及它造成的後續影響。"
            )
        if self._is_humanities_plan():
            return self._humanities_explanation_check_prompt(node_id, label, category=category)
        return (
            f"我們先停在「{label}」。剛才那題先不往下推。\n\n"
            f"我換成更清楚的方式：請用一句話說，{label} 在整個學習中主要幫我們做什麼？"
        )

    def _scaffold_prompt(self, node_id: str, label: str) -> str:
        """Render an explanation-first scaffold after an inability signal.

        The learner has already said they do not know, so this seed must teach
        before checking. It deliberately avoids generic "cause or result"
        checks because those read like a template and do not verify the actual
        concept.
        """
        lesson = self._learner_facing_scaffold_lesson(node_id, label)
        check = (
            self._restatement_check(label)
            if self._is_humanities_plan()
            else self._low_load_scaffold_check(label)
        )
        return (
            f"沒關係，我先直接講「{label}」。\n\n"
            f"{lesson}\n\n"
            f"{check}"
        )

    def _learner_facing_scaffold_lesson(self, node_id: str, label: str) -> str:
        """Return a compact mini-lesson for an inability scaffold.

        Generated skill ``expected_answer`` values are teacher-side rubrics and
        may be English model instructions such as ``Learner should mention...``.
        Those are useful for classification but must never be exposed as a mini
        lesson. The fallback therefore builds learner-facing content from node
        labels, concept descriptions, remediation templates, and prompts.
        """
        concept_text = self._concept_description(node_id)
        remediation_text = self._safe_remediation_template(node_id, label)
        expected = (self.state.current_expected_answer or "").strip()
        prompt = self._base_tutor_prompt(node_id).strip()
        facts = [
            item
            for item in (
                concept_text,
                remediation_text,
                expected if expected and not _looks_like_teacher_rubric(expected) else "",
                prompt,
            )
            if item and not _looks_like_teacher_rubric(item)
        ]
        context_sentence = facts[0] if facts else f"「{label}」是這段學習的起點概念。"
        detail_sentence = facts[1] if len(facts) > 1 else f"先把它理解成後續概念的背景條件。"
        if self._is_humanities_plan():
            return self._humanities_lesson(node_id, label, context_sentence, detail_sentence)
        return (
            f"先抓概念定位：{context_sentence}\n"
            f"再看為什麼重要：{detail_sentence}\n"
            f"一條脈絡先記住：{label} → 後續制度或事件才有發展基礎。"
        )

    def _is_humanities_plan(self) -> bool:
        """Return whether the active generated plan should use humanities tutoring."""
        category = (
            self.state.learning_plan.domain_category
            if self.state.learning_plan and self.state.learning_plan.domain_category
            else self.state.intake_profile.domain_category
        )
        return category == DomainCategory.HUMANITIES.value

    def _humanities_explanation_check_prompt(
        self,
        node_id: str,
        label: str,
        *,
        category: ResponseCategory | None,
    ) -> str:
        """Render explanation-first humanities remediation before rechecking.

        Args:
            node_id: Current knowledge-map concept.
            label: Learner-facing concept label.
            category: Current response category that triggered remediation.

        Returns:
            A learner-facing mini-lesson that keeps the learner on the same
            concept and asks one scaffolded understanding check. Correct
            answers are handled by the normal tutoring state machine, which
            unlocks the next map step only after mastery evidence is recorded.
        """
        concept_text = self._concept_description(node_id)
        remediation_text = self._safe_remediation_template(node_id, label)
        lesson = self._humanities_lesson(
            node_id,
            label,
            concept_text or f"「{label}」是理解這段歷史或文本之前要先放穩的背景。",
            remediation_text or f"先把它看成一段脈絡中的關鍵環節，再看它如何影響後面的發展。",
        )
        prefix = (
            "你已經抓到一部分線索，我把缺口補完整。"
            if category is ResponseCategory.PARTIAL_CORRECT
            else "我們先停在這個知識點，不急著往下。"
        )
        return f"{prefix}\n\n{lesson}\n\n{self._restatement_check(label)}"

    def _humanities_lesson(
        self,
        node_id: str,
        label: str,
        context_sentence: str,
        detail_sentence: str,
    ) -> str:
        """Build a narrative mini-lesson for humanities concepts.

        The method uses only the generated skill artifacts and current
        diagnostic context. It deliberately avoids topic-specific hard-coded
        facts so new humanities topics can follow the same explain-check loop.
        """
        return (
            f"背景脈絡：{context_sentence}\n"
            f"關鍵意思：{detail_sentence}\n"
            f"怎麼理解：文科內容通常不是只背一個名詞，而是要把「{label}」放回人物、事件、制度和時代條件裡。"
            "先抓住它前面承接了什麼、它本身改變了什麼、後面又導致什麼，後續知識點才會連成一條線。"
        )

    def _restatement_check(self, label: str) -> str:
        """Ask a scaffolded humanities micro-check before progression."""
        return (
            f"先不用完整重述。你可以先說說看：「{label}」在剛剛這段裡，最關鍵的原因、轉折點，或影響是哪一個？"
            "如果一開始不好說，也可以只選一個你覺得重要的點，我會先幫你確認理解，再接到知識地圖的下一個知識點。"
        )

    def _concept_description(self, node_id: str) -> str:
        """Return a learner-facing concept positioning sentence."""
        if not node_id:
            return ""
        return f"「{self.curriculum.nodes[node_id].label}」是在建立後續理解之前，先要放清楚的背景基礎。"

    def _safe_remediation_template(self, node_id: str, label: str) -> str:
        """Return remediation guidance only when it contains learner-facing content."""
        if self.state.learning_plan:
            template = self.state.learning_plan.remediation_templates.get(node_id, "")
            if template and not _looks_like_teacher_rubric(template):
                rendered = template.format(label=label)
                if not _looks_like_instruction_only(rendered):
                    return _clean_learner_sentence(rendered)
        return ""

    def _low_load_scaffold_check(self, label: str) -> str:
        """Return a concrete binary check grounded on the current concept label."""
        return (
            "低負荷確認：你先只要選一個，"
            f"「{label}」比較像是 A. 後面事件的背景基礎，還是 B. 已經完成的最後結果？"
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
        return classify_response(
            answer,
            self.state.current_expected_answer,
            self.curriculum,
            prompt=self.state.current_prompt,
        )

    def _tutor_message(
        self,
        strategy: TutoringStrategy,
        node_id: str,
        *,
        evidence_signal: str | None = None,
        learner_answer: str = "",
        base_message: str | None = None,
        tutor_role: AgentRole | None = None,
        turn_interpretation: TurnInterpretation | None = None,
    ) -> tuple[str, str, ProposalValidationStatus, str, str, str, AgentExecutionResult]:
        """Generate or select a bounded tutor response without mastery mutation.

        Args:
            strategy: EDF-selected tutoring move.
            node_id: Current concept node to ground the response.
            evidence_signal: Safe current-turn signal used for proposal trace.
            learner_answer: Latest learner answer passed only to the tutor model
                for acknowledgement and remediation grounding. It is not logged
                or stored in agent proposal metadata by this method.
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
            learner_answer=learner_answer,
            recent_safe_signals=self.memory.recent_safe_signals(self.state),
            base_message=base_message,
            turn_interpretation=turn_interpretation,
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


def _conversation_control_reason(answer: str) -> str:
    """Classify high-confidence no-write conversation-control turns.

    Args:
        answer: Current learner turn. The caller must not log this raw text.

    Returns:
        Stable safe reason code when the turn should be handled before the
        learning pipeline, otherwise an empty string.

    Compatibility:
        This rule-mode guard intentionally covers only very short social turns.
        Rich intent interpretation remains the responsibility of the
        ``LearningManagerOrchestrator`` in LLM mode, while this helper prevents
        offline tests and fallback operation from storing greetings as topics.
    """
    normalized = re.sub(r"\s+", "", answer).casefold()
    if not normalized or len(normalized) > 16:
        return ""
    greetings = {
        "你好",
        "您好",
        "嗨",
        "哈囉",
        "哈啰",
        "hello",
        "hi",
        "hey",
        "yo",
        "你在嗎",
        "你在吗",
    }
    return "social_greeting" if normalized in greetings else ""


def _orchestration_confidence_bucket(value: float) -> str:
    """Return a coarse Learning Manager confidence bucket for safe UI/debug output."""
    if value >= 0.8:
        return "high"
    if value >= 0.62:
        return "medium"
    if value > 0:
        return "low"
    return "none"


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


def _looks_like_teacher_rubric(text: str) -> bool:
    """Return whether text is teacher-facing grading guidance.

    Args:
        text: Candidate explanation text from diagnostics or remediation data.

    Returns:
        ``True`` for rubric-like English instructions that should remain hidden
        from learners.
    """
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    if not normalized:
        return False
    rubric_markers = (
        "learner should",
        "student should",
        "expected answer",
        "should mention",
        "should explain",
        "should identify",
        "should describe",
        "should connect",
    )
    return any(marker in normalized for marker in rubric_markers)


def _looks_like_instruction_only(text: str) -> bool:
    """Return whether text is mainly a teaching instruction, not content."""
    normalized = re.sub(r"\s+", " ", text).strip()
    instruction_markers = (
        "讓我們回到",
        "讓我們看看",
        "我們來回顧",
        "我們來拆解",
        "我們來梳理",
        "先了解",
        "先看看",
    )
    return any(marker in normalized for marker in instruction_markers) and not any(
        marker in normalized for marker in ("因為", "所以", "形成", "造成", "導致", "基礎", "關鍵在於")
    )


def _clean_learner_sentence(text: str) -> str:
    """Normalize a bounded learner-facing sentence."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned.rstrip("。！？?") + "。"


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


def _term_clarification_message(target: str, node_label: str) -> str:
    """Return a short humanities clarification for a learner-requested term.

    Args:
        target: Bounded term extracted by ``DialogueActAgent``.
        node_label: Current knowledge-map concept used only for grounding.

    Returns:
        A learner-facing clarification that avoids replaying the prior
        mini-lesson and asks for one small next action.
    """
    term = target.strip() or "這個詞"
    if term == "轉折點":
        meaning = "讓局勢方向明顯改變的關鍵事件或原因"
    elif term in {"原因", "關鍵"}:
        meaning = "最能解釋前後變化的核心因素"
    elif term == "影響":
        meaning = "這件事後來造成的改變或結果"
    else:
        meaning = f"剛剛問題裡需要先釐清的「{term}」"
    return (
        f"這裡的「{term}」是指：{meaning}。\n\n"
        f"你不用重講整段內容；先把它放回「{node_label}」這個知識點裡看。"
        "可以先回答一個很小的版本：它讓前後情勢、人物選擇，或後續結果出現什麼改變？"
    )


def _micro_check_choice_message(target: str, node_label: str) -> str:
    """Return choices when a learner is unsure how to answer a micro-check."""
    term = target.strip() or "剛剛那題"
    prefix = ""
    if term == "轉折點":
        prefix = "這裡的「轉折點」是指：讓局勢方向明顯改變的關鍵事件或原因。\n\n"
    return (
        prefix +
        f"可以，我把「{term}」換成更好選的方式。\n\n"
        f"先看「{node_label}」時，你只要從三個角度挑一個：\n"
        "A. 前面發生了什麼，讓局勢開始改變\n"
        "B. 哪個事件或條件最直接推動改變\n"
        "C. 這個改變後來造成什麼影響\n\n"
        "你可以只回 A、B、C，或用一句話說你選哪個。"
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
