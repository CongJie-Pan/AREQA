"""FastAPI adapter exposing the local PELICAN MVP learning engine."""

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .curriculum import CURRICULUMS
from .engine import PelicanEngine
from .llm import LlmAdapter
from .models import TranscriptEntry
from .models import MethodologyStage
from .planner import LearningPlanner
from .agents import DiagnosisAgent, FastTutorAgent, SkillAgent, SlowSimulatorAgent
from .skill_generator import DomainSkillGenerator
from .state_store import StateStore, StateStoreError
from .observability import log_event

app = FastAPI(title="PELICAN MVP Web API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8123",
        "http://127.0.0.1:8123",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_lock = threading.Lock()
llm_adapter = LlmAdapter()
data_dir = Path(__file__).resolve().parents[1] / "data"
data_dir.mkdir(exist_ok=True)
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)


class BaseRequest(BaseModel):
    """Common request fields for the local MVP API."""

    learner_id: str = "demo_student"
    curriculum_id: str | None = None


class RespondRequest(BaseRequest):
    """Request body for one learner response."""

    answer: str


class ModeRequest(BaseRequest):
    """Request body for switching rule/LLM mode."""

    mode: str


def _get_engine(learner_id: str, curriculum_id: str | None = None) -> PelicanEngine:
    """Create an engine using the process-global data directory and LLM adapter.

    Args:
        learner_id: Local learner/session identifier.
        curriculum_id: Optional fixture curriculum for compatibility tests.

    Returns:
        Engine wired to the same process-global ``LlmAdapter`` for onboarding,
        tutoring, and planner skill generation. The planner is rebound after
        replacing ``engine.llm`` so runtime skill generation cannot accidentally
        use a stale adapter/config.
    """
    engine = PelicanEngine(data_dir, learner_id, curriculum_id=curriculum_id)
    engine.llm = llm_adapter
    engine.planner = LearningPlanner(engine.llm)
    engine.skill_agent = SkillAgent(DomainSkillGenerator(engine.llm))
    engine.diagnosis_agent = DiagnosisAgent(engine.llm)
    engine.fast_tutor_agent = FastTutorAgent(engine.llm)
    engine.slow_simulator_agent = SlowSimulatorAgent(engine.llm)
    return engine


def _skill_artifact_summary(engine: PelicanEngine) -> dict[str, Any] | None:
    """Return a safe learner-visible summary of the active skill artifact.

    Args:
        engine: Active engine whose session may contain a generated learning
            plan.

    Returns:
        Safe skill metadata for UI/export, or ``None`` before skill
        construction. Answer keys, raw prompts, and raw learner evidence are not
        included.
    """
    plan = engine.state.learning_plan
    if not plan:
        return None
    latest_skill_proposal = next(
        (
            proposal
            for proposal in reversed(engine.state.agent_proposals)
            if proposal.role.value == "skill_agent" and proposal.artifact_type == "skill_generation"
        ),
        None,
    )
    current_node_id = engine.state.current_node_id
    current_node = next((node for node in plan.nodes if node.node_id == current_node_id), None)
    diagnostics = {item.node_id: item for item in plan.diagnostics}
    teaching_moves = [
        {"code": key[:80], "description": value[:180]}
        for key, value in list(plan.teaching_methodology.items())[:6]
    ]
    concept_path = [
        {
            "node_id": node.node_id,
            "label": node.label,
            "priority": node.priority,
            "active": node.node_id == current_node_id,
        }
        for node in plan.nodes[:12]
    ]
    return {
        "skill_id": plan.skill_id,
        "skill_version": plan.skill_version,
        "skill_lifecycle": plan.skill_lifecycle,
        "domain_category": plan.domain_category,
        "model_route": plan.model_route,
        "topic": plan.topic,
        "goal_summary": plan.goal_summary,
        "proposal_source": latest_skill_proposal.payload_ref.ref_id if latest_skill_proposal else plan.model_route,
        "used_fallback": (
            latest_skill_proposal.validation_status.value == "fallback_used"
            if latest_skill_proposal
            else False
        ),
        "final_reason_code": latest_skill_proposal.reason_code if latest_skill_proposal else "compiled",
        "concept_path": concept_path,
        "current_diagnostic_target": {
            "node_id": current_node.node_id,
            "label": current_node.label,
            "diagnostic_source": diagnostics[current_node.node_id].source
            if current_node and current_node.node_id in diagnostics
            else None,
        }
        if current_node
        else None,
        "teaching_moves": teaching_moves,
    }


