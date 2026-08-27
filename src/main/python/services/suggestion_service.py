import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
import opencc
from openai import AsyncOpenAI

from config import settings
from services.conversation_context_service import resolve_answer_language

logger = logging.getLogger(__name__)

# Artificial few-shot examples as "Dynamic Context" seeds
FEW_SHOT_EXAMPLES_ZH = """
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

FEW_SHOT_EXAMPLES_EN = """
[Example 1]
User question: What is the core idea of relativity?
Answer summary: Relativity explains how measurements of space and time depend on the observer and how gravity relates to spacetime curvature.
Suggested questions: ["How do special and general relativity differ?", "How is relativity used in GPS?", "What historical problem motivated relativity?"]

[Example 2]
User question: How can someone develop computational thinking?
Answer summary: Computational thinking includes decomposition, pattern recognition, abstraction, and algorithm design.
Suggested questions: ["What is decomposition in computational thinking?", "How is it applied in daily life?", "Can you show a simple abstraction example?"]
"""

FEW_SHOT_EXAMPLES_ZH_CN = """
[示例一]
用户问题：相对论的核心概念是什么？
回答摘要：相对论解释了空间和时间如何依赖观察者，以及引力如何与时空弯曲相关。
建议问题：["狭义相对论和广义相对论有什么区别？", "相对论如何应用于 GPS？", "什么历史问题促成了相对论？"]

[示例二]
用户问题：如何培养计算思维？
回答摘要：计算思维包括分解、模式识别、抽象化和算法设计。
建议问题：["什么是计算思维中的分解？", "它如何应用在日常生活中？", "可以展示一个简单的抽象化例子吗？"]
"""

SUGGESTION_SYSTEM_PROMPT_ZH = """你是一位博學廣識的引導型學習助手（AREQA）的「延伸問題生成器」。

你的任務是根據用戶的問題、模型的回答摘要，以及相關的對話或檢索片段，
生成 3 個繁體中文的延伸問題，引導用戶從不同角度繼續深入探索與學習。

【重要規則】
- 每個問題必須簡潔，最多 50 個字元
- 問題必須自然、具有啟發性，並能從給定的回答與上下文中延伸
- 問題要有多樣性，角度各不相同（例如：概念澄清、實際應用、歷史脈絡、哲學反思等）
- 必須全程使用繁體中文，與本回合正式回答語言一致
- 輸出純 JSON：{{"suggestions": ["問題1", "問題2", "問題3"]}}

【示範（動態 Few-Shot）】
{few_shot_examples}

現在請根據以下資訊生成延伸問題："""

SUGGESTION_SYSTEM_PROMPT_ZH_CN = """你是一位博学广识的引导型学习助手（AREQA）的“延伸问题生成器”。

你的任务是根据用户的问题、模型的回答摘要，以及相关的对话或检索片段，
生成 3 个简体中文的延伸问题，引导用户从不同角度继续深入探索与学习。

【重要规则】
- 每个问题必须简洁，最多 50 个字符
- 问题必须自然、有启发性，并能从给定的回答与上下文中延伸
- 问题要有多样性，角度各不相同，例如概念澄清、实际应用、比较或影响
- 必须全程使用简体中文，与本回合正式回答语言一致
- 只输出 JSON：{{"suggestions": ["问题1", "问题2", "问题3"]}}

【示范】
{few_shot_examples}

现在请根据以下信息生成延伸问题："""

SUGGESTION_SYSTEM_PROMPT_EN = """You are AREQA's follow-up question generator, an educational assistant that helps users explore an answer further.

Generate exactly 3 concise follow-up questions based on the user's question, the answer summary, and any relevant context. Write every question in English.

Rules:
- Each question must be between 5 and 100 characters.
- Questions must be natural, useful, answerable from or directly extending the supplied answer and context.
- Use three different angles, such as clarification, practical application, comparison, historical context, or implications.
- Return JSON only, with this exact shape: {{"suggestions": ["Question 1", "Question 2", "Question 3"]}}

Examples:
{few_shot_examples}

