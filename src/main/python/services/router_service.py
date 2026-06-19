import os
import json
import logging
from typing import Dict, Any, Optional
import opencc
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """你是「小紅問答系統」的輸入守門人。
你的唯一任務是判斷用戶的輸入是否屬於「《紅樓夢》或中國古典文學、國學」的範疇，
並輸出一個 JSON 物件，格式如下：
{
  "action": "ALLOW" | "DENY",
  "domain": "識別出的問題領域（若ALLOW則為null）",
  "refusal_message": "若DENY，以「小紅」的口吻用繁體中文寫一句自然的拒答，需點出用戶的問題屬於哪個領域。若ALLOW則為null。"
}

判斷標準：
- ALLOW：問題明確涉及紅樓夢人物、情節、詩詞；四書五經、詩詞歌賦、史書、諸子百家等國學範疇
- DENY：數學計算、程式設計、現代科技、自然科學、閒聊、無意義字符、其他非古典文學問題

注意：
- refusal_message 必須自然、具體，不可千篇一律
- 必須輸出純 JSON，不可包含任何說明文字或 Markdown 格式
- 不論問題多短或多奇怪，都必須輸出上述 JSON 格式

範例一：
用戶輸入：賈寶玉為什麼不喜歡仕途？
輸出：{"action": "ALLOW", "domain": null, "refusal_message": null}

範例二：
用戶輸入：請幫我解一道微積分題目
輸出：{"action": "DENY", "domain": "數學/微積分", "refusal_message": "這是數學領域的問題呢，小紅只熟悉《紅樓夢》與國學知識，不在我的範疇內。歡迎詢問古典文學相關問題 😊"}

範例三：
用戶輸入：00000
輸出：{"action": "DENY", "domain": "無意義輸入", "refusal_message": "小紅看不明白這些內容呢，可以換個方式，問一個關於古典文學的問題嗎？"}"""

class RouterService:
    def __init__(self, api_key: Optional[str] = None):
        # Use OpenRouter API key (same as main LLM client)
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not found. RouterService will be disabled.")
            self.client = None
        else:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=15.0  # OpenRouter is more stable; 15s is sufficient
            )
        # qwen/qwen3-vl-8b-instruct: Standard Instruct model (NOT Hybrid Thinking).
        # It does NOT auto-activate thinking mode, so no enable_thinking workaround needed.
        # Avg latency: 0.52s (Alibaba Cloud provider), fast and reliable.
        self.model = "qwen/qwen3-vl-8b-instruct"
        # s2twp: Simplified Chinese to Traditional Chinese (Taiwan Standard)
        self.converter = opencc.OpenCC('s2twp')

    async def check_query_intent(self, query: str) -> Dict[str, Any]:
        """
        Check if the query is within the domain using SLM (Qwen3.5-0.8B).
        Returns:
            Dict with 'action' (ALLOW/DENY) and 'refusal_message'.
        """
        if not self.client:
            return {"action": "ALLOW", "domain": None, "refusal_message": None}

        try:
            import time
            start_time = time.time()
            print(f"DEBUG: RouterService checking intent for: {query[:50]}...")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": query}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=256,
                extra_body={
                    "top_k": 20,  # Limits token choices; helps keep JSON output clean
                }
            )
            
            duration = time.time() - start_time
            print(f"DEBUG: RouterService API call took {duration:.2f}s")
            
            message = response.choices[0].message
            result_str = message.content
            
            # Defensive fallback: some providers may place JSON in reasoning_content.
            # _extract_json_str also strips <think> tags for safety.
            def _extract_json_str(raw: str) -> str:
                """Strip <think>...</think> blocks, then extract the first {...} JSON object."""
                import re
                if not raw:
                    return ""
                # Remove <think>...</think> blocks produced by Qwen3.5 thinking mode
                cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                return match.group(0) if match else ""

            candidates = [result_str]
            if not result_str or not result_str.strip():
                # Priority 1: reasoning_content attribute
                if hasattr(message, "reasoning_content") and message.reasoning_content:
                    candidates = [message.reasoning_content]
                # Priority 2: model_extra['reasoning_content'] (OpenAI SDK internal storage)
                elif hasattr(message, "model_extra") and message.model_extra and "reasoning_content" in message.model_extra:
                    candidates = [message.model_extra["reasoning_content"]]
                else:
                    candidates = []

            json_str = ""
            for raw in candidates:
                json_str = _extract_json_str(raw)
                if json_str:
                    break

            if not json_str:
                print(f"DEBUG: RouterService error - could not extract JSON from any candidate. Message: {message}")
                return {"action": "ALLOW", "domain": None, "refusal_message": None}

            result = json.loads(json_str)
            print(f"DEBUG: RouterService result parsed: {result.get('action')}")
            
            # Post-processing: Traditional Chinese enforcement for refusal message
            if result.get("refusal_message"):
                result["refusal_message"] = self.converter.convert(result["refusal_message"])
            
            # Basic validation of the expected keys
            if "action" not in result:
                result["action"] = "ALLOW"
            
            return result
        except Exception as e:
            print(f"DEBUG: RouterService Exception: {e}")
            # Fail safe: allow the query if the router fails
            return {"action": "ALLOW", "domain": None, "refusal_message": None}
