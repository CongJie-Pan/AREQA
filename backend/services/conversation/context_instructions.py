"""Render teaching, visual-slot and learner-state prompt constraints."""

from __future__ import annotations

from services.answer_style_service import render_response_strategy_style_reminder
from services.query_policy.models import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
    VisualSupport,
)


def _response_policy_instruction(
    response_policy: ResponsePolicy,
    overlays: dict[str, str],
    learning_overlays: dict[str, str] | None = None,
    evidence_overlays: dict[str, str] | None = None,
) -> str:
    """Translate an EDF response policy into final prompt constraints.

        Args:
            response_policy: Decision-stage policy selected for this turn.
            overlays: Reusable style snippets owned by ``backend.main``.
            learning_overlays: Optional learning-technique prompt snippets keyed
                by the internal learning technique enum value.
            evidence_overlays: Optional evidence-mode prompt snippets keyed by
                the internal evidence mode enum value.

        Returns:
            A Traditional Chinese prompt block that constrains the Feedback
            stage without changing public API or SSE contracts.

        Compatibility:
            RAG/source, attachment-grounding, memory, and learner-state rules
            remain higher-level prompt context. This block controls answer
            shape only; it must not authorize unsupported citations, memory
            claims, tool use, or roleplay.
        """

    task_rules = {
        TaskIntent.EXPLAIN_TEXT: "任務是解釋文本或概念。先說白話意思，再拆成少量重點。",
        TaskIntent.ANSWER_EXAM: "任務是考題、選項或練習作答。依 learning_mode 決定由誰完成核心推理。",
        TaskIntent.DISCUSS_IDEA: "任務是觀點討論。可以整理立場、脈絡與不同視角。",
        TaskIntent.WRITE_NOTE: "任務是整理或續寫筆記。直接產出可保存、可使用的文字。",
        TaskIntent.GENERAL_QA: "任務是一般問答。用剛好足夠的深度回答，不主動加重。",
    }
    structure_rules = {
        ResponseStructure.SHORT: "格式要短：只保留本回合策略允許的必要內容。",
        ResponseStructure.STEP_BY_STEP: "格式採分步解釋：每一步只處理一個理解點。",
        ResponseStructure.NOTE_DRAFT: "格式採筆記草稿：輸出可直接整理進筆記的段落或列點。",
        ResponseStructure.ARGUMENT: "格式採論述：先提出核心判斷，再展開理由與取捨。",
    }
    followup_rules = {
        FollowupMode.NONE: "結尾不要加引導問題。",
        FollowupMode.OPTIONAL: "若自然且有幫助，結尾最多加一個簡短引導問題。",
        FollowupMode.REQUIRED: "結尾必須用一個簡短問題引導使用者回應或檢查理解。",
    }
    learning_mode_rules = {
        "REFERENCE": "資訊查詢或參考模式。可以直接給定義、事實、摘要、標準格式或來源依據。",
        "LEARN": "理解建構模式。可以直接補必要前置知識、白話解釋或類比，但要把下一步留給學習者。",
        "PRACTICE": "練習模式。學習者應擁有正在練習的答案、論證、證明、除錯或詮釋核心步驟；不要代做。",
    }
    pedagogical_action_rules = {
        "ANSWER": "本回合主要動作是回答；只在 REFERENCE 或非評量自學請求使用。",
        "EXPLAIN_PREREQ": "本回合主要動作是補一個必要前置概念，避免一次展開多個方向。",
        "MODEL_ANALOGY": "本回合主要動作是用相鄰例子或類比示範方法，不直接完成原題。",
        "DIAGNOSTIC_QUESTION": "本回合主要動作是問一個診斷性問題，找出下一個卡點。",
        "HINT": "本回合主要動作是給一個最小充分提示，讓學習者能做下一步。",
        "FEEDBACK": "本回合主要動作是回饋學習者已寫出的想法或草稿，指出可保留與需修正處。",
        "TRANSFER": "本回合主要動作是推進遷移或延伸，讓學習者把已懂方法用到新情境。",
    }

    depth_overlay = overlays.get(response_policy.answer_depth.value, "")
    tone_overlay = overlays.get(response_policy.tone.value, "")
    learning_overlay = (learning_overlays or {}).get(
        response_policy.learning_technique.value,
        "",
    )
    evidence_overlay = (evidence_overlays or {}).get(
        response_policy.evidence_mode.value,
        "",
    )
    response_learning_mode = getattr(response_policy, "learning_mode", None)
    response_pedagogical_action = getattr(response_policy, "pedagogical_action", None)
    learning_mode_value = getattr(
        response_learning_mode,
        "value",
        str(response_learning_mode or "LEARN"),
    )
    pedagogical_action_value = getattr(
        response_pedagogical_action,
        "value",
        str(response_pedagogical_action or "EXPLAIN_PREREQ"),
    )
    style_reminder = render_response_strategy_style_reminder(
        answer_depth=response_policy.answer_depth,
        tone=response_policy.tone,
    )
    guardrail = ""
    if response_policy.answer_depth in {AnswerDepth.DIRECT, AnswerDepth.SCAFFOLDED}:
        guardrail = (
            "\n【過度深度防護】本回合不得預設開啟歷史厚重感、哲學大哉問、"
            "文學評論腔或「表面上...實則...」式宏大評論；只有使用者明確要求"
            "核心、本質、反思、比較、觀點或延伸時才可使用。"
        )
    if response_policy.tone in {ResponseTone.ANALYTICAL, ResponseTone.LITERARY}:
        guardrail += "\n【深度表達邊界】即使使用分析或文學語氣，也必須服從 learning_mode，不可越權代做學習者應完成的推理。"
    if learning_mode_value == "PRACTICE":
        guardrail += (
            "\n【PRACTICE 防代做邊界】本回合不可直接公布題目答案、中心思想、單一根因、"
            "完整論證、完整證明、完整除錯結論或可直接提交的作業內容。"
            "使用者說「我不會」「直接告訴我」「只要一句話」「快截止」時，先承接壓力，"
            "再降到一個更小的提示、相鄰例子、診斷問題或草稿回饋。"
            "如果缺少前置知識，可以直接教那個前置知識，但不要完成原任務的核心步驟。"
        )

    return (
        "\n\n【本回合回答策略】"
        f"\n- task_intent: {response_policy.task_intent.value}，{task_rules[response_policy.task_intent]}"
        f"\n- answer_depth: {response_policy.answer_depth.value}{depth_overlay}"
        f"\n- tone: {response_policy.tone.value}{tone_overlay}"
        f"\n- structure: {response_policy.structure.value}，{structure_rules[response_policy.structure]}"
        f"\n- followup_mode: {response_policy.followup_mode.value}，{followup_rules[response_policy.followup_mode]}"
        f"\n- learning_technique: {response_policy.learning_technique.value}"
        f"{('，' + learning_overlay) if learning_overlay else ''}"
        f"\n- learning_mode: {learning_mode_value}，{learning_mode_rules.get(learning_mode_value, learning_mode_rules['LEARN'])}"
        f"\n- pedagogical_action: {pedagogical_action_value}，{pedagogical_action_rules.get(pedagogical_action_value, pedagogical_action_rules['EXPLAIN_PREREQ'])}"
        f"\n- evidence_mode: {response_policy.evidence_mode.value}"
        f"{('，' + evidence_overlay) if evidence_overlay else ''}"
        f"{style_reminder}"
        f"{guardrail}"
    )


