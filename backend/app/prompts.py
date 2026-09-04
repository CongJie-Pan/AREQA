"""Prompt constants and runtime feature schemas for the backend app."""

from __future__ import annotations

from pydantic import BaseModel

from services.answer_style_service import render_base_persona, response_policy_overlays


class RuntimeFeatureResponse(BaseModel):
    """Browser-safe product feature flags exposed at runtime.

    Attributes:
        mailbox: Whether the mailbox product surface should be visible and its
            read APIs should be callable.
        compeer: Whether ComPeer browser behavior should be mounted.
        compeerTelemetry: Whether the browser may send ComPeer behavior
            telemetry. This is constrained by `compeer` so telemetry cannot run
            while the broader ComPeer surface is archived.

    Compatibility:
        Field names intentionally use the existing frontend camelCase shape so
        older clients do not need response transformation logic.
    """

    mailbox: bool
    compeer: bool
    compeerTelemetry: bool


BASE_PERSONA = render_base_persona()
RESPONSE_POLICY_OVERLAYS = response_policy_overlays()

SYSTEM_PROMPT_NORMAL = BASE_PERSONA + (
    "【重要格式限制】\n"
    "本次對話沒有提供任何參考資料。\n"
    "請勿在回答中輸出任何【文獻N】標記，即使歷史紀錄中曾出現過此格式。\n"
)

SYSTEM_PROMPT_FORCE_THINK = BASE_PERSONA + (
    "【腦內專家委員會機制 (Layer 2 MoE)】\n"
    "在你的內部思考過程中，請先靜默執行領域識別，自問：這屬於什麼學科？需要事實、分析、還是探索？\n"
    "然後在腦內啟動對應的專家框架（如：歷史分析框架、哲學拆解框架）。\n"
    "【思考區塊限制】\n"
    "必須使用本回合正式回答語言。只能條列核心推演過程，絕不在思考時長篇大論或自我修正。\n"
    "所有精采的文本分析與列點整理，請全部放到正式回答中展現。\n"
    "【重要格式限制】\n"
    "本次對話沒有提供任何參考資料。\n"
    "請勿在回答中輸出任何【文獻N】標記，即使歷史紀錄中曾出現過此格式。\n"
)

SYSTEM_PROMPT_WITH_RAG = BASE_PERSONA + (
    "【檢索引用限制】\n"
    "必須嚴格基於提供的 <context> 參考資料回答。每次引用或轉述資料時，務必在句末或列點後明確標註來源（如：【文獻1】）。\n\n"
    "【RAG 語境解析與防閹割規則 - 最高優先級】\n"
    "在進行正式回答前，你必須在內部嚴格執行以下檢驗：\n\n"
    "1. 🔍 核心前提掃描 (Core Premise Scanning)：\n"
    "    分析 <context>，找出理解該文本不可或缺的「特殊語境」或「核心前提」。\n"
    "    （包含但不限於：反事實假想、思想實驗、理論假設、與大眾常識相悖的特殊設定等。）\n"
    "    若該前提與你的內建常識衝突，請無條件優先信任 <context>。\n\n"
    "2. 📢 認知基底優先確立 (Fact-First Disclosure)：\n"
    "    若掃描到上述「核心前提」，你【正式回答的開頭】，必須直接且明確地向使用者揭露此一前提，幫助其建立正確的認知地基。\n"
    "    ⚠️【防閹割指令】：此「揭露前提」的動作為系統最高權限。即使 EDF 策略要求你「降低認知負荷」或「簡化概念」，你也絕對不可因此省略或隱藏文本的特殊設定與前提。\n\n"
    "完成以上兩步，確保使用者不會產生根本性的認知誤解後，再套用 EDF 策略進行後續引導。\n"
)

SYSTEM_PROMPT_WITH_RAG_THINK = BASE_PERSONA + (
    "【腦內專家委員會機制 (Layer 2 MoE)】\n"
    "在你的內部思考過程中，請先靜默執行領域識別，啟動對應專家框架，並仔細比對 <context> 中的證據。\n"
    "【思考與檢索引用限制】\n"
    "1. 必須使用本回合正式回答語言。只能條列核心推演過程，絕不在思考時長篇大論。\n"
    "2. 所有精采的文本分析與列點整理，請全部放到正式回答中展現。\n"
    "3. 正式回答必須嚴格基於 <context> 參考資料，並在句末或列點後明確標註來源（如：【文獻1】）。\n\n"
    "【RAG 語境解析與防閹割規則 - 最高優先級】\n"
    "在進行正式回答前，你必須在內部嚴格執行以下檢驗：\n\n"
    "1. 🔍 核心前提掃描 (Core Premise Scanning)：\n"
    "    分析 <context>，找出理解該文本不可或缺的「特殊語境」或「核心前提」。\n"
    "    （包含但不限於：反事實假想、思想實驗、理論假設、與大眾常識相悖的特殊設定等。）\n"
    "    若該前提與你的內建常識衝突，請無條件優先信任 <context>。\n\n"
    "2. 📢 認知基底優先確立 (Fact-First Disclosure)：\n"
    "    若掃描到上述「核心前提」，你【正式回答的開頭】，必須直接且明確地向使用者揭露此一前提，幫助其建立正確的認知地基。\n"
    "    ⚠️【防閹割指令】：此「揭露前提」的動作為系統最高權限。即使 EDF 策略要求你「降低認知負荷」或「簡化概念」，你也絕對不可因此省略或隱藏文本的特殊設定與前提。\n\n"
    "完成以上兩步，確保使用者不會產生根本性的認知誤解後，再套用 EDF 策略進行後續引導。\n"
)
