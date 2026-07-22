import os
import json
import logging
from typing import List, Dict, Any, Optional
import opencc
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

# Artificial few-shot examples as "Dynamic Context" seeds
FEW_SHOT_EXAMPLES = """
[範例一]
用戶問題：相對論的核心概念是什麼？
回答摘要：愛因斯坦提出的相對論分為狹義與廣義，核心在於光速不變以及重力是時空彎曲的表現。
建議問題：["狹義相對論與廣義相對論有什麼主要差異？", "相對論在現代科技（如GPS）上有什麼應用？", "愛因斯坦提出相對論的歷史背景是什麼？"]

[範例二]
用戶問題：如何培養運算思維？
回答摘要：運算思維包含拆解、模式識別、抽象化與演算法設計，可透過程式學習與邏輯訓練來培養。
建議問題：["運算思維在日常生活中有哪些實際應用？", "初學者應該從哪種程式語言開始學習運算思維？", "能否舉例說明什麼是抽象化？"]

[範例三]
用戶問題：莎士比亞的《哈姆雷特》為何經典？
回答摘要：透過對主角內心猶豫與道德掙扎的深刻描寫，展現了複雜的人性與存在主義式的哲學反思。
建議問題：["《哈姆雷特》中經典台詞「To be, or not to be」有何深意？", "哈姆雷特的性格缺陷如何導致了悲劇？", "這部戲劇對後世的心理學有哪些影響？"]
"""

SUGGESTION_SYSTEM_PROMPT = f"""你是一位博學廣識的引導型學習助手（AREQA）的「延伸問題生成器」。

你的任務是根據用戶的問題、模型的回答摘要，以及相關的對話或檢索片段，
生成 3 個繁體中文的延伸問題，引導用戶從不同角度繼續深入探索與學習。

【重要規則】
- 每個問題必須在 25 字以內
- 問題必須自然、具有啟發性，並能從給定的回答與上下文中延伸
- 問題要有多樣性，角度各不相同（例如：概念澄清、實際應用、歷史脈絡、哲學反思等）
- 絕對禁止使用簡體中文，必須全程使用繁體中文（zh-TW）
- 輸出純 JSON：{{"suggestions": ["問題1", "問題2", "問題3"]}}

【示範（動態 Few-Shot）】
{FEW_SHOT_EXAMPLES}

現在請根據以下資訊生成延伸問題："""

class SuggestionService:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize the follow-up question generator.

        Args:
            api_key: Optional OpenRouter key override for tests or alternate
                deployment wiring.
            model: Optional model override. Defaults to the central
                `model_suggestion` setting so deployments can tune latency
                without changing service code.
        """

        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not found. SuggestionService will be limited.")
            self.client = None
        else:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=10.0
            )
        self.model = model or settings.model_suggestion
        # s2twp: Simplified Chinese to Traditional Chinese (Taiwan Standard, with phrase conversion)
        self.converter = opencc.OpenCC('s2twp')

    async def generate_suggestions(
        self,
        user_query: str,
        answer_text: str,
        reranked_results: List[Any]
    ) -> List[str]:
        """
        Generate 3 follow-up questions based on the Dynamic Contexts approach.
        reranked_results: Expected to be list of RetrievalResult or objects with text/snippet and title/source.
        """
        if not self.client:
            return []

        # Assemble dynamic retrieved contexts (Top-4 as per paper)
        context_parts = []
        for i, res in enumerate(reranked_results[:4], 1):
            text = getattr(res, 'text', getattr(res, 'snippet', str(res)))
            source = getattr(res, 'source', getattr(res, 'title', '文獻'))
            context_parts.append(f"[片段{i}] {source}: {text}")
        
        context_text = "\n\n".join(context_parts)

        user_content = f"""用戶問題：{user_query}

回答摘要（前400字）：
{answer_text[:400]}

相關古籍文本片段（請確保生成的問題可以從以下片段中找到答案）：
{context_text}

請務必以繁體中文輸出。"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SUGGESTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=200,
                temperature=0.7
            )
            
            result_str = response.choices[0].message.content
            result = json.loads(result_str)
            suggestions = result.get("suggestions", [])
            
            # Post-processing: diversity, length filter, and Traditional Chinese enforcement
            valid_suggestions = []
            for s in suggestions:
                s = s.strip()
                # Apply OpenCC conversion as a failsafe
                s = self.converter.convert(s)
                if 5 <= len(s) <= 35: # Slightly more relaxed than 25 for safety
                    valid_suggestions.append(s)
            
            return valid_suggestions[:3]

        except Exception as e:
            logger.error(f"SuggestionService error: {e}")
            return []
