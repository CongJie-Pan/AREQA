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
from .state_store import StateStore

app = FastAPI(title="PELICAN MVP Web API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    learner_id: str = "demo_student"
    curriculum_id: str | None = None


class RespondRequest(BaseRequest):
    answer: str


class ModeRequest(BaseRequest):
    mode: str


def _get_engine(learner_id: str, curriculum_id: str | None = None) -> PelicanEngine:
    engine = PelicanEngine(data_dir, learner_id, curriculum_id=curriculum_id)
    engine.llm = llm_adapter
    return engine


def _serialize_response(engine: PelicanEngine, msg: Any) -> dict[str, Any]:
    return {
        "message": msg.message,
        "mode": engine.state.mode,
        "curriculum_id": engine.state.curriculum_id,
        "node_id": engine.state.current_node_id,
        "tree": engine.tree_state(),
        "state_changes": list(msg.state_changes),
    }


@app.get("/api/curriculums")
def get_curriculums() -> dict[str, str]:
    return {k: v.name for k, v in CURRICULUMS.items()}


@app.post("/api/start")
def start(req: BaseRequest) -> dict[str, Any]:
    with state_lock:
        engine = _get_engine(req.learner_id, req.curriculum_id)
        if engine.state.mode == "llm" and not engine.llm.available:
            engine.state.mode = "rule"
            engine.store.save(engine.state)
        msg = engine.start()
        return _serialize_response(engine, msg)


@app.post("/api/respond")
def respond(req: RespondRequest) -> dict[str, Any]:
    with state_lock:
        engine = _get_engine(req.learner_id)
        msg = engine.respond(req.answer)
        return _serialize_response(engine, msg)


@app.post("/api/reset")
def reset(req: BaseRequest) -> dict[str, Any]:
    with state_lock:
        engine = _get_engine(req.learner_id)
        msg = engine.reset(req.curriculum_id)
        return _serialize_response(engine, msg)


@app.post("/api/mode")
def set_mode(req: ModeRequest) -> dict[str, Any]:
    with state_lock:
        engine = _get_engine(req.learner_id)
        mode = req.mode.lower()
        if mode == "llm" and not engine.llm.available:
            raise HTTPException(status_code=400, detail="LLM 尚未設定或無法連線")
        try:
            msg = engine.switch_mode(mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return _serialize_response(engine, msg)


app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
