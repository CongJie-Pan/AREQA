#!/usr/bin/env python3
"""Inspect likely proactive-care memory contamination.

Default mode is read-only. Use --apply to delete matching Redis entries and
scheduled PostgreSQL delayed tasks after reviewing the dry-run output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


CONTAMINATION_TERMS = (
    "昨天文言文卡很久",
    "文言文卡很久",
    "判詞理解有偏差",
    "判詞",
    "金陵十二釵",
)


@dataclass
class Finding:
    source: str
    key: str
    detail: str
    value: str


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _contains_contamination(value: Any) -> bool:
    text_value = value if isinstance(value, str) else _json_dumps(value)
    return any(term in text_value for term in CONTAMINATION_TERMS)


def _clean_json_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        changed = False
        for key, item in value.items():
            if _contains_contamination(item):
                changed = True
                continue
            cleaned_item, item_changed = _clean_json_value(item)
            cleaned[key] = cleaned_item
            changed = changed or item_changed
        return cleaned, changed

    if isinstance(value, list):
        cleaned_items = []
        changed = False
        for item in value:
            if _contains_contamination(item):
                changed = True
                continue
            cleaned_item, item_changed = _clean_json_value(item)
            cleaned_items.append(cleaned_item)
            changed = changed or item_changed
        return cleaned_items, changed

    return value, False


def _database_url() -> str:
    return os.environ.get("MAILBOX_DATABASE_URL") or os.environ.get("DATABASE_URL", "")


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def inspect_redis(redis_url: str, user_id: str | None, apply: bool) -> list[Finding]:
    client = redis.from_url(redis_url, decode_responses=True)
    patterns = [
        f"areqa:working_memory:{user_id}" if user_id else "areqa:working_memory:*",
        f"areqa:cold_candidates:{user_id}" if user_id else "areqa:cold_candidates:*",
        f"areqa:hot_memory:{user_id}" if user_id else "areqa:hot_memory:*",
        f"areqa:mailbox:{user_id}" if user_id else "areqa:mailbox:*",
    ]
    findings: list[Finding] = []

    try:
        for pattern in patterns:
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
                for key in keys:
                    raw = await client.get(key)
                    if not raw:
                        continue
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        parsed = raw
                    if not _contains_contamination(parsed):
                        continue
                    findings.append(Finding("redis", key, "matched contamination terms", raw))
                    if apply and not key.startswith("areqa:mailbox:"):
                        if isinstance(parsed, (dict, list)):
                            cleaned, changed = _clean_json_value(parsed)
                            if changed:
                                await client.set(key, _json_dumps(cleaned))
                        else:
                            print(f"SKIP apply for non-JSON Redis value: {key}")
                    elif apply:
                        print(f"SKIP apply for delivered mailbox cache: {key}")
                if cursor == 0:
                    break
    finally:
        await client.aclose()

    return findings


async def inspect_postgres(user_id: str | None, apply: bool) -> list[Finding]:
    db_url = _database_url()
    if not db_url:
        return []

    engine = create_async_engine(_asyncpg_url(db_url), connect_args={"statement_cache_size": 0})
    findings: list[Finding] = []
    like_clauses = " OR ".join([f"payload::text LIKE :term_{idx}" for idx, _ in enumerate(CONTAMINATION_TERMS)])
    params = {f"term_{idx}": f"%{term}%" for idx, term in enumerate(CONTAMINATION_TERMS)}
    user_clause = "AND user_id = :user_id" if user_id else ""
    if user_id:
        params["user_id"] = user_id

    try:
        async with AsyncSession(engine) as session:
            cursor = await session.execute(
                text(
                    f"""
                    SELECT task_id, user_id, payload::text AS payload
                    FROM mailbox_delayed_tasks
                    WHERE status = 'scheduled'
                      AND ({like_clauses})
                      {user_clause}
                    """
                ),
                params,
            )
            rows = cursor.mappings().all()
            for row in rows:
                findings.append(
                    Finding(
                        "postgres",
                        str(row["task_id"]),
                        f"scheduled delayed task for user {row['user_id']}",
                        row["payload"],
                    )
                )

            if apply:
                for row in rows:
                    await session.execute(
                        text(
                            """
                            DELETE FROM mailbox_delayed_tasks
                            WHERE task_id = :task_id
                            """
                        ),
                        {"task_id": row["task_id"]},
                    )
                await session.commit()
    finally:
        await engine.dispose()

    return findings


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", help="Limit inspection to one user id.")
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379"))
    parser.add_argument("--apply", action="store_true", help="Delete matched entries. Default is dry-run.")
    args = parser.parse_args()

    findings = []
    findings.extend(await inspect_redis(args.redis_url, args.user_id, args.apply))
    findings.extend(await inspect_postgres(args.user_id, args.apply))

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode}: {len(findings)} finding(s)")
    for finding in findings:
        print(f"[{finding.source}] {finding.key} - {finding.detail}")
        print(finding.value[:1000])
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
