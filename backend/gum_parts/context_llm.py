"""Context, cold-memory, EDF, and letter-generation helpers for GUM.

These functions are re-exported from ``gum_integration.py`` for compatibility.
They preserve existing fail-soft behavior and avoid adding new structured logs
that might expose raw prompts, user text, generated letters, or credentials.
"""

from __future__ import annotations

import json
import logging
import os
import re
import importlib
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _integration_module():
    return (
        sys.modules.get("backend.gum_integration")
        or sys.modules.get("gum_integration")
        or importlib.import_module("gum_integration")
    )

async def get_hot_memory_snapshot(
    user_id: str = "default_user",
    *,
    conversation_id: str = "",
    include_cross_conversation_focus: bool = True,
) -> str:
    from memory_store import get_global_store
    import json
    store = get_global_store()
    if not store:
        return ""

    # Combine durable profile facts and prompt-safe working memory.
    profile = await store.get_user_profile(user_id)
    import inspect
    get_working_memory = getattr(store, "get_working_memory", None)
    if inspect.iscoroutinefunction(get_working_memory):
        working_memory = await get_working_memory(user_id)
    else:
        working_memory = {}

    parts = []
    if profile:
        parts.append("【使用者畫像 (User Profile)】\n" + json.dumps(profile, ensure_ascii=False, indent=2))

    if working_memory:
        focus = working_memory.get("current_focus")
        focus_conversation_id = working_memory.get("current_focus_conversation_id")
        session_summary = working_memory.get("session_summary")
        summary_conversation_id = working_memory.get("session_summary_conversation_id")
        explicit_memories = working_memory.get("explicit_memories") or []
        recent_points = working_memory.get("recent_learning_points") or []
        if not include_cross_conversation_focus and conversation_id:
            is_same_conversation = bool(focus_conversation_id and focus_conversation_id == conversation_id)
            if not is_same_conversation:
                focus = ""
                explicit_memories = []
                recent_points = []
            if summary_conversation_id != conversation_id:
                session_summary = ""

        if not include_cross_conversation_focus and conversation_id:
            recent_points = [
                point for point in recent_points
                if isinstance(point, dict) and point.get("conversation_id") == conversation_id
            ]

        working_parts = []
        if session_summary:
            working_parts.append(f"Session summary: {session_summary}")
        if focus:
            working_parts.append(f"Current focus: {focus}")
        for memory in explicit_memories[-8:]:
            if memory:
                working_parts.append(f"Explicit memory: {memory}")
        for point in recent_points[-8:]:
            if isinstance(point, dict) and point.get("prompt_safe") is False:
                # logger.info(
                logger.debug(
                    "hot_memory.snapshot_excluded user_id=%s reason=not_prompt_safe",
                    user_id,
                )
                continue
            if isinstance(point, dict) and point.get("text"):
                working_parts.append(point["text"])
            elif isinstance(point, str):
                working_parts.append(point)

        if working_parts:
            parts.append("【工作記憶 (Working Memory)】\n- " + "\n- ".join(working_parts))

    return "\n\n".join(parts)

async def generate_zpd_query_via_llm(client, model, original_query, learner_state):
    prompt = f"""You are an educational AI converting a student's question into a ZPD-aligned search query.
Student's current learning state: {learner_state}
Original query: {original_query}

If the state is "TINKERING" or "RUN_REPEAT", focus on underlying concepts rather than the exact syntax.
If the state is "STARTING", focus on fundamental definitions.
Otherwise, refine the query to be pedagogical.
Return ONLY the refined query string without any quotes or explanations."""
    try:
        rsp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ZPD Query Gen] Error: {e}")
        return original_query

async def query_cold_memory_for_context(
    user_id: str,
    query: str,
    top_k: int = 5,
    client=None,
    model=None,
    memory_trace=None,
) -> str:
    """Return prompt-safe cold memory context with optional safe trace metadata."""

    from cold_memory import ColdMemoryRetriever
    from memory_store import get_global_store
    import os
    from pathlib import Path

    db_path = str(Path(__file__).resolve().parents[1] / "data" / "gum_data" / "gum.db")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return ""

    try:
        store = get_global_store()
        if memory_trace:
            async with memory_trace.measure("cold_memory_learner_state"):
                learner_state = await store.get_learner_state(user_id) if store else "STARTING"
        else:
            learner_state = await store.get_learner_state(user_id) if store else "STARTING"

        c = client
        from config import settings
        m = model if model else settings.model_zpd_query
        if not c:
            from openai import AsyncOpenAI
            c = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

        if memory_trace:
            async with memory_trace.measure("cold_memory_zpd_query"):
                zpd_query = await generate_zpd_query_via_llm(c, m, query, learner_state)
        else:
            zpd_query = await generate_zpd_query_via_llm(c, m, query, learner_state)

        cold_retriever = ColdMemoryRetriever(db_path, api_key)
        if memory_trace:
            async with memory_trace.measure("cold_memory_search"):
                results = await cold_retriever.search(
                    zpd_query,
                    user_id=user_id,
                    top_k=top_k,
                    memory_trace=memory_trace,
                )
        else:
            results = await cold_retriever.search(zpd_query, user_id=user_id, top_k=top_k)
        if not results:
            return ""

        if memory_trace:
            memory_trace.record_step("cold_memory_results", 0, outcome=f"count_{min(len(results), 6)}")
        parts = ["【檢索到的長尾記憶 (Cold Memory)】"]
        for r in results:
            parts.append(f"- {r['text']}")

        return "\n".join(parts)
    except Exception as e:
        print(f"[GUM] Error querying cold memory: {e}")
        return ""

