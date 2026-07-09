#!/usr/bin/env python3
"""Cloud API probe for AREQA's auth, Redis, mailbox, and cold-memory paths.

This runner intentionally lives outside pytest so it never hits cloud services
from normal local or CI test runs by accident.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse

import psycopg2
import redis
import requests
from dotenv import load_dotenv
from jose import jwt


DEFAULT_BACKEND_URL = "https://areqa-backend.onrender.com"
REQUIRED_ENV = (
    "DATABASE_URL",
    "JWT_SECRET",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "OPENROUTER_API_KEY",
    "REDIS_URL",
)


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ProbeState:
    backend_url: str
    run_id: str
    test_user_id: str
    token: str
    session: requests.Session
    request_timeout: int
    request_retries: int
    redis_client: redis.Redis | None = None
    delayed_task_id: str | None = None
    conversation_id: str = ""
    created_mail_id: str | None = None
    db_propositions_exists: bool = False
    db_vec_memory_exists: bool = False
    db_mailbox_messages_exists: bool = False
    db_mailbox_delayed_tasks_exists: bool = False
    results: list[ProbeResult] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(ProbeResult(name=name, ok=ok, detail=detail))
        status = "PASS" if ok else "FAIL"
        suffix = f" - {detail}" if detail else ""
        print(f"[{status}] {name}{suffix}")


def redact(value: str | None) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 10:
        return "<set>"
    return f"{value[:4]}...{value[-4:]}"


def normalize_backend_url(raw: str) -> str:
    return raw.rstrip("/")


def psycopg2_url(raw: str) -> str:
    if raw.startswith("postgresql+asyncpg://"):
        return raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    if raw.startswith("postgres+asyncpg://"):
        return raw.replace("postgres+asyncpg://", "postgresql://", 1)
    return raw


def safe_db_host(raw: str) -> str:
    try:
        parsed = urlparse(psycopg2_url(raw))
        netloc = parsed.hostname or "<unknown>"
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
    except Exception:
        return "<unparseable>"


def make_test_jwt(user_id: str, secret: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + 60 * 60,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def request_json(
    state: ProbeState,
    method: str,
    path: str,
    *,
    auth: bool = True,
    expected: tuple[int, ...] = (200,),
    **kwargs: Any,
) -> tuple[int, Any]:
    headers = dict(kwargs.pop("headers", {}) or {})
    if auth:
        headers["Authorization"] = f"Bearer {state.token}"
    url = f"{state.backend_url}{path}"
    response = request_with_retries(state, method, url, headers=headers, **kwargs)
    content_type = response.headers.get("content-type", "")
    data: Any
    if "application/json" in content_type:
        data = response.json()
    else:
        data = response.text[:500]
    if response.status_code not in expected:
        raise AssertionError(f"{method} {path} returned {response.status_code}: {data}")
    return response.status_code, data


def request_with_retries(state: ProbeState, method: str, url: str, **kwargs: Any) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(1, state.request_retries + 1):
        try:
            return state.session.request(method, url, timeout=state.request_timeout, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < state.request_retries:
                time.sleep(min(5 * attempt, 15))
    raise AssertionError(f"{method} {url} failed after {state.request_retries} attempts: {last_exc}")


def check_env() -> dict[str, str]:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    print("Environment keys:")
    for key in REQUIRED_ENV:
        print(f"  {key}={redact(os.environ.get(key))}")
    if missing:
        raise RuntimeError(f"Missing required .env keys: {', '.join(missing)}")
    return {key: os.environ[key] for key in REQUIRED_ENV}


def connect_redis(state: ProbeState, redis_url: str) -> None:
    client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=10)
    pong = client.ping()
    state.redis_client = client
    state.record("Redis ping", bool(pong), "connected")


def probe_database(state: ProbeState, database_url: str) -> None:
    db_url = psycopg2_url(database_url)
    print(f"Database target: {safe_db_host(db_url)}")
    with psycopg2.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.propositions')")
            state.db_propositions_exists = cur.fetchone()[0] is not None
            cur.execute("SELECT to_regclass('public.vec_memory')")
            state.db_vec_memory_exists = cur.fetchone()[0] is not None
            cur.execute("SELECT to_regclass('public.mailbox_messages')")
            state.db_mailbox_messages_exists = cur.fetchone()[0] is not None
            cur.execute("SELECT to_regclass('public.mailbox_delayed_tasks')")
            state.db_mailbox_delayed_tasks_exists = cur.fetchone()[0] is not None
    state.record("PostgreSQL propositions table", state.db_propositions_exists)
    state.record(
        "PostgreSQL vec_memory table",
        True,
        "present" if state.db_vec_memory_exists else "missing; vector search should degrade",
    )
    state.record("PostgreSQL mailbox_messages table", state.db_mailbox_messages_exists)
    state.record("PostgreSQL mailbox_delayed_tasks table", state.db_mailbox_delayed_tasks_exists)


def probe_api_auth(state: ProbeState) -> None:
    try:
        response = request_with_retries(state, "GET", f"{state.backend_url}/docs")
        state.record("Backend /docs", response.status_code == 200, f"status={response.status_code}")
    except AssertionError as exc:
        state.record("Backend /docs", False, str(exc))

    try:
        unauth = request_with_retries(state, "GET", f"{state.backend_url}/api/v1/mailbox")
        state.record(
            "Mailbox rejects missing token",
            unauth.status_code in (401, 403),
            f"status={unauth.status_code}",
        )
    except AssertionError as exc:
        state.record("Mailbox rejects missing token", False, str(exc))

    try:
        _, mailbox = request_json(state, "GET", "/api/v1/mailbox")
        state.record(
            "Mailbox accepts test JWT",
            isinstance(mailbox, dict) and "mails" in mailbox and "unread_count" in mailbox,
            f"mails={len(mailbox.get('mails', [])) if isinstance(mailbox, dict) else 'n/a'}",
        )
    except AssertionError as exc:
        state.record("Mailbox accepts test JWT", False, str(exc))

    try:
        _, memory = request_json(state, "GET", "/api/v1/memory")
        state.record(
            "Memory accepts test JWT",
            isinstance(memory, dict) and "propositions" in memory,
            f"propositions={len(memory.get('propositions', [])) if isinstance(memory, dict) else 'n/a'}",
        )
    except AssertionError as exc:
        state.record("Memory accepts test JWT", False, str(exc))


def redis_json(client: redis.Redis, key: str) -> Any:
    raw = client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


def run_write_probe(state: ProbeState, delayed_wait_seconds: int, skip_delayed_wait: bool, memory_events: int) -> None:
    if state.redis_client is None:
        raise RuntimeError("Redis client is not initialized")

    state.conversation_id = f"api-e2e-{state.run_id}"
    action_context = {
        "run_id": state.run_id,
        "probe": "cloud api memory probe",
    }

    action_results = []
    for index in range(memory_events):
        _, action = request_json(
            state,
            "POST",
            "/api/v1/log_action",
            json={
                "action_type": "api_e2e_memory_probe",
                "timestamp": int(time.time()),
                "context": {**action_context, "event_index": index},
            },
        )
        action_results.append(action.get("status") == "ok")
    state.record(
        "POST /api/v1/log_action",
        all(action_results),
        f"events={len(action_results)} ok={sum(1 for ok in action_results if ok)}",
    )

    hot_key = f"areqa:hot_memory:{state.test_user_id}"
    hot = wait_for(lambda: redis_json(state.redis_client, hot_key), timeout=15, interval=2)
    hot_text = json.dumps(hot, ensure_ascii=False) if hot else ""
    state.record("Redis hot memory contains RUN_ID", state.run_id in hot_text, hot_key)

    mail_content = f"{state.run_id} cloud api mailbox probe"
    _, sent = request_json(
        state,
        "POST",
        "/api/v1/mailbox/send",
        json={
            "content": mail_content,
            "recipient": "柏拉圖",
            "conversation_id": state.conversation_id,
        },
    )
    state.created_mail_id = sent.get("mail_id")
    state.record("POST /api/v1/mailbox/send", sent.get("status") == "success", f"mail_id={state.created_mail_id}")

    _, mailbox = request_json(state, "GET", "/api/v1/mailbox")
    user_mails = [
        mail
        for mail in mailbox.get("mails", [])
        if mail.get("conversation_id") == state.conversation_id and mail.get("sender") == "User"
    ]
    state.record("Mailbox user mail visible via API", len(user_mails) == 1, f"matches={len(user_mails)}")
    state.record(
        "Mailbox user mail marked read",
        bool(user_mails and user_mails[0].get("is_read") is True),
    )

    mailbox_key = f"areqa:mailbox:{state.test_user_id}"
    mailbox_raw = redis_json(state.redis_client, mailbox_key)
    mailbox_text = json.dumps(mailbox_raw, ensure_ascii=False) if mailbox_raw else ""
    state.record("Redis mailbox contains RUN_ID", state.run_id in mailbox_text, mailbox_key)

    delayed_key = f"areqa:delayed_mail:{state.test_user_id}"
    delayed_tasks = state.redis_client.zrange(delayed_key, 0, -1, withscores=True)
    matching_tasks = []
    for task_json, score in delayed_tasks:
        try:
            task = json.loads(task_json)
        except json.JSONDecodeError:
            continue
        if task.get("conversation_id") == state.conversation_id:
            matching_tasks.append((task, score))
    if matching_tasks:
        state.delayed_task_id = matching_tasks[-1][0].get("task_id")
    state.record(
        "Redis delayed queue contains task",
        len(matching_tasks) == 1,
        f"matches={len(matching_tasks)} task_id={state.delayed_task_id}",
    )
    probe_mailbox_persistence(state, expect_delayed=True)

    if skip_delayed_wait:
        state.record("Delayed delivery wait", True, "skipped by --skip-delayed-wait")
    else:
        wait_for_delayed_reply(state, delayed_wait_seconds)
        probe_mailbox_persistence(state, expect_delayed=True)

    probe_cold_memory(state)


def wait_for_delayed_reply(state: ProbeState, timeout: int) -> None:
    deadline = time.time() + timeout
    first_count = None
    final_matches: list[dict[str, Any]] = []
    while time.time() < deadline:
        _, mailbox = request_json(state, "GET", "/api/v1/mailbox")
        final_matches = [
            mail
            for mail in mailbox.get("mails", [])
            if mail.get("conversation_id") == state.conversation_id and mail.get("sender") != "User"
        ]
        if first_count is None and final_matches:
            first_count = len(final_matches)
            time.sleep(15)
            _, mailbox_again = request_json(state, "GET", "/api/v1/mailbox")
            final_matches = [
                mail
                for mail in mailbox_again.get("mails", [])
                if mail.get("conversation_id") == state.conversation_id and mail.get("sender") != "User"
            ]
            break
        time.sleep(10)

    state.record("Delayed avatar reply delivered", len(final_matches) >= 1, f"matches={len(final_matches)}")
    state.record("Delayed avatar reply not duplicated", len(final_matches) == 1, f"matches={len(final_matches)}")


def probe_cold_memory(state: ProbeState) -> None:
    if not state.db_propositions_exists:
        state.record("Cold memory proposition lookup", False, "public.propositions is missing")
        return

    rows = wait_for(
        lambda: find_cold_memory_rows(state),
        timeout=240,
        interval=10,
    )
    state.record("PostgreSQL propositions contain RUN_ID", len(rows) > 0, f"matches={len(rows)}")


def find_cold_memory_rows(state: ProbeState) -> list[tuple[Any, ...]]:
    db_url = psycopg2_url(os.environ["DATABASE_URL"])
    with psycopg2.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, text
                FROM propositions
                WHERE CAST(user_id AS text) = %s
                  AND text ILIKE %s
                ORDER BY id DESC
                LIMIT 5
                """,
                (state.test_user_id, f"%{state.run_id}%"),
            )
            return cur.fetchall()


