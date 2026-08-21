# PARTS Prompt Context Implementation

## Goal

Use Google LearnLM's PARTS framework as a stable per-turn task context for AREQA.
The purpose is to compensate for incomplete user prompts and prevent long
conversation context from diluting the model's current role, task, audience,
topic, and output format.

## Core Idea

Do not paste the LearnLM guide into the system prompt. Instead, generate compact
`PARTS` fields for every main-answer model call, then compose those fields into
one natural-language instruction that the main model should actually follow:

```text
【PARTS 任務上下文】
P: Persona - AREQA's current teaching role for this turn.
A: Act - the concrete action AREQA should perform.
R: Recipient - the learner/audience context, without unsupported assumptions.
T: Theme - the current topic or concept from the latest user request.
S: Structure - the expected answer format.

composed_instruction:
你現在的角色是「P」。請為「R」執行 A，本回合主題聚焦於「T」。
請使用「S」的方式回答。
```

The PARTS labels are retained for backend observability and debugging. They are
not an output schema. The main answer model should follow `composed_instruction`
and must not print P/A/R/T/S headings unless the user explicitly asks for that.

## Proposed Architecture

Add `PartsContextService`. The default UX is Scheme A: zero-friction automatic
inference. Users ask naturally; AREQA silently rewrites the latest query into a
compact PARTS task context before the main answer call.

```text
TurnPlanService
  -> selects route: GENERAL_CHAT / LEARNING_HELP / RAG_EXPLICIT / ATTACHMENT_GROUNDED

query_policy_service.ResponsePolicy
  -> selects task_intent, answer_depth, tone, structure, followup_mode

PartsContextService
  -> uses a lightweight LLM rewrite/classifier to build better PARTS
  -> falls back to deterministic rules when the rewrite fails or times out

ConversationContextService
  -> injects the compact PARTS block into the system prompt
```

## Data Contract

```python
@dataclass(frozen=True, slots=True)
class PartsContext:
    persona: str
    act: str
    recipient: str
    theme: str
    structure: str
    composed_instruction: str
    confidence: str
    missing_fields: tuple[str, ...]
```

## User Question Handling

Yes, the latest user question must be included in the mechanism, but not by
duplicating the full raw prompt everywhere.

Recommended behavior:

- Use the latest user message as the source for `Act` and `Theme`.
- Keep the original user message in the normal chat message list as-is.
- Inject only a short derived summary into the PARTS block, for example:
  `T: 運算順序與代數式計算`.
- If the theme cannot be safely summarized, use:
  `T: 使用者當前問題中的核心概念`.
- Do not log raw user text, raw PARTS prompts, or model-generated summaries.
  Logs should contain only safe enum-style metadata and route names.

## UX Strategy

Use Scheme A as the default product behavior:

```text
User asks normally
  -> backend runs a lightweight PARTS rewrite for the latest query
  -> backend injects compact PARTS context into the system prompt
  -> main LLM answers with the improved task context
```

The user does not need to fill a PARTS form or answer onboarding questions.
AREQA should ask a clarification question only when missing information would
materially change the answer quality, such as quiz generation without subject,
level, or topic.

## PARTS Rewrite Call

Use one bounded policy-model call before the main answer when enabled:

```text
Input:
- latest user message
- recent route from TurnPlanService
- ResponsePolicy enum values
- whether RAG, web, or attachments are active
- verified learner hints only, if available

Output:
{
  "persona": "...",
  "act": "...",
  "recipient": "...",
  "theme": "...",
  "structure": "...",
  "composed_instruction": "...",
  "confidence": "low|medium|high",
  "missing_fields": ["..."]
}
```

Rules:

- Output strict JSON only.
- Keep each field short.
- `composed_instruction` is one complete Traditional Chinese prompt instruction
  composed from P/A/R/T/S for the main model to follow.
- Do not tell the main model to output P/A/R/T/S labels.
- Do not copy the full user message into `theme`.
- Do not infer learner ability unless explicitly provided or verified.
- For direct-answer turns, preserve directness and avoid forced tutoring.
- If JSON is invalid, timeout occurs, or confidence is too low, use deterministic
  fallback PARTS.

