"""Backend application bootstrap utilities.

The functions in this module are intentionally small and side-effect focused:
they configure process logging, load environment files, and construct the
FastAPI application. `backend.main` calls them at import time so legacy ASGI
entry points and tests keep observing the same public module behavior.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI


def configure_logging() -> logging.Logger:
    """Configure backend process logging and return the main logger.

    Returns:
        The logger used by `backend.main` and app-level route modules.

    Side Effects:
        Configures root logging once through `logging.basicConfig()` and
        suppresses noisy dependency loggers unless `AREQA_VERBOSE_LOGS` is
        enabled. The stable logger names and levels preserve terminal
        debuggability without logging user content, prompts, tokens, or
        credentials.
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if os.environ.get("AREQA_VERBOSE_LOGS", "").lower() not in {"1", "true", "yes", "on"}:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("gum").setLevel(logging.WARNING)
        logging.getLogger("gum.batcher").setLevel(logging.WARNING)
    return logging.getLogger("backend.main")


def load_environment(project_root: Path) -> None:
    """Load backend environment files from the project root.

    Args:
        project_root: Repository root that may contain `.env` or `.env.local`.

    Side Effects:
        Loads the first existing environment file from `.env` and `.env.local`.
        The function prints only the filename, never variable values or secrets,
        matching the previous startup behavior.
    """

    for env_name in [".env", ".env.local"]:
        env_path = project_root / env_name
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded environment variables from {env_name}")
            break


def create_app() -> FastAPI:
    """Create the backend FastAPI application.

    Returns:
        A FastAPI app with the legacy title preserved for clients and tests.
    """

    return FastAPI(title="XiaoHong Ancient Chinese QA - RAG Backend API")