def probe_mailbox_persistence(state: ProbeState, *, expect_delayed: bool) -> None:
    if not state.db_mailbox_messages_exists:
        state.record("PostgreSQL mailbox_messages contain RUN_ID", False, "public.mailbox_messages is missing")
        return
    if expect_delayed and not state.db_mailbox_delayed_tasks_exists:
        state.record("PostgreSQL mailbox_delayed_tasks contain task", False, "public.mailbox_delayed_tasks is missing")
        return

    db_url = psycopg2_url(os.environ["DATABASE_URL"])
    with psycopg2.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mail_id, content
                FROM mailbox_messages
                WHERE CAST(user_id AS text) = %s
                  AND content ILIKE %s
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (state.test_user_id, f"%{state.run_id}%"),
            )
            mail_rows = cur.fetchall()
            delayed_rows = []
            if expect_delayed:
                cur.execute(
                    """
                    SELECT task_id, status
                    FROM mailbox_delayed_tasks
                    WHERE CAST(user_id AS text) = %s
                      AND payload::text ILIKE %s
                    ORDER BY created_at DESC
                    LIMIT 5
                    """,
                    (state.test_user_id, f"%{state.run_id}%"),
                )
                delayed_rows = cur.fetchall()
    state.record("PostgreSQL mailbox_messages contain RUN_ID", len(mail_rows) > 0, f"matches={len(mail_rows)}")
    if expect_delayed:
        state.record(
            "PostgreSQL mailbox_delayed_tasks contain task",
            len(delayed_rows) > 0,
            f"matches={len(delayed_rows)} statuses={[row[1] for row in delayed_rows]}",
        )


