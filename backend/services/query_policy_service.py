"""Own model-assisted query decomposition and dialogue policy classification."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


async def parse_and_decompose_query_impl(
    query: str,
    client: Any,
) -> List[Dict[str, str]]:
    """Return validated hybrid-retrieval subqueries with a safe fallback."""

    prompt = f"""你是一個檢索分析師。將問題拆成適合 BM25 與 FAISS 的乾淨檢索詞。
移除題幹指令語；多實體問題拆成獨立子查詢。type 只能是 exact_entity 或 abstract_concept。
只輸出 JSON array，每項包含 query 與 type。
問題：{query}"""
    queries: List[Dict[str, str]] = []
    try:
        from config import settings

        response = await client.chat.completions.create(
            model=settings.model_policy_classifier,
            messages=[
                {"role": "system", "content": "只輸出符合要求的 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        if response.choices and response.choices[0].message.content:
            content = response.choices[0].message.content.strip()
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
            parsed = json.loads(content)
            if isinstance(parsed, list):
                for item in parsed:
                    if not isinstance(item, dict) or not str(item.get("query", "")).strip():
                        continue
                    query_type = item.get("type")
                    if query_type not in {"exact_entity", "abstract_concept"}:
                        query_type = "abstract_concept"
                    queries.append({"query": str(item["query"]), "type": query_type})
    except Exception as exc:
        logger.warning("orchestration.query_decomposition_failed reason=%s", type(exc).__name__)
    return queries or [{"query": query, "type": "abstract_concept"}]


async def classify_dialogue_policy_impl(
    client: Any,
    model: str,
    user_msg: str,
    chat_history: list,
) -> str:
    """Return one allowlisted pedagogical policy or ``NORMAL``."""

    del chat_history
    prompt = f"""Analyze the user's message and select one pedagogical policy.
User message: {user_msg}
Select one of: PROBE_UNDERSTANDING, SUGGEST_ACTION, PUSH_LIMIT, NORMAL.
Return only the policy name."""
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.1,
        )
        policy = response.choices[0].message.content.strip()
        if policy in {"PROBE_UNDERSTANDING", "SUGGEST_ACTION", "PUSH_LIMIT", "NORMAL"}:
            return policy
    except Exception as exc:
        logger.warning("orchestration.dialogue_policy_failed reason=%s", type(exc).__name__)
    return "NORMAL"