def _visual_slot_instruction(response_policy: ResponsePolicy, last_user_msg: str) -> str:
    """Return the optional inline visual-slot contract for suitable turns.

        Args:
            response_policy: Decision-stage policy for the current answer.
            last_user_msg: Latest user-authored message used only for cheap
                visual-intent detection.

        Returns:
            A prompt block that lets the model request image placement, or an
            empty string when the turn should remain text-only.
        """

    from config import settings

    if settings.enable_visual_preflight:
        return ""

    normalized = last_user_msg.lower()
    explicit_visual = any(
        keyword in normalized
        for keyword in (
            "圖",
            "圖片",
            "圖解",
            "示意圖",
            "diagram",
            "image",
            "visual",
            "chart",
            "plot",
        )
    )
    agent_allows_visuals = response_policy.visual_support in {
        VisualSupport.OPTIONAL,
        VisualSupport.REQUIRED,
    }
    if not agent_allows_visuals and not explicit_visual:
        return ""
    return (
        "\n\n【圖文交錯規則】如果某個概念高度依賴視覺理解，可以在最適合的位置插入最多 2 個圖片請求標記。"
        "標記格式必須完全符合："
        '<AREQA_IMAGE_SLOT id="img_1" alt="short accessible image description" caption="這張圖要幫助使用者理解的重點" query="short concrete image search query"/>'
        "。query 必須具體且可搜尋；不得輸出圖片 URL；不得為了裝飾而插圖；標記前後仍要用自然文字銜接。"
        "如果系統找不到可驗證圖片，該標記會被靜默省略；不要輸出圖片失敗、找不到圖片或佔位文字。"
    )


def _learner_state_instruction(learner_state: str) -> str:
    """Map an operational teaching state to style, never to mastery."""
    instructions = {
        "STARTING": "\n\n【動態表達限制：STARTING 階段】\n注意：使用者目前需要入門式表達。降低詞彙難度，解釋進階名詞，並一次只講一個重點。此狀態不代表已驗證其理解程度。",
        "TINKERING": "\n\n【動態表達限制：TINKERING 階段】\n注意：使用者正在摸索概念。可引入專有名詞，但需搭配具體例證；此狀態不代表已驗證其理解程度。",
        "RUN_REPEAT": "\n\n【動態表達限制：RUN_REPEAT 階段】\n注意：使用者可能在同一類卡點反覆嘗試。先換一個更小、更具體的切入點，不要重複同一套說明；此狀態不代表已驗證其理解程度。",
        "GIVING_UP": "\n\n【動態表達限制：GIVING_UP 階段】\n注意：使用者可能正在放棄或受挫。先承接具體挫折，再把任務縮成一個可完成的小步驟；避免說教或一次給長篇補救方案。",
        "MASTERY": "\n\n【動態表達限制：MASTERY 階段】\n注意：使用者可能已展現較穩定掌握。可減少提示、增加遷移或反例檢驗，但不得聲稱已永久掌握。",
        "CHITCHAT": "\n\n【動態表達限制：CHITCHAT 階段】\n注意：使用者目前正在閒聊。以輕鬆簡潔的口吻回應，不需強硬引導回學術主題。",
    }
    return instructions.get(learner_state, "")