async def async_evaluate_and_update_state(
    client,
    model,
    chat_history,
    user_id: str = "default_user",
    conversation_id: str = "",
    ingest_memory: bool = False,
):
    """Evaluate EDF state without creating profile-memory evidence.

    ``ingest_memory`` remains temporarily for worker compatibility, but is
    intentionally ignored. Exact user evidence enters memory only through
    ``TurnIntakeService`` and ``MemoryIngestionService``.
    """
    from compaction import evaluate_student_state
    from memory_store import get_global_store

    state_res = await evaluate_student_state(client, model, chat_history)
    store = get_global_store()
    if store:
        await store.update_learner_state_snapshot(
            user_id,
            learner_state=state_res.get("learner_state", "STARTING"),
            strategy=state_res.get("pedagogical_strategy", "NORMAL"),
            trigger_proactive=bool(state_res.get("trigger_proactive")),
        )
        # State evaluation must not summon avatars or affect chat persona.
        # Conversation-scoped roleplay is handled only by explicit chat commands in OrchestrationService.
        if state_res.get("trigger_proactive"):
            # We flag this for ComPeer to pick up or log it
            print(f"[ComPeer] Proactive trigger needed: {state_res}")

        # EDF evaluates the learner state only. It must never promote an
        # assistant-generated inference into durable user memory.
        if state_res.get("memory_operations"):
            print("[EDF-LOG] Ignored legacy memory_operations from state evaluation")

        if ingest_memory:
            logger.warning(
                "memory.ingestion_skipped user_id=%s conversation_id=%s reason=edf_boundary",
                user_id,
                conversation_id,
            )


async def detect_proactive_event_via_llm(user_id: str, hot_memory_snapshot: str) -> dict:
    """
    Analyze hot memory snapshot to determine if a proactive intervention is warranted.
    """
    gum_instance, _ = await _integration_module().get_gum_instance(user_id)
    if not gum_instance:
        return {"has_event": False, "event_summary": "", "importance": 0.0}

    from pydantic import BaseModel
    from gum.schemas import get_schema

    class EventDetectSchema(BaseModel):
        has_event: bool
        event_summary: str
        importance: float

    prompt = f"""你是一個學習行為分析師。以下是用戶最近的行為與對話快照：
{hot_memory_snapshot}

請判斷：
1. 用戶是否正在面臨「具體的學習挑戰」或「負面情緒（如挫折、困惑、反覆卡住）」？
2. 如果是，給出事件摘要與重要性（0.0–1.0）。
3. 如果只是正常瀏覽或學習進展順暢，請回傳 has_event=false，重要性設為 0。

請嚴格以 JSON 格式回傳。"""

    try:
        from config import settings
        rsp = await gum_instance.client.chat.completions.create(
            model=settings.model_policy_classifier,
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(EventDetectSchema.model_json_schema()),
            temperature=0.1
        )
        import json as _json
        return _json.loads(rsp.choices[0].message.content)
    except Exception as e:
        print(f"[ComPeer] detect_proactive_event_via_llm failed: {e}")
        return {"has_event": False, "event_summary": "", "importance": 0.0}