def cleanup(state: ProbeState) -> None:
    print("Cleanup:")
    if state.redis_client is not None:
        keys = [
            f"areqa:hot_memory:{state.test_user_id}",
            f"areqa:user_profile:{state.test_user_id}",
            f"areqa:mailbox:{state.test_user_id}",
            f"areqa:delayed_mail:{state.test_user_id}",
        ]
        deleted = state.redis_client.delete(*keys)
        state.record("Redis cleanup", True, f"deleted_keys={deleted}")

    db_url = psycopg2_url(os.environ["DATABASE_URL"])
    with psycopg2.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            if state.db_mailbox_delayed_tasks_exists:
                cur.execute(
                    "DELETE FROM mailbox_delayed_tasks WHERE CAST(user_id AS text) = %s",
                    (state.test_user_id,),
                )
                deleted_delayed_tasks = cur.rowcount
            else:
                deleted_delayed_tasks = 0
            if state.db_mailbox_messages_exists:
                cur.execute(
                    "DELETE FROM mailbox_messages WHERE CAST(user_id AS text) = %s",
                    (state.test_user_id,),
                )
                deleted_mailbox_messages = cur.rowcount
            else:
                deleted_mailbox_messages = 0

            if state.db_propositions_exists:
                cur.execute(
                    """
                    DELETE FROM observation_proposition
                    WHERE observation_id IN (
                        SELECT id FROM observations WHERE CAST(user_id AS text) = %s
                    )
                       OR proposition_id IN (
                        SELECT id FROM propositions WHERE CAST(user_id AS text) = %s
                    )
                    """,
                    (state.test_user_id, state.test_user_id),
                )
                deleted_links = cur.rowcount
                cur.execute(
                    """
                    DELETE FROM vec_memory
                    WHERE id IN (
                        SELECT id FROM propositions WHERE CAST(user_id AS text) = %s
                    )
                    """,
                    (state.test_user_id,),
                )
                deleted_vectors = cur.rowcount
                cur.execute(
                    "DELETE FROM observations WHERE CAST(user_id AS text) = %s",
                    (state.test_user_id,),
                )
                deleted_observations = cur.rowcount
                cur.execute(
                    "DELETE FROM propositions WHERE CAST(user_id AS text) = %s",
                    (state.test_user_id,),
                )
                deleted_propositions = cur.rowcount
            else:
                deleted_links = 0
                deleted_vectors = 0
                deleted_observations = 0
                deleted_propositions = 0
        conn.commit()
    state.record(
        "PostgreSQL cleanup",
        True,
        (
            f"mailbox_messages={deleted_mailbox_messages} delayed_tasks={deleted_delayed_tasks} "
            f"links={deleted_links} vectors={deleted_vectors} "
            f"observations={deleted_observations} propositions={deleted_propositions}"
        ),
    )