def _tutor_proposal_trace(engine: PelicanEngine) -> list[dict[str, Any]]:
    """Return recent safe tutor proposals linked to final visible messages."""
    return [
        item.to_dict()
        for item in engine.state.agent_proposals[-16:]
        if item.artifact_type == "tutor_proposal"
    ][-6:]


def _agent_executor_trace(engine: PelicanEngine) -> list[dict[str, Any]]:
    """Return safe proposal-adoption rows for the methodology agent executors.

    The trace intentionally exposes references and bounded summaries only:
    proposal ids, role/stage labels, artifact refs, validation status, reason
    codes, and learner-visible previews after validation. Raw learner answers,
    prompts, model bodies, credentials, and hidden reasoning are excluded.
    """
    rows: list[dict[str, Any]] = []
    events = engine.state.methodology_events
    for proposal in engine.state.agent_proposals[-24:]:
        adopted_event = next(
            (
                event
                for event in events
                if event.sequence >= proposal.sequence
                and event.stage == proposal.stage
                and (proposal.node_id is None or event.node_id in {None, proposal.node_id})
            ),
            None,
        )
        rows.append(
            {
                "proposal_id": proposal.proposal_id,
                "sequence": proposal.sequence,
                "role": proposal.role.value,
                "stage": proposal.stage.value,
                "input_ref": proposal.payload_ref.to_dict(),
                "proposal_artifact": {
                    "artifact_type": proposal.artifact_type,
                    "artifact_ref": proposal.payload_ref.to_dict(),
                    "display_summary": proposal.display_summary,
                    "pedagogical_move": proposal.pedagogical_move,
                },
                "validation_status": proposal.validation_status.value,
                "reason_code": proposal.reason_code,
                "adopted_output_ref": adopted_event.output_ref.to_dict() if adopted_event and adopted_event.output_ref else None,
                "final_effect": proposal.final_message_preview or proposal.display_summary or proposal.reason_code,
            }
        )
    return rows[-12:]


def _evidence_response_trace(engine: PelicanEngine) -> list[dict[str, Any]]:
    """Build safe evidence-to-response trace rows for paper-aligned export.

    Returns:
        Bounded rows that connect recent safe evidence signals to EDF state,
        policy, tutor proposal, and final message preview.
    """
    tutor_proposals = _tutor_proposal_trace(engine)
    latest_proposal = tutor_proposals[-1] if tutor_proposals else None
    rows: list[dict[str, Any]] = []
    for evidence in engine.state.direct_evidence[-6:]:
        rows.append(
            {
                "node_id": evidence.node_id,
                "signal": evidence.signal,
                "edf_state": engine.state.edf_snapshot.learner_state,
                "edf_policy": engine.state.edf_snapshot.pedagogical_strategy,
                "proposal_id": latest_proposal.get("proposal_id") if latest_proposal else None,
                "pedagogical_move": latest_proposal.get("pedagogical_move") if latest_proposal else None,
                "final_message_preview": latest_proposal.get("final_message_preview") if latest_proposal else "",
            }
        )
    return rows