Now generate the follow-up questions from the following information:"""

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
        reranked_results: List[Any],
        interface_language: str = "zh-TW",
    ) -> List[str]:
        """Generate language-matched follow-up questions from the completed answer.

        Args:
            user_query: The latest user-authored query used for language detection.
            answer_text: The generated answer summary to extend.
            reranked_results: Retrieval results that may ground the suggestions.
            interface_language: UI language used only as a fallback when the query
                does not provide a reliable language signal.

        Returns:
            Up to three validated questions. Provider, parsing, and validation
            failures return an empty list so suggestions remain non-critical.

        Side Effects:
            Emits safe structured logs containing language, counts, and failure
            stages. Raw queries, answers, prompts, and model output are never logged.

        Compatibility:
            The return type remains ``List[str]`` for the existing SSE and database
            persistence contracts.
        """
        if not self.client:
            logger.info("suggestions.skipped reason=client_unavailable")
            return []

        answer_language = resolve_answer_language(interface_language, user_query)
        is_english = answer_language == "English"
        is_simplified_chinese = answer_language == "簡體中文"
        prompt_template = (
            SUGGESTION_SYSTEM_PROMPT_EN
            if is_english
            else SUGGESTION_SYSTEM_PROMPT_ZH_CN
            if is_simplified_chinese
            else SUGGESTION_SYSTEM_PROMPT_ZH
        )
        system_prompt = (
            prompt_template
        ).format(
            few_shot_examples=(
                FEW_SHOT_EXAMPLES_EN
                if is_english
                else FEW_SHOT_EXAMPLES_ZH_CN
                if is_simplified_chinese
                else FEW_SHOT_EXAMPLES_ZH
            ),
        )

        # Assemble dynamic retrieved contexts (Top-4 as per paper)
        context_parts = []
        for i, res in enumerate(reranked_results[:4], 1):
            text = getattr(res, 'text', getattr(res, 'snippet', str(res)))
            source = getattr(
                res,
                'source',
                getattr(res, 'title', 'source' if is_english else '文獻'),
            )
            context_marker = "Excerpt" if is_english else "片段"
            context_parts.append(f"[{context_marker}{i}] {source}: {text}")
        
        context_text = "\n\n".join(context_parts)

        user_question_label = "User question" if is_english else "用户问题" if is_simplified_chinese else "用戶問題"
        answer_summary_label = (
            "Answer summary (first 400 characters)"
            if is_english
            else "回答摘要（前400字）"
            if is_simplified_chinese
            else "回答摘要（前400字）"
        )
        context_label = (
            "Relevant context excerpts (make sure the questions directly extend these excerpts)"
            if is_english
            else "相关文本片段（请确保生成的问题可以从以下片段中找到答案）"
            if is_simplified_chinese
            else "相關文本片段（請確保生成的問題可以從以下片段中找到答案）"
        )
        output_language_instruction = (
            "Return English only."
            if is_english
            else "请务必以简体中文输出。"
            if is_simplified_chinese
            else "請務必以繁體中文輸出。"
        )
        user_content = f"""{user_question_label}：{user_query}

{answer_summary_label}：
{answer_text[:400]}

{context_label}：
{context_text}

{output_language_instruction}"""

        logger.info(
            "suggestions.requested language=%s model=%s context_count=%s",
            answer_language,
            self.model,
            len(context_parts),
        )

        stage = "provider_call"
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=200,
                temperature=0.7
            )
            
            stage = "response_parse"
            result_str = response.choices[0].message.content or ""
            logger.info(
                "suggestions.model_returned language=%s response_chars=%s",
                answer_language,
                len(result_str),
            )
            result = json.loads(result_str)
            suggestions = result.get("suggestions", [])
            if not isinstance(suggestions, list):
                raise ValueError("suggestions field must be a list")
            logger.info(
                "suggestions.json_parsed language=%s candidate_count=%s",
                answer_language,
                len(suggestions),
            )
            
            stage = "candidate_filter"
            # Post-processing: diversity, length filter, and Traditional Chinese enforcement.
            valid_suggestions = []
            for s in suggestions:
                if not isinstance(s, str):
                    continue
                s = s.strip()
                s = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", s).strip()
                if answer_language == "繁體中文":
                    # Apply OpenCC conversion as a Traditional Chinese failsafe only.
                    s = self.converter.convert(s)
                max_length = 100 if is_english else 50
                if 5 <= len(s) <= max_length:
                    valid_suggestions.append(s)
            logger.info(
                "suggestions.filtered language=%s candidate_count=%s accepted_count=%s",
                answer_language,
                len(suggestions),
                len(valid_suggestions),
            )
            return valid_suggestions[:3]

        except Exception as exc:
            logger.warning(
                "suggestions.failed language=%s stage=%s reason=%s",
                answer_language,
                stage,
                type(exc).__name__,
            )
            return []