def wait_for(fn, *, timeout: int, interval: int) -> Any:
    deadline = time.time() + timeout
    last_value = None
    while time.time() < deadline:
        last_value = fn()
        if last_value:
            return last_value
        time.sleep(interval)
    return last_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe AREQA cloud API, Redis, and PostgreSQL data flow.")
    parser.add_argument("--env-file", default=".env", help="Path to .env file.")
    parser.add_argument("--backend-url", default=os.environ.get("BACKEND_URL") or os.environ.get("NEXT_PUBLIC_BACKEND_URL") or DEFAULT_BACKEND_URL)
    parser.add_argument("--test-user-id", default=str(uuid.uuid4()), help="JWT sub/user id for the isolated probe.")
    parser.add_argument("--run-id", default=f"api-e2e-{time.strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--write", action="store_true", help="Write isolated test data to cloud Redis/PostgreSQL through APIs.")
    parser.add_argument("--cleanup", action=argparse.BooleanOptionalAction, default=True, help="Clean up Redis/DB test data after write probe.")
    parser.add_argument("--skip-delayed-wait", action="store_true", help="Verify delayed queue only; do not wait for delivery.")
    parser.add_argument("--delayed-wait-seconds", type=int, default=420, help="Max wait for delayed mailbox delivery.")
    parser.add_argument("--memory-events", type=int, default=18, help="Number of log_action events to send so GUM batch processing can produce cold memory.")
    parser.add_argument("--request-timeout", type=int, default=90, help="HTTP request timeout in seconds.")
    parser.add_argument("--request-retries", type=int, default=2, help="HTTP retry attempts for cloud cold starts.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(args.env_file)

    try:
        env = check_env()
        backend_url = normalize_backend_url(args.backend_url)
        token = make_test_jwt(args.test_user_id, env["JWT_SECRET"])
        session = requests.Session()
        state = ProbeState(
            backend_url=backend_url,
            run_id=args.run_id,
            test_user_id=args.test_user_id,
            token=token,
            session=session,
            request_timeout=args.request_timeout,
            request_retries=args.request_retries,
        )

        print(f"Backend target: {backend_url}")
        print(f"RUN_ID: {state.run_id}")
        print(f"TEST_USER_ID: {state.test_user_id}")

        connect_redis(state, env["REDIS_URL"])
        probe_database(state, env["DATABASE_URL"])
        probe_api_auth(state)

        if args.write:
            run_write_probe(state, args.delayed_wait_seconds, args.skip_delayed_wait, args.memory_events)
            if args.cleanup:
                cleanup(state)
        else:
            state.record("Write probe", True, "skipped; pass --write to exercise mailbox/memory writes")

        failed = [result for result in state.results if not result.ok]
        print(f"Summary: {len(state.results) - len(failed)} passed, {len(failed)} failed")
        print_next_actions(state, failed)
        return 1 if failed else 0
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1


def print_next_actions(state: ProbeState, failed: list[ProbeResult]) -> None:
    if not failed:
        return

    print("Next actions:")
    if any("Auth configuration missing" in result.detail for result in failed):
        print("  - Configure JWT_SECRET in the running backend environment, then redeploy/restart the API.")
    if any(result.name == "PostgreSQL propositions table" for result in failed):
        print("  - Apply the cold-memory PostgreSQL schema/migration that creates public.propositions.")
    if any(result.name.startswith("PostgreSQL mailbox_") for result in failed):
        print("  - Apply the mailbox persistence PostgreSQL schema/migration that creates public.mailbox_messages and public.mailbox_delayed_tasks.")
    if not state.db_vec_memory_exists:
        print("  - Optional: create public.vec_memory for vector search; API should still degrade without it.")
    if any("failed after" in result.detail for result in failed):
        print("  - Check backend URL, Render service health, and cold-start duration; retry with --request-timeout 120.")


if __name__ == "__main__":
    raise SystemExit(main())