def _learning_metadata(engine: PelicanEngine, activity_steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Build safe learning metadata shared by JSON responses and exports.

    Args:
        engine: Active learning engine.
        activity_steps: Already serialized activity events to expose to the UI
            or Markdown export.

    Returns:
        Metadata about the teaching engine state. This deliberately excludes raw
        learner answers so it can be reused by logs and UI status displays.
    """
    skill_id = engine.state.learning_plan.skill_id if engine.state.learning_plan else engine.state.intake_profile.skill_id
    skill_version = engine.state.learning_plan.skill_version if engine.state.learning_plan else engine.state.intake_profile.skill_version
    skill_lifecycle = engine.state.learning_plan.skill_lifecycle if engine.state.learning_plan else engine.state.intake_profile.skill_lifecycle
    domain_category = (
        engine.state.learning_plan.domain_category
        if engine.state.learning_plan and engine.state.learning_plan.domain_category
        else engine.state.intake_profile.domain_category
    )
    model_route = engine.state.learning_plan.model_route if engine.state.learning_plan else engine.state.intake_profile.model_route
    return {
        "phase": engine.state.phase,
        "plan_source": engine.state.plan_source.value,
        "topic": engine.state.learning_plan.topic if engine.state.learning_plan else None,
        "intake_turns": engine.state.intake_profile.intake_turns,
        "intent": engine.state.intake_profile.intent.value,
        "level_hint": engine.state.intake_profile.level_hint,
        "domain_category": domain_category,
        "skill_id": skill_id,
        "skill_version": skill_version,
        "skill_lifecycle": skill_lifecycle,
        "model_route": model_route,
        "latest_signal": engine.state.direct_evidence[-1].signal if engine.state.direct_evidence else None,
        "current_activity": activity_steps[-1] if activity_steps else None,
        "activity_steps": activity_steps,
        "edf_state": engine.state.edf_snapshot.learner_state if engine.state.edf_snapshot else "unknown",
        "edf_policy": engine.state.edf_snapshot.pedagogical_strategy if engine.state.edf_snapshot else "unknown",
        "evidence_count": engine.state.memory_snapshot.evidence_count if hasattr(engine.state, 'memory_snapshot') and engine.state.memory_snapshot else 0,
        "context_count": engine.state.memory_snapshot.working_context_count if hasattr(engine.state, 'memory_snapshot') and engine.state.memory_snapshot else 0,
        "progress_snapshot": engine.state.learner_progress.to_dict(),
        "skill_artifact_summary": _skill_artifact_summary(engine),
        "agent_proposals": [item.to_dict() for item in engine.state.agent_proposals[-8:]],
        "agent_executor_trace": _agent_executor_trace(engine),
        "tutor_proposal_trace": _tutor_proposal_trace(engine),
        "evidence_response_trace": _evidence_response_trace(engine),
        "methodology_stages": [stage.value for stage in MethodologyStage],
        "methodology_events": [item.to_dict() for item in engine.state.methodology_events[-16:]],
        "current_cycle_id": engine.state.cycle_id,
    }


def _serialize_response(engine: PelicanEngine, msg: Any) -> dict[str, Any]:
    """Serialize a turn response with safe learning metadata only."""
    activity_steps = [item.to_dict() for item in engine.state.activity_log[-8:]]
    return {
        "api_version": "v1",
        "message": msg.message,
        "mode": engine.state.mode,
        "curriculum_id": engine.state.curriculum_id,
        "node_id": engine.state.current_node_id,
        "tree": engine.tree_state(),
        "state_changes": list(msg.state_changes),
        "learning": _learning_metadata(engine, activity_steps),
    }


def _log_api_event(event: str, learner_id: str, engine: PelicanEngine, **fields: Any) -> None:
    """Emit API logs with the active safe teaching metadata attached."""
    log_event(
        event,
        learner_id,
        phase=engine.state.phase,
        plan_source=engine.state.plan_source.value,
        skill_id=engine.state.learning_plan.skill_id if engine.state.learning_plan else engine.state.intake_profile.skill_id,
        skill_version=engine.state.learning_plan.skill_version if engine.state.learning_plan else engine.state.intake_profile.skill_version,
        skill_lifecycle=engine.state.learning_plan.skill_lifecycle if engine.state.learning_plan else engine.state.intake_profile.skill_lifecycle,
        domain_category=(
            engine.state.learning_plan.domain_category
            if engine.state.learning_plan and engine.state.learning_plan.domain_category
            else engine.state.intake_profile.domain_category
        ),
        route=engine.state.learning_plan.model_route if engine.state.learning_plan else engine.state.intake_profile.model_route,
        learner_state=engine.state.edf_snapshot.learner_state,
        strategy=engine.state.edf_snapshot.pedagogical_strategy,
        **fields,
    )


def _record_transcript(engine: PelicanEngine, role: str, text: str) -> None:
    """Persist one user-visible chat entry for explicit Markdown export.

    Args:
        engine: Active session engine whose state will receive the transcript.
        role: ``user`` or ``assistant`` style chat role.
        text: Learner-visible message text. This is saved only in the local
            session state and is not emitted through structured logs.

    Side Effects:
        Appends to ``SessionState.transcript`` and saves the session. The list is
        capped to keep local MVP state bounded during repeated experiments.
    """
    if not text.strip():
        return
    normalized_text = text.strip()
    if (
        engine.state.transcript
        and engine.state.transcript[-1].role == role
        and engine.state.transcript[-1].text == normalized_text
    ):
        return
    engine.state.transcript.append(
        TranscriptEntry(role=role, text=normalized_text, phase=engine.state.phase)
    )
    if len(engine.state.transcript) > 200:
        engine.state.transcript = engine.state.transcript[-200:]
    engine.store.save(engine.state)


def _markdown_export(engine: PelicanEngine) -> str:
    """Render the current session as a Markdown conversation export.

    Returns:
        Markdown containing learner-visible transcript plus safe engine metadata.
        It intentionally includes the transcript text because export is an
        explicit user action, while logs continue to use safe metadata only.
    """
    activity_steps = [item.to_dict() for item in engine.state.activity_log[-12:]]
    learning = _learning_metadata(engine, activity_steps)
    lines = [
        "# PELICAN MVP Conversation Export",
        "",
        "## Session",
        "",
        f"- Learner: `{engine.state.learner_id}`",
        f"- Phase: `{learning['phase']}`",
        f"- Topic: `{learning['topic'] or engine.state.intake_profile.topic or '-'}`",
        f"- Domain: `{learning['domain_category']}`",
        f"- Skill: `{learning['skill_id'] or '-'}`",
        f"- Skill lifecycle: `{learning['skill_lifecycle'] or '-'}`",
        f"- Model route: `{learning['model_route'] or '-'}`",
        f"- EDF state: `{learning['edf_state']}`",
        f"- EDF policy: `{learning['edf_policy']}`",
        f"- Evidence count: `{learning['evidence_count']}`",
        "",
        "## Conversation",
        "",
    ]
    if engine.state.transcript:
        for entry in engine.state.transcript:
            speaker = "User" if entry.role == "user" else "AI"
            lines.extend([f"### {speaker}", "", entry.text, ""])
    else:
        lines.extend(["_No transcript entries recorded yet._", ""])

    lines.extend(["## Skill Artifact Summary", ""])
    skill_summary = learning.get("skill_artifact_summary")
    if skill_summary:
        lines.extend(
            [
                f"- Skill id: `{skill_summary.get('skill_id') or '-'}`",
                f"- Version: `{skill_summary.get('skill_version') or '-'}`",
                f"- Lifecycle: `{skill_summary.get('skill_lifecycle') or '-'}`",
                f"- Domain: `{skill_summary.get('domain_category') or '-'}`",
                f"- Goal: {skill_summary.get('goal_summary') or '-'}",
                "",
                "### Concept Path",
                "",
            ]
        )
        for concept in skill_summary.get("concept_path", []):
            marker = "-> " if concept.get("active") else ""
            lines.append(f"- {marker}{concept.get('label')}: `{concept.get('node_id')}`")
        lines.extend(["", "### Teaching Moves", ""])
        for move in skill_summary.get("teaching_moves", []):
            lines.append(f"- `{move.get('code')}`: {move.get('description')}")
        if not skill_summary.get("teaching_moves"):
            lines.append("_No teaching moves recorded yet._")
    else:
        lines.append("_No generated skill artifact recorded yet._")

    lines.extend(["## Knowledge Tree", ""])
    tree = engine.tree_state()
    if tree:
        for node in tree:
            marker = "-> " if node["id"] == engine.state.current_node_id else ""
            lines.append(f"- {marker}{node['label']}: `{node['status']}`")
    else:
        lines.append("_No knowledge tree has been compiled yet._")

    lines.extend(["", "## Recent Engine Activity", ""])
    if engine.state.activity_log:
        for item in engine.state.activity_log[-12:]:
            detail = f" - `{item.detail}`" if item.detail else ""
            lines.append(f"- `{item.code}`: {item.label}{detail}")
    else:
        lines.append("_No engine activity recorded yet._")

    lines.extend(["", "## Methodology Events", ""])
    if learning["methodology_events"]:
        for event in learning["methodology_events"][-12:]:
            stage = event.get("stage") or event.get("event_type")
            reason = event.get("reason_code") or "recorded"
            lines.append(f"- `{event.get('sequence')}` `{stage}`: `{reason}`")
    else:
        lines.append("_No methodology events recorded yet._")

    lines.extend(["", "## Agent Proposals", ""])
    if learning["agent_proposals"]:
        for proposal in learning["agent_proposals"][-8:]:
            lines.append(
                f"- `{proposal.get('role')}` `{proposal.get('validation_status')}`: `{proposal.get('reason_code')}`"
            )
    else:
        lines.append("_No agent proposals recorded yet._")

    lines.extend(["", "## Agent Executor Trace", ""])
    if learning["agent_executor_trace"]:
        for row in learning["agent_executor_trace"]:
            input_ref = row.get("input_ref") or {}
            output_ref = row.get("adopted_output_ref") or {}
            artifact = row.get("proposal_artifact") or {}
            lines.append(
                "- `{seq}` `{role}` `{status}`: input `{input}` → artifact `{artifact}` "
                "→ adopted `{output}` → {effect}".format(
                    seq=row.get("sequence"),
                    role=row.get("role"),
                    status=row.get("validation_status"),
                    input=input_ref.get("label") or input_ref.get("ref_type") or "-",
                    artifact=artifact.get("artifact_type") or "-",
                    output=output_ref.get("label") or "-",
                    effect=row.get("final_effect") or row.get("reason_code") or "-",
                )
            )
    else:
        lines.append("_No agent executor trace recorded yet._")

    lines.extend(["", "## Recent Evidence-to-Response Trace", ""])
    if learning["evidence_response_trace"]:
        for row in learning["evidence_response_trace"]:
            lines.append(
                "- Evidence `{signal}` on `{node}` → EDF `{edf}` / `{policy}` → "
                "proposal `{proposal}` / `{move}` → {preview}".format(
                    signal=row.get("signal") or "-",
                    node=row.get("node_id") or "-",
                    edf=row.get("edf_state") or "-",
                    policy=row.get("edf_policy") or "-",
                    proposal=row.get("proposal_id") or "-",
                    move=row.get("pedagogical_move") or "-",
                    preview=row.get("final_message_preview") or "-",
                )
            )
    else:
        lines.append("_No evidence-to-response trace recorded yet._")

    lines.extend(["", "## Tutor Proposal Trace", ""])
    if learning["tutor_proposal_trace"]:
        for proposal in learning["tutor_proposal_trace"]:
            lines.append(
                f"- `{proposal.get('proposal_id')}` `{proposal.get('validation_status')}` "
                f"`{proposal.get('pedagogical_move') or '-'}`: {proposal.get('display_summary') or '-'}"
            )
    else:
        lines.append("_No tutor proposal trace recorded yet._")

    lines.extend(["", "## Learner Progress Snapshot", ""])
    progress_nodes = learning["progress_snapshot"].get("nodes", [])
    if progress_nodes:
        for node in progress_nodes:
            lines.append(
                f"- {node.get('label')}: `{node.get('status')}` confidence `{node.get('confidence')}`"
            )
    else:
        lines.append("_No learner progress snapshot recorded yet._")
    lines.append("")
    return "\n".join(lines)


@app.get("/api/curriculums")
def get_curriculums() -> dict[str, str]:
    """Return reviewed fixture curricula available for compatibility tests."""
    return {k: v.name for k, v in CURRICULUMS.items()}


@app.post("/api/start")
def start(req: BaseRequest) -> dict[str, Any]:
    """Start or resume a learner session."""
    with state_lock:
        try:
            engine = _get_engine(req.learner_id, req.curriculum_id)
            if engine.state.mode == "llm" and not engine.llm.available:
                engine.state.mode = "rule"
                engine.store.save(engine.state)
            msg = engine.start()
            _record_transcript(engine, "assistant", msg.message)
            _log_api_event("pelican_api_start", req.learner_id, engine)
            return _serialize_response(engine, msg)
        except StateStoreError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/start", reason_code="state_store_error")
            raise HTTPException(status_code=400, detail="Invalid session state")
        except ValueError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/start", reason_code="validation_error")
            raise HTTPException(status_code=400, detail="Validation error")


@app.post("/api/respond")
def respond(req: RespondRequest) -> dict[str, Any]:
    """Process one learner answer through the PELICAN engine."""
    with state_lock:
        try:
            engine = _get_engine(req.learner_id)
            msg = engine.respond(req.answer)
            _record_transcript(engine, "user", req.answer)
            _record_transcript(engine, "assistant", msg.message)
            _log_api_event("pelican_api_response", req.learner_id, engine)
            return _serialize_response(engine, msg)
        except StateStoreError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/respond", reason_code="state_store_error")
            raise HTTPException(status_code=400, detail="Invalid session state")
        except ValueError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/respond", reason_code="validation_error")
            raise HTTPException(status_code=400, detail="Validation error")


@app.post("/api/reset")
def reset(req: BaseRequest) -> dict[str, Any]:
    """Reset a learner session to onboarding or an explicit fixture."""
    with state_lock:
        try:
            engine = _get_engine(req.learner_id)
            msg = engine.reset(req.curriculum_id)
            _record_transcript(engine, "assistant", msg.message)
            _log_api_event("pelican_api_reset", req.learner_id, engine)
            return _serialize_response(engine, msg)
        except StateStoreError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/reset", reason_code="state_store_error")
            raise HTTPException(status_code=400, detail="Invalid session state")
        except ValueError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/reset", reason_code="validation_error")
            raise HTTPException(status_code=400, detail="Validation error")


@app.post("/api/mode")
def set_mode(req: ModeRequest) -> dict[str, Any]:
    """Switch a learner session between deterministic rule mode and LLM mode."""
    with state_lock:
        try:
            engine = _get_engine(req.learner_id)
            mode = req.mode.lower()
            if mode == "llm" and not engine.llm.available:
                raise HTTPException(status_code=400, detail="LLM 尚未設定或無法連線")
            msg = engine.switch_mode(mode)
            _record_transcript(engine, "assistant", msg.message)
            _log_api_event("pelican_api_mode_changed", req.learner_id, engine)
            return _serialize_response(engine, msg)
        except ValueError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/mode", reason_code="validation_error")
            raise HTTPException(status_code=400, detail="Validation error")
        except StateStoreError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/mode", reason_code="state_store_error")
            raise HTTPException(status_code=400, detail="Invalid session state")


@app.get("/api/export")
def export_markdown(learner_id: str = "demo_student") -> Response:
    """Export the current local session transcript as Markdown.

    Args:
        learner_id: Local learner/session identifier to export.

    Returns:
        Downloadable Markdown response containing transcript and safe metadata.
    """
    with state_lock:
        try:
            engine = _get_engine(learner_id)
            markdown = _markdown_export(engine)
            filename = f"pelican_{learner_id}.md"
            _log_api_event("pelican_api_export", learner_id, engine)
            return Response(
                content=markdown,
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except StateStoreError:
            log_event("pelican_api_error", learner_id, endpoint="/api/export", reason_code="state_store_error")
            raise HTTPException(status_code=400, detail="Invalid session state")
        except ValueError:
            log_event("pelican_api_error", learner_id, endpoint="/api/export", reason_code="validation_error")
            raise HTTPException(status_code=400, detail="Validation error")


app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