async def generate_scaffolding_message_via_llm(
    user_id: str,
    hot_memory_snapshot: str,
    cold_memory_context: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str = "",
    last_compeer_message: str = "",
    active_avatar: str = None
) -> str:
    """
    Generate a personalized scaffolding message for proactive ComPeer intervention.
    """
    gum_instance, _ = await _integration_module().get_gum_instance(user_id)
    if not gum_instance:
        return "你學習狀況還好嗎？有任何問題都可以問我。"

    strategy_hints = {
        "GIVING_UP":   "語氣溫柔、帶情感支持，先安撫再提問。",
        "RUN_REPEAT":  "提供一個新的切入角度或比喻，引導跳出迴圈。",
        "TINKERING":   "提出一個具體的蘇格拉底式問題，促進深化思考。",
        "MASTERY":     "挑戰性地提出一個反例或更深層的問題。",
        "STARTING":    "提供一個簡短的背景知識錨點，降低門檻。",
    }
    hint = strategy_hints.get(learner_state, "自然地詢問用戶的學習進展。")

    tone_constraint = ""
    if learner_state == "STARTING":
        tone_constraint = "\n【動態表達限制：STARTING 階段】\n注意：使用者目前為初學者（STARTING）。你必須「嚴格降低詞彙難度」，絕對禁止使用未經解釋的進階專有名詞。請用最白話、最生活化的比喻來引導，一次只講一個重點，避免造成認知負荷超載。"
    elif learner_state == "TINKERING":
        tone_constraint = "\n【動態表達限制：TINKERING 階段】\n注意：使用者正在摸索與建構概念（TINKERING）。你可以適度引入專有名詞，但必須伴隨具體例證與解釋。鼓勵思辨，但避免過度拋出艱澀的哲學大哉問而讓使用者不知所措。"

    last_msg_hint = f"\n【禁止重複】上一次已經問過：「{last_compeer_message}」，本次訊息不得與此主題重複。" if last_compeer_message else ""

    if active_avatar:
        roleplay_instruction = f"你現在已被召喚為歷史人物/思想家：「{active_avatar}」。用戶正在學習或探討你的思想。\n請完全沉浸在這個角色中，用{active_avatar}特有的語氣（例如第一人稱、特有的哲學比喻或經典口吻），主動發一句話打斷用戶，丟出一個符合你身份的靈魂拷問或啟發式提問。"
    else:
        roleplay_instruction = "你是 AREQA，一個溫暖且專業的學習陪伴者。\n現在你需要主動關心用戶，根據以下資訊生成一句**精準的**主動關懷訊息。"

    prompt = f"""{roleplay_instruction}

【當前學習行為（Hot Memory）- 用戶正在面臨的狀況】
{hot_memory_snapshot}

【歷史學習背景（Cold Memory）- 僅供參考，若與當前狀況無關請忽略】
{cold_memory_context}

【當前學習者狀態】{learner_state}
【偵測到的挑戰摘要】{event_summary if event_summary else "（無特定事件，基於狀態主動關懷）"}
【建議策略】{hint}{tone_constraint}{last_msg_hint}

要求：
1. **必須絕對聚焦於「當前學習行為（Hot Memory）」與「挑戰摘要」**，針對用戶**現在**正在閱讀或提問的具體知識點給出提示。
2. 歷史學習背景（Cold Memory）僅用於了解用戶程度或過去喜好，**絕不可強行將過去的無關話題（如其他角色）插入當前關懷中**，以免造成上下文斷裂。
3. **對話必須以「引導式詢問」為主，用一個簡單的問題邀請用戶互動。絕對避免單向陳述或自顧自地說教。**
4. 繁體中文，語氣自然，如果扮演角色，請展現強烈的角色魅力，不要像機器人。
5. 長度控制在 60 字以內，直接輸出訊息本身，不要加任何前綴說明。"""

    try:
        from config import settings
        rsp = await gum_instance.client.chat.completions.create(
            model=settings.model_gum,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.6
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ComPeer] generate_scaffolding_message_via_llm failed: {e}")
        return "你學習狀況還好嗎？有任何問題都可以問我。"

async def generate_epistolary_letter_via_llm(
    user_id: str,
    active_avatar: str,
    hot_memory_snapshot: str,
    cold_memory_context: str
) -> str:
    gum_instance, _ = await _integration_module().get_gum_instance(user_id)
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
        print(f"[Mailbox] generate_epistolary_letter_via_llm failed: {e}")
        return "一封未知的信", f"來自{active_avatar}的一封信，因時空亂流未能完整送達。"


async def generate_areqa_care_letter_via_llm(
    user_id: str,
    hot_memory_snapshot: str,
    cold_memory_context: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str = "",
    last_compeer_message: str = "",
    allow_topic_specific: bool = False,
) -> tuple[str, str]:
    gum_instance, _ = await _integration_module().get_gum_instance(user_id)
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
        print(f"[Mailbox] generate_areqa_care_letter_via_llm failed: {e}")
        return "給你的學習小箋", "我注意到你最近可能有些卡住。先不用急著解決全部問題，我們可以只從一個最小的地方開始。你願意回信告訴我，現在最困住你的是哪一句或哪個想法嗎？"

async def delayed_reply_writer(user_id: str, mail_id: str, reply_content: str, active_avatar: str, delay_seconds: int = 300):
    print(f"[Mailbox] delayed_reply_writer started for mail_id {mail_id}, scheduling in {delay_seconds} seconds...")
    try:
        from mailbox_store import get_mailbox_store
        store = get_mailbox_store()

        await store.schedule_delayed_mail(user_id, {
            "reply_to_mail_id": mail_id,
            "reply_content": reply_content,
            "active_avatar": active_avatar,
            "conversation_id": mail_id
        }, delay_seconds)

        print(f"[Mailbox] delayed_reply_writer completed, scheduled new mail from {active_avatar} in response to {mail_id}.")
    except Exception as e:
        print(f"[Mailbox] delayed_reply_writer failed for {mail_id}: {e}")
