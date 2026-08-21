# AREQA PARTS + Gemini-like Image Slot Plan

## Goal

Use LearnLM PARTS as a stable per-turn prompt-engineering layer, and add a
Gemini-like inline image display flow without depending on Gemini private
`image_agent_tag_*` handles.

## PARTS Rewrite Flow

Data flow:

```text
latest user message
  + cleaned previous assistant context
  + response policy
  + turn route / RAG / web / attachment state
  -> PartsContextService
  -> policy model JSON rewrite
  -> validate / sanitize
  -> composed_instruction
  -> ConversationContextService system prompt
  -> main model + original conversation messages
```

`previous_assistant_context` comes from the latest assistant message in the same
conversation. Before sending it to PARTS rewrite:

- remove source sections such as `文獻來源`, `參考文獻`, `References`, `Sources`
- remove inline citations such as `【文獻13】` or `[1]`
- keep the cleaned assistant text as context for follow-up references

## PARTS JSON Shape

```json
{
  "persona": "歷史思考教練",
  "act": "承接前文分析日本為何未優先透過商業發展解決資源困境",
  "recipient": "程度未知的學習者，不假設已掌握日本近現代史或經濟史脈絡",
  "theme": "二戰前日本面對資源困境時的商業外交與軍事擴張選擇",
  "structure": "承接前文 + 一小段歷史背景 + 因果分析 + 一個開放式追問",
  "composed_instruction": "請承接上一輪日本二戰歷史脈絡，說明當時日本為何沒有優先透過發展商業或外交談判處理資源困境，而轉向軍事擴張。不要把問題改寫成一般商業發展利弊，也不要一次展開完整二戰時間線。",
  "confidence": "high",
  "missing_fields": ["recipient_level"]
}
```

Main model follows only `composed_instruction`; PARTS fields are retained for
debugging and observability. The model must not output P/A/R/T/S labels.

## Rewrite Rules

- Short learning-topic queries may be treated as learning entry points when the
  user did not explicitly ask for a complete summary, timeline, key-point list,
  or final answer.
- Learning entry points should prefer a warm subject coach, one small step,
  Socratic questioning, and a focused guiding question.
- Follow-up phrases such as `那`, `這個`, `為何`, or `怎麼辦` should be resolved
  against `previous_assistant_context`.
- PARTS must not override citation rules, attachment grounding, memory safety,
  tool authorization, or safety policy.
- Timeout, malformed JSON, low confidence, or missing provider should fall back
  to deterministic PARTS.

## Runtime Flags

```python
enable_parts_prompt_context = True
enable_parts_llm_rewrite = True
parts_rewrite_timeout_ms = 2500
enable_parts_prompt_debug_logs = True  # local diagnosis only
```

Debug logs may show raw user text, cleaned previous assistant context inside the
rewrite prompt, selected PARTS fields, and `composed_instruction`.

## Gemini-like Image Slot Flow

Gemini export uses private handles like:

```text
<Image alt="..." caption="..." src="image_agent_tag_..."/>
```

AREQA should not use those handles. Use AREQA-owned slot placeholders:

```text
<AREQA_IMAGE_SLOT id="img_1" alt="中國東北（滿洲）地理位置圖" caption="中國東北（滿洲）地理位置" query="中國東北 滿洲 地圖"/>
```

Image data flow:

```text
main model emits AREQA_IMAGE_SLOT
  -> backend strips slot markers from public text
  -> backend converts slots into structured image requests
  -> VisualAnswerService resolves images through providers
  -> grounding / license / safety / confidence checks
  -> backend emits image_block
  -> frontend renders inline image card between paragraphs
```

`image_block` shape:

```json
{
  "type": "image_block",
  "slot_id": "img_1",
  "alt": "中國東北（滿洲）地理位置圖",
  "caption": "中國東北（滿洲）地理位置",
  "image_url": "https://...",
  "source_url": "https://...",
  "source_domain": "commons.wikimedia.org",
  "license": "Public domain",
  "match_confidence": 0.88
}
```

If no verified image is found, silently omit the entire image slot. Do not render
fallback text, broken-image UI, or unresolved slot placeholders.

## Tests

- PARTS rewrite receives cleaned previous assistant context for follow-up turns.
- Citation/source noise is removed before rewrite.
- Follow-up question stays on prior topic instead of drifting to a generic topic.
- `composed_instruction` is injected and P/A/R/T/S labels are not requested as
  output.
- Timeout, invalid JSON, and low confidence still fall back safely.
- `AREQA_IMAGE_SLOT` markers are removed from public text.
- Valid image slots become image block requests.
- Failed image retrieval emits no broken image, fallback text, or unresolved
  placeholder.
- Frontend renders verified image blocks with caption and source attribution.
