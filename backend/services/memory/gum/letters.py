"""Generate and schedule optional care letters without owning GUM runtime state."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def generate_epistolary_letter_via_llm(runtime, 
    user_id: str,
    active_avatar: str,
    hot_memory_snapshot: str,
    cold_memory_context: str
) -> str:
    gum_instance, _ = await runtime.get_gum_instance(user_id)
    if not gum_instance:
        return "系統發生錯誤，無法寫信。"

    prompt = f"""你現在是「{active_avatar}」。請以第一人稱，寫一封信給正在與你進行思想交流的學習者（User）。
這不是一般的即時對話，而是一封跨時空的信件，因此語氣要具有沉澱感、哲學反思與歷史厚度。

【當前學習行為與近期探討（Hot Memory）】
{hot_memory_snapshot}

【歷史學習背景（Cold Memory）】
{cold_memory_context}

要求：
1. 必須回傳一個 JSON 格式，包含兩個欄位："subject"（信件主旨）與 "content"（信件內容）。
2. "subject" 請擬定一個吸引人且具有哲理的簡短標題。
3. "content" 長度控制在 300 到 500 字之間。針對使用者在對話中展現的疑惑、掙扎或深刻見解，給予回應與更深一層的提問。
4. 充分展現「{active_avatar}」的歷史背景與口吻，不可像 AI 機器人。
5. 排版支援 Markdown，請善用段落讓信件便於閱讀。
6. 結尾請署名，並留下一個發人深省的問題等待對方的回信。

請務必只回傳 JSON 格式，不要包含其他無關的文字。
"""
    try:
        from config import settings
        from pydantic import BaseModel

        class LetterSchema(BaseModel):
            subject: str
            content: str

        rsp = await gum_instance.client.chat.completions.create(
            model=settings.model_gum,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "letter_schema", "schema": LetterSchema.model_json_schema()}},
            max_tokens=800,
            temperature=0.8
        )
        response_text = rsp.choices[0].message.content.strip()

        import json
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)

        data = json.loads(response_text)

        subject = data.get("subject", "一封來自遠方的信")
        if not subject or subject.strip() == "":
            subject = "來自遠方的思考"

        content = data.get("content", "信件內容未能解碼。")

        if isinstance(content, list):
            content = "\n".join(str(c) for c in content)

        return subject, content
    except Exception as e:
        logger.warning("gum.letters_failed reason=%s", type(e).__name__)
        return "一封未知的信", f"來自{active_avatar}的一封信，因時空亂流未能完整送達。"


async def generate_areqa_care_letter_via_llm(runtime, 
    user_id: str,
    hot_memory_snapshot: str,
    cold_memory_context: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str = "",
    last_compeer_message: str = "",
    allow_topic_specific: bool = False,
) -> tuple[str, str]:
    gum_instance, _ = await runtime.get_gum_instance(user_id)
    if not gum_instance:
        return "給你的學習小箋", "我注意到你最近可能有些卡住。先不用急著解決全部問題，回到一個最小的段落或概念就好。你願意告訴我，現在最困住你的是哪一句或哪個想法嗎？"

    safe_cold_memory_context = cold_memory_context if allow_topic_specific else ""
    last_msg_hint = f"\n【避免重複】上一封主動關懷已提過：「{last_compeer_message}」，這封信不得重複同一個問法。" if last_compeer_message else ""
    topic_policy = (
        "【主題證據政策】系統已確認有足夠的近期語意證據。你可以提及 Hot Memory、觸發原因、或相關 Cold Memory 中明確出現的具體學習主題，但不可超出這些證據。"
        if allow_topic_specific
        else (
            "【主題證據政策】系統沒有足夠的近期語意證據支撐具體學習主題。"
            "你必須寫成中性的低壓力關懷短箋，不得提及或暗示任何特定文本、學科、角色、章節或概念。"
            "尤其禁止自行輸出「文言文」、「判詞」、「紅樓夢」、任何角色名，或「昨天你在讀 X」這類具體化時間敘述。"
        )
    )
    prompt = f"""你是 AREQA，一位溫暖、克制、專業的學習陪伴者。請根據學生最近的狀態寫一封非同步關懷信。

【近期學習狀態（Hot Memory）】
{hot_memory_snapshot}

【長期學習背景（Cold Memory，僅供參考）】
{safe_cold_memory_context}

【目前 learner_state】{learner_state}
【目前教學策略】{edf_policy}
【觸發原因】{event_summary or "系統偵測到學生可能需要低壓力關懷"}{last_msg_hint}
{topic_policy}

要求：
1. 寄件人固定是 AREQA，不要扮演任何歷史人物或虛構角色。
2. 必須像 5 分鐘後送達的一封短箋，而不是即時聊天室插話。
3. 內容要回應學生最近卡住、焦慮或長時間停留的狀態；只有在主題證據政策允許時，才可提及具體主題。
4. 長度 120 到 220 字，繁體中文，溫柔但不肉麻，不說教。
5. 結尾只問一個低壓力問題，讓學生可以回信。
6. 嚴格回傳 JSON，包含 "subject" 與 "content"。
"""
    try:
        from config import settings
        from pydantic import BaseModel

        class CareLetterSchema(BaseModel):
            subject: str
            content: str

        rsp = await gum_instance.client.chat.completions.create(
            model=settings.model_gum,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "care_letter_schema", "schema": CareLetterSchema.model_json_schema()}},
            max_tokens=500,
            temperature=0.6,
        )
        response_text = rsp.choices[0].message.content.strip()
        import json
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        data = json.loads(response_text)
        subject = data.get("subject") or "給你的學習小箋"
        content = data.get("content") or "我注意到你最近可能有些卡住。你願意回信告訴我，現在最困住你的是哪一小段嗎？"
        return subject, content
    except Exception as e:
        logger.warning("gum.letters_failed reason=%s", type(e).__name__)
        return "給你的學習小箋", "我注意到你最近可能有些卡住。先不用急著解決全部問題，我們可以只從一個最小的地方開始。你願意回信告訴我，現在最困住你的是哪一句或哪個想法嗎？"


async def delayed_reply_writer(user_id: str, mail_id: str, reply_content: str, active_avatar: str, delay_seconds: int = 300):
    logger.info("gum.reply_scheduling delay_seconds=%s", delay_seconds)
    try:
        from mailbox_store import get_mailbox_store
        store = get_mailbox_store()

        await store.schedule_delayed_mail(user_id, {
            "reply_to_mail_id": mail_id,
            "reply_content": reply_content,
            "active_avatar": active_avatar,
            "conversation_id": mail_id
        }, delay_seconds)

        logger.info("gum.reply_scheduled")
    except Exception as e:
        logger.warning("gum.letters_failed reason=%s", type(e).__name__)