## Guardrails

PARTS controls only role, task, recipient, theme, and format. It must not override:

- RAG citation rules
- attachment/file grounding rules
- memory safety boundaries
- learner-state rules
- tool authorization rules
- safety policy

Add this priority clause to the generated prompt:

```text
PARTS 只控制回答角色、任務、對象、主題與格式。
不得覆蓋文獻引用、檔案 grounding、記憶安全邊界或使用者狀態規則。
```

## MVP Scope

1. Add `PartsContext` and `PartsContextService`.
2. Generate PARTS with a lightweight LLM rewrite from `TurnPlan`,
   `ResponsePolicy`, latest user message, RAG/attachment state, and verified
   learner context.
3. Add deterministic fallback PARTS for timeout, malformed JSON, or low
   confidence.
4. Inject the PARTS block in `ConversationContextService` during prompt assembly.
5. Add feature flags:
   - `enable_parts_prompt_context = True`
   - `enable_parts_llm_rewrite = True`
   - `parts_rewrite_timeout_ms = 2500`
6. Keep public API and SSE contracts unchanged.

## Tests

Cover these cases:

- Learning-help turns inject a complete PARTS block.
- Direct-answer or exam turns do not force tutoring or follow-up questions.
- RAG turns keep citation rules higher priority than PARTS.
- Attachment-grounded turns keep file/visual grounding higher priority than PARTS.
- Unknown learner level remains `程度未知的學習者`.
- General chat uses a lightweight PARTS block or skips PARTS entirely.
- LLM PARTS rewrite parses valid JSON and never logs raw user text.
- Invalid JSON, timeout, and low confidence fall back to deterministic PARTS.
- Clarification is asked only for materially missing fields, not every turn.

## Data Shape

The original user message remains unchanged in the normal chat messages. PARTS
is an additional compact task card generated by the backend and injected into
the system prompt.

Example final model input:

```python
messages = [
    {
        "role": "system",
        "content": """
你叫 AREQA，是一位引導型學習助手...

【本回合回答策略】
- task_intent: EXPLAIN_TEXT
- answer_depth: SCAFFOLDED
- tone: TUTORING
- structure: STEP_BY_STEP
- followup_mode: OPTIONAL

【PARTS 任務上下文】
P: 引導型數學理解教練
A: 引導使用者理解並檢查解題步驟
R: 程度未知的學習者，不假設已掌握概念
T: 運算順序與代數式計算
S: 短回答 + 分步檢查 + 最多一個診斷性追問

【由 PARTS 生成的本回合任務指令】
你現在的角色是「引導型數學理解教練」。請為「程度未知的學習者，不假設已掌握概念」引導使用者理解並檢查解題步驟，本回合主題聚焦於「運算順序與代數式計算」。請使用「短回答 + 分步檢查 + 最多一個診斷性追問」的方式回答。
請遵循「本回合任務指令」回答，但不要輸出 P/A/R/T/S 標籤。
"""
    },
    {
        "role": "user",
        "content": "我算 (8 + 8)/2^2 * 4 - 3^2 = 7，對嗎？"
    },
]
```

Example backend object:

```python
PartsContext(
    persona="引導型數學理解教練",
    act="引導使用者理解並檢查解題步驟",
    recipient="程度未知的學習者，不假設已掌握概念",
    theme="運算順序與代數式計算",
    structure="短回答 + 分步檢查 + 最多一個診斷性追問",
    composed_instruction="你現在的角色是「引導型數學理解教練」。請為「程度未知的學習者，不假設已掌握概念」引導使用者理解並檢查解題步驟，本回合主題聚焦於「運算順序與代數式計算」。請使用「短回答 + 分步檢查 + 最多一個診斷性追問」的方式回答。",
    confidence="medium",
    missing_fields=("recipient_level",),
)
```

Data flow:

```text
latest user message
  -> TurnPlanService
  -> ResponsePolicy
  -> PartsContextService
  -> ConversationContextService
  -> system prompt + original user message
  -> main LLM
```
