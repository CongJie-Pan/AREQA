import json
import asyncio
from typing import AsyncGenerator, List, Dict, Any
from fastapi import Request
from pydantic import BaseModel

class OrchestrationService:
    def __init__(self, router_service, rag_service, suggestion_service, client):
        self.router = router_service
        self.rag = rag_service
        self.suggestion = suggestion_service
        self.client = client

    async def execute(self, messages: List[Dict[str, str]], use_rag: bool, force_think: bool,
                      max_tokens: int, temperature: float, top_p: float,
                      repetition_penalty: float, request: Request) -> AsyncGenerator[str, None]:
        
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        
        # Node 1: Intent Routing
        denied = False
        async for event in self._node_intent_routing(last_user_msg):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("status") == "refused":
                denied = True
                
        if denied:
            yield "data: [DONE]\n\n"
            return
            
        yield f"data: {json.dumps({'status': 'processing'}, ensure_ascii=False)}\n\n"
        
        # Node 2-6: Placeholder for pipeline (will be filled in Gate 1B)
        # For Gate 1A, we just yield a dummy message to show pipeline continues
        yield f"data: {json.dumps({'choices': [{'delta': {'content': 'Orchestrator OK'}}]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    async def _node_intent_routing(self, query: str) -> AsyncGenerator[Dict[str, Any], None]:
        # Emulate the existing gatekeeper logic
        intent_result = await self.router.check_query_intent(query)
        if intent_result["action"] == "DENY":
            yield {"status": "refused", "message": intent_result.get("refusal_message", "拒絕回答")}
        else:
            yield {"status": "routing", "message": ""}
