"""Shared imports for orchestration service mixins."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Request

from config import settings
from services.memory.gate import classify_user_message
from core import AgentEvent, ConversationRunState, EventType, SearchMode
from policies import CapabilityPolicy, SearchDecision, SearchReason
from services.query_policy.classifier import (
    AttachmentTask,
    apply_pdf_auto_explain_guardrail,
    count_pdf_attachments,
    default_response_policy,
    paper_auto_explain_instruction,
    response_policy_from_legacy,
)
from services.turn_latency_trace import TurnLatencyTrace
from services.turn_plan_service import TurnPlan
from services.turn_intake_service import chat_avatar_key as _chat_avatar_key
from services.orchestration.utils import (
    _build_valid_web_sources,
    _localized_greeting_reply,
    classify_dialogue_policy,
    parse_and_decompose_query,
    reorder_for_attention,
)

logger = logging.getLogger(__name__)
InterfaceLanguage = str

class OrchestrationRetrievalMixin:
    async def _node_rag_retrieval(self, last_user_msg: str, rag_queries: List[Dict[str, str]], cached_results=None, run_state: Optional[ConversationRunState] = None) -> AsyncGenerator[str, None]:
        """
        Execute the local RAG retrieval node.

        Args:
            last_user_msg (str): The latest user message.
            rag_queries (List[Dict[str, str]]): Decomposed queries for retrieval.
            cached_results (Optional[Any]): Cached retrieval results, if any. Defaults to None.
            run_state (Optional[ConversationRunState]): The current conversation state object. Defaults to None.

        Yields:
            str: SSE formatted status updates and retrieved sources.
        """
        run_state = run_state or ConversationRunState()
        from main import get_query_fingerprint, rag_cache, _thread_pool
        fingerprint = get_query_fingerprint(last_user_msg)
        context_results_obj = cached_results

        if not context_results_obj and rag_queries is not None:
            if self.rag:
                gen = self.rag.retrieve_with_events(rag_queries)
                while True:
                    rag_task = asyncio.get_running_loop().run_in_executor(_thread_pool, next, gen, None)
                    while not rag_task.done():
                        done, pending = await asyncio.wait([rag_task], timeout=5.0)
                        if not done:
                            yield f": heartbeat\n\n"
                    event = await rag_task
                    if event is None:
                        break
                    if event["type"] == "status":
                        yield f"event: status\ndata: {json.dumps({'status': event['status'], 'message': event['message']}, ensure_ascii=False)}\n\n"
                    elif event["type"] == "results":
                        context_results_obj = event["data"]
            else:
                yield f"event: status\ndata: {json.dumps({'status': 'RAG disabled (missing index)', 'message': 'Skipping local vector retrieval.'}, ensure_ascii=False)}\n\n"
                context_results_obj = {"fused_results": []}

            if context_results_obj and rag_cache:
                await rag_cache.set(fingerprint, context_results_obj)

        if context_results_obj:
            is_reranked = False
            if context_results_obj.final_results and len(context_results_obj.final_results) > 0:
                first_res = context_results_obj.final_results[0]
                is_reranked = hasattr(first_res, 'reranker_score') or (isinstance(first_res, dict) and 'reranker_score' in first_res)

            effective_threshold = 0.35 if is_reranked else 0.005
            if context_results_obj.highest_score < effective_threshold:
                refusal = "AREQA查閱了相關文獻，暫時沒能找到與您問題直接相關的內容。為了保證回答的準確性，AREQA建議您換個方式提問，或詢問其他相關問題喔！ 😊"
                yield f"data: {json.dumps({'choices': [{'delta': {'content': refusal}, 'index': 0, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
                yield "event: REFUSED\n\n"
                return

            valid_results = [r for r in context_results_obj.final_results if r.text and r.text.strip()]
            highest_score = context_results_obj.highest_score

            dynamic_results = []
            for doc in valid_results:
                if len(dynamic_results) >= 7: break
                if doc.score < 0.005: continue
                if (highest_score - doc.score) > 0.60: continue
                dynamic_results.append(doc)

            valid_results = reorder_for_attention(dynamic_results)

            sources_payload = []
            context_texts = []
            for idx, chunk in enumerate(valid_results, 1):
                raw_source = (getattr(chunk, 'source', None) or getattr(getattr(chunk, 'metadata', None), 'source', None) or getattr(getattr(chunk, 'metadata', None), 'book', None) or getattr(getattr(chunk, 'metadata', None), 'book_name', None))
                chunk_id = getattr(chunk, 'chunk_id', None) or "N/A"
                if not raw_source and chunk_id != "N/A":
                    raw_source = chunk_id.split('_')[0] if '_' in str(chunk_id) else None
                source = raw_source or "古籍文獻"
                context_texts.append(f"[文獻{idx}] {source}\n{chunk.text}")
                sources_payload.append({"title": source, "snippet": chunk.text, "score": float(chunk.score), "chunk_id": chunk_id})

            yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
            yield f"event: status\ndata: {json.dumps({'status': 'generating', 'message': '✍️ 援引文獻，生成解說...' }, ensure_ascii=False)}\n\n"

            context_prompt = "<context>\n" + "\n\n".join(context_texts) + "\n</context>\n\n"
            run_state.context_results = context_results_obj
            run_state.context_prompt = context_prompt
            yield "event: results_obj\n\n"

    async def _node_perplexity_search(self, last_user_msg: str, conversation_id: str, messages: List[Dict[str, str]] = None, run_state: Optional[ConversationRunState] = None, user_id: str = "", trace: Optional[TurnLatencyTrace] = None) -> AsyncGenerator[str, None]:
        """
        Execute the web search node using Perplexity or a configured web search tool.

        Args:
            last_user_msg (str): The latest user message.
            conversation_id (str): The conversation identifier.
            messages (Optional[List[Dict[str, str]]]): The conversation history. Defaults to None.
            run_state (Optional[ConversationRunState]): The current conversation state object. Defaults to None.
            user_id (str): The user identifier. Defaults to "".

        Yields:
            str: SSE formatted status updates and search results.
        """
        node_start = time.time()
        run_state = run_state or ConversationRunState()
        logger.info(
            "orchestration.web_search_started conversation_id=%s user_id=%s",
            conversation_id,
            user_id,
        )
        if trace:
            trace.mark("web_search_started")
        yield f"event: status\ndata: {json.dumps({'status': 'searching_dense', 'message': '🌐 網路檢索中...'}, ensure_ascii=False)}\n\n"


        web_search_provider = os.environ.get(
            "WEB_SEARCH_PROVIDER",
            settings.web_search_provider,
        ).strip().lower() or "openrouter"
        web_search_model = os.environ.get("MODEL_WEB_SEARCH", settings.model_web_search).strip()
        web_search_engine = os.environ.get(
            "OPENROUTER_WEB_SEARCH_ENGINE",
            settings.openrouter_web_search_engine,
        ).strip().lower() or "auto"
        web_search_max_tool_calls = int(os.environ.get(
            "OPENROUTER_WEB_SEARCH_MAX_TOOL_CALLS",
            str(settings.openrouter_web_search_max_tool_calls),
        ))
        if web_search_provider == "openrouter":
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
        elif web_search_provider == "tavily":
            api_key = os.environ.get("TAVILY_API_KEY", "")
        else:
            api_key = os.environ.get("PERPLEXITY_API_KEY", "")
        if not api_key:
            yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 未設定網路搜尋服務金鑰，改用一般對話...'}, ensure_ascii=False)}\n\n"
            run_state.context_prompt = ""
            return

        rewritten_query = last_user_msg
        max_results = min(max(int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "15")), 3), 20)
        search_context_size = os.environ.get("WEB_SEARCH_CONTEXT_SIZE", "high").lower()
        if search_context_size not in {"low", "medium", "high"}:
            search_context_size = "high"
        rewrite_start = time.time()
        enable_query_rewrite = os.environ.get("ENABLE_WEB_QUERY_REWRITE", "true").lower() in {"1", "true", "yes", "on"}
        if enable_query_rewrite and self.client and messages:
            try:
                if trace:
                    trace.increment_model_call("web_query_rewrite")
                history_str = "\n".join([f'{m["role"]}: {m["content"]}' for m in messages[-4:]])
                rewrite_prompt = f"""請根據以下對話歷史，將最後一個使用者的提問重寫為適合在搜尋引擎上查詢的『獨立關鍵字』（Standalone Query）。同時請分析該問題的「複雜度」，並決定需要參考的文獻數量（3到20篇之間）。
