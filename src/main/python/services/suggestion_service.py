import os
import json
import logging
from typing import List, Dict, Any, Optional
import opencc
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Artificial few-shot examples as "Dynamic Context" seeds
FEW_SHOT_EXAMPLES = """
[範例一]
用戶問題：賈寶玉為什麼不喜歡讀四書五經？
回答摘要：寶玉天性叛逆，認為仕途功名是「國賊祿鬼」，對女兒家的靈秀更為欣賞。
建議問題：["寶玉對仕途的態度如何影響他與賈政的關係？", "《紅樓夢》中有哪些人物積極追求仕途？", "寶玉的人生觀與魏晉名士有何相通之處？"]

[範例二]
用戶問題：林黛玉和薛寶釵的性格有什麼不同？
回答摘要：黛玉多愁善感、才情縱橫；寶釵圓融世故、處事周全，代表「情」與「禮」的對立。
建議問題：["金陵十二釵正冊中黛玉和寶釵的判詞各是什麼？", "大觀園中其他人對黛玉和寶釵的態度有何不同？", "曹雪芹對這兩個角色的設計意圖是什麼？"]

[範例三]
用戶問題：《紅樓夢》的主題思想是什麼？
回答摘要：全書以賈府盛衰映照社會興亡，以寶黛愛情悲劇探討情與世俗的衝突，充滿濃郁的虛無感與悲憫情懷。
建議問題：["《紅樓夢》的「色空觀」從哪些情節體現出來？", "賈府的衰敗與清代社會背景有何關聯？", "前八十回與後四十回的主題風格有何差異？"]
"""

SUGGESTION_SYSTEM_PROMPT = f"""你是《紅樓夢》與中國古典文學問答系統「小紅」的延伸問題生成器。

你的任務是根據用戶的問題、模型的回答摘要，以及相關的古籍文本片段，
生成 3 個繁體中文的延伸問題，讓用戶可以繼續深入探索。

【重要規則】
- 每個問題必須在 25 字以內
- 所有問題都必須是系統能從提供的古籍片段中回答的（不能超出上下文範疇）
- 問題要有多樣性，角度各不相同（如：人物、情節、主題、比較等）
- 禁止生成與紅樓夢或國學無關的問題
- 絕對禁止使用簡體中文，必須全程使用繁體中文（zh-TW）
- 輸出純 JSON：{{"suggestions": ["問題1", "問題2", "問題3"]}}

【示範（動態 Few-Shot）】
{FEW_SHOT_EXAMPLES}

現在請根據以下資訊生成延伸問題："""

class SuggestionService:
    def __init__(self, api_key: Optional[str] = None):
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
        self.model = "qwen/qwen-2.5-7b-instruct"
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
