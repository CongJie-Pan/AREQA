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
from .planner import LearningPlanner
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
    return engine


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
