import math
from typing import Dict, Any, Tuple

# We reuse K_DECAY from db_utils.py or define it here if not available directly
K_DECAY = 2.0

def calculate_activation_score(confidence: float, decay: float, age_days: float) -> float:
    """
    Calculate the Activation Score based on GUM decay strategy.
    Activation Score = Confidence * e^(-(11 - Decay) * K * Age)
    """
    # Inverse decay factor so high decay means it lasts longer
    alpha = 11.0 - decay
    gamma = -alpha * K_DECAY * age_days
    return confidence * math.exp(gamma)

def is_user_profile(key: str) -> bool:
    """
    Determine if a memory key belongs to the USER_PROFILE.
    For simplicity, we assume keys related to profile traits or stored in user_profile.json
    are flagged somehow. In this context, if the key is explicitly 'user_profile', it skips decay.
    """
    # This logic can be expanded based on how memory keys are classified
    return key.startswith("user_profile")

async def generate_stitch_tags(llm_client, model: str, memory_content: str) -> Dict[str, Any]:
    """
    Generate STITCH tags using the LLM based on the defined prompt template.
    Gracefully fall back if the LLM returns invalid JSON.
    """
    prompt = f"""你是一個專業的學習行為分析專家。給定以下待歸檔的熱記憶條目，請執行以下任務：
1. 提煉出精煉的語意內容 (refined_content)
2. 從 [AcademicContext, ConceptMastery, ErrorWeakness, LearningGoal, CognitiveStyle, GeneralPersonal] 中選擇 1-2 個最符合的標籤 (primary_tags)
3. 提取記憶中出現的核心實體 (entities)，如人物、章節、書名
4. 判斷並保留時間脈絡或對話狀態 (temporal_context)

請嚴格以 JSON 格式回傳，範例如下：
{{
  "refined_content": "使用者混淆了金陵十二釵正冊的妙玉與副冊的香菱，且對於判詞理解有偏差。",
  "primary_tags": ["ConceptMastery", "ErrorWeakness"],
  "entities": ["妙玉", "香菱", "金陵十二釵"],
  "temporal_context": "2026-06-21 對話第三輪"
}}

待歸檔熱記憶：
{memory_content}
"""
    try:
        from pydantic import BaseModel
        class StitchSchema(BaseModel):
            refined_content: str
            primary_tags: list[str]
            entities: list[str]
            temporal_context: str

        rsp = await llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "stitch_schema", "schema": StitchSchema.model_json_schema()}}
        )
        import json
        import re
        content = rsp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            content = match.group(0)
        return json.loads(content)
    except Exception as e:
        # Graceful fallback
        print(f"[STITCH] Tagging failed, gracefully falling back: {e}")
        return {
            "refined_content": memory_content,
            "primary_tags": ["GeneralPersonal"],
            "entities": [],
            "temporal_context": ""
        }

