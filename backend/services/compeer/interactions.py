"""Internal ComPeer scheduler implementation module."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import random
import sys
import time as _time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel
from redis_client import get_redis
from services.hot_memory_service import remove_typed_entry

logger = logging.getLogger("services.compeer_scheduler")


def _facade():
    return (
        sys.modules.get("services.compeer_scheduler")
        or sys.modules.get("backend.services.compeer_scheduler")
        or importlib.import_module("services.compeer_scheduler")
    )

async def get_last_interaction_time(user_id: str) -> float:
    """
    Retrieve the timestamp of the user's last interaction from Redis.

    Args:
        user_id (str): The ID of the user.

    Returns:
        float: The UNIX timestamp of the last interaction.
    """
    redis = _facade().get_redis()
    val = await redis.get(f"areqa:last_interaction:{user_id}")
    return float(val) if val else _time.time()

async def set_last_interaction_time(user_id: str, timestamp: float):
    """
    Save the timestamp of the user's latest interaction to Redis.

    Args:
        user_id (str): The ID of the user.
        timestamp (float): The UNIX timestamp to save.
    """
    redis = _facade().get_redis()
    await redis.set(f"areqa:last_interaction:{user_id}", str(timestamp))
