from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict, dataclass

from core.run_context import RunContext, SearchMode
from policies.search_policy import SearchDecision, SearchPolicy, SearchReason

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ShadowRoutingRecord:
    run_id: str
    decision: SearchDecision
    latency_ms: int


class TutorAgent:
    """Bounded routing component; shadow mode never executes a tool."""

    def __init__(self, search_policy: SearchPolicy | None = None) -> None:
        self.search_policy = search_policy or SearchPolicy()

    async def decide_search(
        self,
        query: str,
        context: RunContext,
        *,
        client=None,
        model: str | None = None,
        timeout_seconds: float = 2.0,
    ) -> SearchDecision:
        # Explicit user modes are deterministic capabilities, never model choices.
        if context.search_mode != SearchMode.AUTO or client is None or not model:
            return self.search_policy.evaluate(query, context.search_mode)

        prompt = f"""Decide whether this query needs external web search before answering.
Search whenever the user asks a knowledge-based question, including conceptual explanations, definitions, facts, recent information, or reference lookups.
Do not search ONLY if the user is making casual chat, greetings, or referring strictly to the ongoing conversation.
Return JSON only: {{"should_search": true|false, "reason_code": "EXTERNAL_SEARCH_REQUIRED"|"AUTHORITATIVE_SOURCE_REQUIRED"|"INTERNAL_KNOWLEDGE_SUFFICIENT"}}.
Do not include reasoning or repeat the query.

Query: {query}"""
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=80,
                ),
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content or ""
            match = re.search(r"\{.*\}", content, re.DOTALL)
            parsed = json.loads(match.group(0) if match else content)
            should_search = bool(parsed["should_search"])
            reason_code = str(parsed["reason_code"])
            if reason_code == "CURRENT_INFORMATION_REQUIRED":
                reason_code = SearchReason.EXTERNAL_SEARCH_REQUIRED.value
            reason = SearchReason(reason_code)
            search_reasons = {
                SearchReason.EXTERNAL_SEARCH_REQUIRED,
                SearchReason.AUTHORITATIVE_SOURCE_REQUIRED,
            }
            if should_search != (reason in search_reasons):
                raise ValueError("inconsistent search decision")
            return SearchDecision(should_search, reason)
        except Exception as exc:
            logger.warning("Tutor routing fallback: %s", type(exc).__name__)
            return self.search_policy.evaluate(query, SearchMode.AUTO)

    async def evaluate_search_shadow(
        self,
        query: str,
        context: RunContext,
        *,
        evaluation_mode: SearchMode = SearchMode.AUTO,
        client=None,
        model: str | None = None,
    ) -> ShadowRoutingRecord:
        started = time.monotonic()
        shadow_context = RunContext(
            run_id=context.run_id,
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            request_id=context.request_id,
            search_mode=evaluation_mode,
            memory_scope=context.memory_scope,
            learner_state_version=context.learner_state_version,
            started_at=context.started_at,
        )
        decision = await self.decide_search(
            query,
            shadow_context,
            client=client,
            model=model,
        )
        record = ShadowRoutingRecord(
            run_id=context.run_id,
            decision=decision,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        logger.info(
            "Tutor shadow routing: %s",
            {
                "run_id": record.run_id,
                "decision": asdict(record.decision),
                "latency_ms": record.latency_ms,
                "actual_search_mode": context.search_mode.value,
            },
        )
        return record