請嚴格以 JSON 格式回傳，格式如下：
{{"query": "獨立關鍵字", "max_results": 15}}
不要有任何其他解釋。

對話歷史：
{history_str}"""
                rewrite_res = await self.client.chat.completions.create(
                    model=settings.model_hyde_decomposer,
                    messages=[{"role": "user", "content": rewrite_prompt}],
                    temperature=0.1,
                    max_tokens=150,
                )
                if rewrite_res.choices and rewrite_res.choices[0].message.content:
                    content = rewrite_res.choices[0].message.content.strip()
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(0))
                        rewritten_query = parsed.get("query", last_user_msg)
                        max_results = min(max(int(parsed.get("max_results", 15)), 3), 20)
                    else:
                        rewritten_query = content
            except Exception as exc:
                logger.warning(
                    "orchestration.web_query_rewrite_failed conversation_id=%s reason=%s",
                    conversation_id,
                    type(exc).__name__,
                )

        logger.info(
            "orchestration.web_query_ready conversation_id=%s provider=%s model=%s elapsed_ms=%s max_results=%s context_size=%s rewritten=%s",
            conversation_id,
            web_search_provider,
            web_search_model if web_search_provider == "openrouter" else web_search_provider,
            int((time.time() - rewrite_start) * 1000),
            max_results,
            search_context_size,
            enable_query_rewrite,
        )

        yield f"event: tool_started\ndata: {json.dumps({'tool_name': 'web_search', 'display_message': '🌐 正在查找最新資料'}, ensure_ascii=False)}\n\n"
        try:
            tool_result = await self.tool_registry.execute(
                "web_search",
                {
                    "query": rewritten_query,
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "api_key": api_key,
                    "provider": web_search_provider,
                    "model": web_search_model,
                    "engine": web_search_engine,
                    "max_tool_calls": web_search_max_tool_calls,
                    "max_results": max_results,
                    "search_context_size": search_context_size,
                    "tavily_search_depth": os.environ.get(
                        "TAVILY_WEB_SEARCH_DEPTH",
                        settings.tavily_web_search_depth,
                    ),
                    "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379"),
                },
                run_state.tool_budget,
            )
            if trace:
                trace.increment_tool_call("web_search", tool_result.cache_status)
        except Exception as exc:
            logger.exception(
                "orchestration.web_search_failed conversation_id=%s reason=%s",
                conversation_id,
                type(exc).__name__,
            )
            yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 聯網搜尋服務暫時無法使用，改用一般對話...'}, ensure_ascii=False)}\n\n"
            run_state.context_prompt = ""
            return

        results = tool_result.content["results"]
        openrouter_summary = str(tool_result.content.get("summary") or "").strip()
        run_state.web_search_results = list(results)
        yield f"event: tool_completed\ndata: {json.dumps({'tool_name': 'web_search', 'display_message': '已完成資料查找', 'result_count': len(results), 'latency_ms': tool_result.latency_ms, 'cache_status': tool_result.cache_status}, ensure_ascii=False)}\n\n"

        logger.info(
            "orchestration.web_search_completed conversation_id=%s result_count=%s latency_ms=%s",
            conversation_id,
            len(results),
            tool_result.latency_ms,
        )
        yield f"event: status\ndata: {json.dumps({'status': 'reranking', 'message': '⚡ 篩選與統整網路資訊...'}, ensure_ascii=False)}\n\n"

        context_texts, sources_payload = _build_valid_web_sources(results)
        if not context_texts and openrouter_summary:
            context_texts = [f"[網路搜尋摘要]\n{openrouter_summary}"]
            logger.info(
                "orchestration.web_search_summary_used conversation_id=%s provider=%s",
                conversation_id,
                web_search_provider,
            )
        if sources_payload:
            yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
            yield f"event: status\ndata: {json.dumps({'status': 'sources_ready', 'message': f'已取得 {len(sources_payload)} 筆網路文獻'}, ensure_ascii=False)}\n\n"

        run_state.context_prompt = "<context>\n" + "\n\n".join(context_texts) + "\n</context>\n\n"
        run_state.context_results = {"source": "web_search"}
        logger.info(
            "orchestration.web_search_node_completed conversation_id=%s elapsed_ms=%s",
            conversation_id,
            int((time.time() - node_start) * 1000),
        )
        if trace:
            trace.mark("web_search_finished")
        yield "event: results_obj\n\n"
