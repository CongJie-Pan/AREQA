"""FastAPI adapter exposing the local PELICAN MVP learning engine."""

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .curriculum import CURRICULUMS
from .engine import PelicanEngine
from .llm import LlmAdapter
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
    """Create an engine using the process-global data directory and LLM adapter."""
    engine = PelicanEngine(data_dir, learner_id, curriculum_id=curriculum_id)
    engine.llm = llm_adapter
    return engine


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
        "learning": {
            "phase": engine.state.phase,
            "plan_source": engine.state.plan_source.value,
            "topic": engine.state.learning_plan.topic if engine.state.learning_plan else None,
            "intake_turns": engine.state.intake_profile.intake_turns,
            "intent": engine.state.intake_profile.intent.value,
            "level_hint": engine.state.intake_profile.level_hint,
            "domain_category": (
                engine.state.learning_plan.domain_category
                if engine.state.learning_plan and engine.state.learning_plan.domain_category
                else engine.state.intake_profile.domain_category
            ),
            "skill_id": engine.state.learning_plan.skill_id if engine.state.learning_plan else engine.state.intake_profile.skill_id,
            "skill_version": engine.state.learning_plan.skill_version if engine.state.learning_plan else engine.state.intake_profile.skill_version,
            "skill_lifecycle": engine.state.learning_plan.skill_lifecycle if engine.state.learning_plan else engine.state.intake_profile.skill_lifecycle,
            "model_route": engine.state.learning_plan.model_route if engine.state.learning_plan else engine.state.intake_profile.model_route,
            "latest_signal": engine.state.direct_evidence[-1].signal if engine.state.direct_evidence else None,
            "current_activity": activity_steps[-1] if activity_steps else None,
            "activity_steps": activity_steps,
            "edf_state": engine.state.edf_snapshot.learner_state if engine.state.edf_snapshot else "unknown",
            "edf_policy": engine.state.edf_snapshot.pedagogical_strategy if engine.state.edf_snapshot else "unknown",
            "evidence_count": engine.state.memory_snapshot.evidence_count if hasattr(engine.state, 'memory_snapshot') and engine.state.memory_snapshot else 0,
            "context_count": engine.state.memory_snapshot.working_context_count if hasattr(engine.state, 'memory_snapshot') and engine.state.memory_snapshot else 0,
        }
    }


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
            log_event("pelican_api_start", req.learner_id, phase=engine.state.phase, plan_source=engine.state.plan_source.value)
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
            log_event("pelican_api_response", req.learner_id, phase=engine.state.phase, plan_source=engine.state.plan_source.value)
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
            log_event("pelican_api_reset", req.learner_id, phase=engine.state.phase, plan_source=engine.state.plan_source.value)
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
            log_event("pelican_api_mode_changed", req.learner_id, phase=engine.state.phase, plan_source=engine.state.plan_source.value)
            return _serialize_response(engine, msg)
        except ValueError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/mode", reason_code="validation_error")
            raise HTTPException(status_code=400, detail="Validation error")
        except StateStoreError as e:
            log_event("pelican_api_error", req.learner_id, endpoint="/api/mode", reason_code="state_store_error")
            raise HTTPException(status_code=400, detail="Invalid session state")


app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
