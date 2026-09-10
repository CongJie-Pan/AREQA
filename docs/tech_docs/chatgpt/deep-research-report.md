# Why AREQA Live Voice and Video Avatar Responses Are Shallower Than Text Chat

## Executive finding and research boundary

The most likely root cause is not a single weak voice model. It is an objective-function and architecture mismatch: AREQA’s text pipeline appears to be optimised for *answer completeness, grounding and educational depth*, while its Live Voice/video-avatar pipeline appears to be optimised for *low latency, short turns, interruptibility and conversational flow*. The resulting quality gap is therefore produced by several reinforcing constraints: a terse voice prompt, reduced access to authoritative context, a latency-oriented model/pipeline, and response-budget/turn-taking policies.

Based on the behaviour you described, I would rank the blanket brevity/turn-taking policy as the strongest proximate cause of the obvious shallowness, and context asymmetry as the strongest cause of poorer grounding on papers, PDFs and complex learning material. Model choice then determines the ceiling once those first two issues are corrected. Token limits and avatar/turn-detection constraints amplify the problem but are less likely to be the fundamental cause.

A particularly important diagnostic clue is your observation that the same voice experience becomes substantially better when the user explicitly says “give me concrete examples” or “go into more detail”. That is hard to reconcile with a pure capability limitation. It is much more consistent with a capable-enough model obeying an overly aggressive default verbosity policy. Current OpenAI guidance explicitly recommends defining response length by task type rather than giving realtime models a blanket “be concise” instruction. For example, direct answers can remain one or two sentences while comparisons and other complex requests receive enough space for trade-offs and explanation. citeturn13view1

At the same time, improving the prompt alone will not create text-mode parity if the voice agent is genuinely receiving only attachment names, abbreviated memory, or document summaries. Current Realtime APIs allow applications to construct custom response contexts and explicitly inject whatever context is appropriate, while newer realtime models have substantially larger context windows. In other words, weak document grounding is an integration choice rather than an unavoidable property of realtime voice. citeturn13view4turn13view3

There is one important limitation to this research: I was not able to inspect AREQA's private source code, production prompts or session traces in this session. I therefore treat the implementation details in your context — such as the “one to three sentences” policy, bounded context bridge, realtime-mini usage and differing PARTS/retrieval pipelines — as hypotheses supplied by you, not independently verified facts. The conclusions below are consequently a high-confidence architectural diagnosis plus a falsifiable test plan, rather than a line-by-line forensic audit of AREQA.

Bottom-line diagnosis: AREQA is probably asking two different systems to solve two different optimisation problems and then comparing their answer quality as though they were equivalent:

> Text: “Produce the best complete educational answer.”  
> Voice: “Keep the conversation moving quickly and naturally.”

To achieve text-like intellectual quality in voice, AREQA should decouple “how quickly/naturally the system interacts” from “how deeply the system thinks and grounds its answer.” That is now an explicit pattern in modern voice architecture. OpenAI's July 2026 GPT‑Live architecture, for example, separates continuous realtime interaction from deeper work: the voice model maintains conversational flow while complex search or reasoning is delegated to a frontier model and the result is brought back into the live conversation. citeturn12view9

## Root-cause analysis and ranked contributing factors

### The central problem is a policy-and-pipeline mismatch

Voice systems do legitimately need different presentation behaviour from text systems. Spoken prose cannot simply be a 1,500-word markdown essay read aloud. LiveKit's own voice-agent prompting guidance says users generally have less patience for long spoken monologues and gives a common default of one to three sentences and one question at a time. It also recommends breaking many real-world voice applications into workflows, tasks or handoffs rather than relying on a single prompt. citeturn16view4

That advice is sensible for customer service, booking, simple lookup and transactional agents. It becomes harmful, however, if AREQA applies the same rule indiscriminately to requests such as:

> “Explain this paper to me in depth.”  
> “Why does this method work?”  
> “Walk me through the theory and methodology.”  
> “Give me a concrete example and explain the limitations.”

A tutoring system cannot satisfy those intents in one to three sentences without discarding requested information. The problem is therefore not that concise voice UX is inherently wrong; it is that a local presentation heuristic has apparently become a global content policy.

OpenAI's current realtime prompting guidance makes almost exactly this distinction: it recommends defining verbosity according to task type instead of globally saying “be concise”. It also treats reasoning effort, verbosity, tools, preambles and long-context behaviour as separate prompt concerns. citeturn13view0turn13view1

### Ranked factors

| Rank | Contributing factor | Likely importance | What it explains particularly well | Diagnostic confidence |
|---|---|---:|---|---|
| First | Blanket voice brevity / forced turn-taking policy | Very high | One- or two-paragraph replies; premature follow-up questions; dramatic improvement after “give more detail” | High |
| Second | Context-grounding asymmetry | Very high for document questions | Generic paper explanations, missing terminology, weak evidence, inability to discuss specific methodology/limitations | High if your bridge description is accurate |
| Third | Different model / reasoning pipeline | High | Lower sophistication even after verbosity is relaxed; weaker synthesis and multi-step reasoning | Medium-high |
| Fourth | Output and latency budgets | Medium-high | Truncation, abbreviated examples, avoidance of long derivations | Medium until configs are measured |
| Fifth | Realtime UX/turn-management policy | Medium | Frequent “What would you like to explore?” endings; reluctance to continue; over-segmentation | High as a design effect |
| Sixth | Video-avatar layer itself | Low for semantics; meaningful for latency | Additional playback delay and perhaps more pressure to shorten turns | High that it is not the main intellectual bottleneck |

### Prompt policy is probably the main cause of the *length* gap

Your “detail recovery” observation is the strongest evidence here. Suppose the model replies initially:

> “The paper proposes a new attention mechanism that improves efficiency. The main idea is to reduce redundant computation. Would you like me to explain the architecture?”

Then, after:

> “Yes, explain exactly how it works and give an example,”

it produces a substantially better explanation.

That pattern means the underlying model had enough latent capability to go further but had initially inferred that it should stop. A hard 300-token output ceiling or severe model-capability deficiency would not be so easily overcome merely by strengthening the user's request.

Current realtime guidance also states that newer realtime models follow task-specific length guidance and explicitly recommends assigning different response lengths to direct answers, tool results, comparisons, troubleshooting and similar categories. citeturn13view1

The suspected “always finish with an open question” rule would further compound this. In tutoring, questions are pedagogically useful, but they should come after substantive fulfilment of the learner's current request, not as a mechanism for prematurely terminating every explanation. Research on AI-tutor evaluation distinguishes a good tutor from a generic question-answering system and measures dimensions such as relevant guidance, actionability, coherence, tutor tone and human-likeness; guidance can include explanations, hints and examples rather than merely asking another question. citeturn17view0

### Context asymmetry is probably the main cause of the *grounding* gap

For complex education, the model is only as good as the evidence it receives.

Imagine text mode gets:

> the full paper  
> + extracted figures/tables  
> + relevant retrieval chunks  
> + current task state  
> + conversation history  
> + pedagogical instructions

while Live Voice gets:

> `Attention_Is_All_You_Need.pdf`  
> + “User is studying transformers”  
> + a short memory summary.

Even with the identical model, those are fundamentally different tasks. The first system can discuss the paper; the second can mainly discuss *what it generally knows about papers like it*.

Modern Realtime infrastructure does not require this impoverishment. OpenAI allows a realtime response to be generated from a custom context outside the default conversation, including newly supplied inputs or references to previous items. citeturn13view4 Current Realtime-2 documentation describes a 128,000-token context window and advises applications handling large contexts to distinguish current state, authoritative sources and historical/background information rather than dumping an undifferentiated transcript into the model. citeturn13view3turn13view5

This leads to an important architectural principle:

Text and voice should not maintain separate notions of “what the user is studying”.

They should query the same canonical grounding layer.

For a paper question, both should receive the same retrieved passages, section/page metadata, user-selected attachment identity and task objective. Voice can receive fewer *irrelevant* tokens than text, but it should not receive materially less *evidence*.

### Model choice creates a real ceiling, but that ceiling is no longer inherent to “realtime”

If AREQA is using a smaller/older realtime-mini model while text uses a substantially stronger reasoning model, that obviously introduces an additional quality gap. A lightweight speech model may handle conversational reactions and straightforward questions extremely well while still being worse at multi-step conceptual synthesis, comparing hypotheses or reconstructing a complex paper argument.

However, it would now be misleading to conclude that “realtime models are intrinsically too small for deep responses”. As of September 2026, OpenAI's current documentation identifies `gpt-realtime-2.1` as the low-latency voice-agent path, while GPT-Realtime-2 supports configurable reasoning effort, a 128k context window and up to 32k output tokens. Its documentation explicitly says higher reasoning effort can trade additional latency and output usage for deeper reasoning. citeturn13view6turn13view5

This changes the diagnosis substantially:

Old framing

> Realtime voice is intrinsically shallow because realtime models cannot reason deeply.

Better 2026 framing

> Realtime voice can perform substantially deeper work, but high-quality systems should dynamically allocate reasoning, context and model capability according to task complexity rather than forcing every turn through one low-latency configuration.

OpenAI now recommends starting production voice agents at relatively low reasoning effort and increasing it when task complexity or failure cost warrants it; medium effort is suggested for multi-step tasks rather than the simplest interactions. citeturn13view0

More importantly, GPT‑Live's architecture goes further by decoupling realtime interaction from deep reasoning altogether. That is strong evidence that even vendors with increasingly capable native voice models see architectural value in a fast conversational model plus a stronger delegated thinker. citeturn12view9

### Token limits matter, but they may be an implementation cap rather than an API cap

If AREQA sets a low per-response `max_output_tokens`, explicit duration limit, TTS character budget or internal “stop after N sentences” rule, that is a hard ceiling regardless of prompt quality.

But an extremely short answer should not automatically be attributed to the Realtime API itself. Current GPT-Realtime-2 exposes up to 32,000 maximum output tokens, vastly more than needed for an ordinary spoken explanation. citeturn13view5

Therefore the useful question is not:

> “Does realtime have fewer tokens than text?”

It is:

> “At every layer between the user's turn and playback, what is the effective response budget?”

AREQA should instrument at least:

`requested max output → generated semantic tokens → speech-realiser tokens → TTS characters/audio duration → actually played content`

That will reveal whether shortening is occurring in the model call, a secondary summariser, the TTS/avatar adapter, a timeout, or the system prompt.

### Realtime UX constraints are real but need not imply intellectual shallowness

Realtime systems are built around latency and turn-taking. OpenAI explicitly positions Realtime sessions for live audio where low latency matters. citeturn13view6 LiveKit likewise supports both native speech-to-speech realtime models and cascaded STT–LLM–TTS architectures, which means product teams can choose different intelligence/latency trade-offs rather than adopting one universal architecture. citeturn16view5

The critical design mistake is equating:

interruptible = short

Those are not the same property.

A deep explanation can consist of five 20-second conceptual chunks and still be highly interruptible. A 90-second explanation can begin speaking after one second if the first chunk is generated or an appropriate preamble is available. A realtime responder can also stop immediately if the learner interrupts, without preventing the underlying thinker from having produced a detailed answer plan.

Current Realtime prompting guidance explicitly supports brief preambles before longer reasoning or tool-use flows. citeturn13view0 The architecture therefore should optimise separately for:

- time to first meaningful audio;
- depth/completeness of the full answer;
- interruptibility.

Trying to optimise all three by shrinking the answer to two sentences predictably sacrifices the second.

### The avatar should be a renderer, not the intellectual engine

Nothing about an animated video avatar inherently requires a shallower semantic answer. LiveKit exposes virtual-avatar support separately from the language/realtime model choices, and its architecture supports multiple speech/intelligence pipelines. citeturn16view5

Avatar rendering can increase user-perceived delay. LiveKit's per-turn telemetry explicitly includes `playback_latency`, and notes that this is particularly relevant when a remote avatar worker is in the chain. citeturn12view5

That is a reason to optimise animation/audio streaming, not to make the underlying explanation intellectually worse.

AREQA should therefore architect:

> knowledge/reasoning → semantic answer → spoken realisation → audio → avatar animation

rather than:

> avatar mode → separate small “avatar chatbot brain”.

## Recommended architecture for a deep voice mode

### Use a dual-path interaction architecture

The strongest design is a fast interaction path plus a deep cognition path, sharing the same context/retrieval substrate.

```text
                         ┌──────────────────────────┐
User speech/video ─────► │ Realtime interaction     │
                         │ VAD / transcription /     │
                         │ interruption management   │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ Depth / task router       │
                         │                          │
                         │ quick? explanation?       │
                         │ document-grounded?        │
                         │ multi-step? user asks     │
                         │ "deep", "why", "example"? │
                         └───────┬─────────┬────────┘
                                 │         │
                       FAST PATH │         │ DEEP PATH
                                 ▼         ▼
                      ┌─────────────┐  ┌───────────────────────┐
                      │ Realtime     │  │ Canonical AREQA       │
                      │ model        │  │ answer pipeline       │
                      │ low/medium   │  │                       │
                      │ reasoning    │  │ PARTS / retrieval /   │
                      └──────┬──────┘  │ PDFs / memory /      │
                             │         │ stronger reasoning     │
                             │         └───────────┬───────────┘
                             │                     │
                             │                     ▼
                             │          ┌──────────────────────┐
                             │          │ Semantic answer plan  │
                             │          │ claims + evidence +   │
                             │          │ examples + limits     │
                             │          └───────────┬──────────┘
                             │                      │
                             └────────────┬─────────┘
                                          ▼
                            ┌──────────────────────────┐
                            │ Speech realiser/chunker  │
                            │ Natural spoken form      │
                            │ without deleting content │
                            └────────────┬─────────────┘
                                         ▼
                               TTS/realtime audio
                                         │
                                         ▼
                                  Video avatar

              Shared across both paths:
       canonical conversation state + retrieval +
       attachment/document index + learner model
```

This is not speculative architecture without precedent. OpenAI's realtime prompting guide explicitly describes a Responder–Thinker architecture in which the realtime model handles speaking while a stronger text model handles planning, policies or other substantive work, after which the responder converts that result into speech-friendly language. citeturn13view2 LiveKit similarly supports model specialisation and handoffs, including lightweight triage followed by escalation to a larger model. citeturn16view3

OpenAI's GPT‑Live product architecture goes one step further and uses this separation specifically for deeper reasoning and search while maintaining continuous conversation. citeturn12view9

### Route by task complexity, not merely by modality

Do not route:

> text → strong model  
> voice → small model.

Route instead:

| Intent | Recommended route |
|---|---|
| “Hi”, “repeat that”, simple clarification | Realtime fast path |
| Simple factual answer already in active context | Realtime fast path |
| “Why?” requiring modest reasoning | Realtime with elevated reasoning/verbosity |
| “Explain this concept” | Medium/deep path depending on scope |
| “Explain this paper” | Deep pipeline + document retrieval |
| “Compare these methods and limitations” | Deep pipeline |
| “Derive this equation step by step” | Deep pipeline |
| “Give me the quick version” | Fast path even for complex topic |
| Explicit “deep dive”, “detailed”, “teach me properly” | Deep pipeline unconditionally |

The router itself can be cheap. It can combine lexical signals, conversation state and task metadata. “Explain”, “why”, “walk me through”, “paper”, “methodology”, “derive”, “limitations”, “example”, “deep”, “detailed” and document references should strongly increase the probability of a deep route.

The key is user intent supersedes the default voice brevity preference.

### Keep one canonical context layer for text and voice

AREQA should build a single server-side `LearningContext` or equivalent object consumed by every modality:

```text
current_user_goal
current_course_or_project
current_question
selected_attachment_ids
retrieved_source_chunks
source_page_or_section_metadata
relevant_figures_or_tables
recent_dialogue
long-term_memory
current_learning_state
authoritative_task_instructions
depth_preference
```

Voice should retrieve from this same representation before substantive paper/document responses.

Current OpenAI guidance for long realtime sessions similarly recommends structuring current state, authoritative sources, historical/background material and applicable rules so the model can distinguish what is current and trustworthy. citeturn13view3

Do not make a conversation-summary service the only bridge between the main AREQA application and Live Voice. A summary is useful for continuity, but it is not a substitute for the source.

For example:

```text
BAD VOICE CONTEXT
Attachment: attention_paper.pdf
Summary: Paper about attention models.

BETTER VOICE CONTEXT
Current task:
Explain why multi-head attention helps.

Authoritative source excerpts:
- Section 3.2, p. 4: [retrieved relevant passage]
- Section 3.2.2, p. 5: [relevant multi-head passage]
- Figure 2 caption/data: [relevant extracted content]

Learner context:
Understands dot-product attention but not multiple heads.

Requested depth:
Deep explanation with intuitive example and limitation.
```

Realtime APIs support constructing context specifically for an individual response, so AREQA does not need to stuff every PDF permanently into every realtime turn. citeturn13view4

### Make retrieval parity a product invariant

For every input mode, define:

> Same question + same active attachments = same accessible evidence set.

The generated wording may differ between text and speech, but available evidence should not.

Log the retrieved chunk IDs for both modes. For paired evaluation prompts, calculate context overlap:

\[
\text{Context parity}
=
\frac{|R_\text{voice}\cap R_\text{text}|}
{|R_\text{text}|}
\]

where \(R\) denotes the relevant source chunks returned by the canonical retriever.

A low value immediately identifies a grounding problem before anybody argues about model quality.

### Introduce staged explanation rather than “one massive voice answer”

A strong tutor should not turn a text essay into a ten-minute monologue. The alternative is progressive disclosure.

For a deep request:

Opening: immediately frame the answer.

> “Yes. The paper's main contribution comes from three ideas. I'll first give you the intuition, then the mechanism, and then a concrete example.”

Core conceptual chunk: explain the central idea.

Mechanism chunk: explain how it actually works.

Example chunk: instantiate it concretely.

Evidence/limitations chunk: connect to the paper and discuss what the method does not solve.

Pedagogical close: offer an appropriate next move only after the request is fulfilled.

> “The important distinction is X versus Y. We can now derive the equation or look at the experiment that demonstrates it.”

This achieves two goals that superficially conflict: it supplies depth while creating regular interruption points.

AI-tutoring research supports this general direction. MRBench's learning-science discussion explicitly highlights structured elaboration and examples in manageable chunks as a way to manage cognitive load, while also emphasising adaptation to the learner and active participation. citeturn17view0 MathTutorBench separately finds that raw subject-solving ability does not automatically translate into good tutoring and that longer dialogues create additional pedagogical difficulty. citeturn14view0

So the goal is not “make voice longer”. It is:

> make voice complete enough, appropriately chunked, learner-aware and interruptible.

### Use an immediate conversational layer while the deep answer is generated

For a complex request, AREQA can begin audio quickly without pretending the final answer is already known.

A short preamble might be:

> “Yes — I'll separate the paper's core idea from the experimental evidence, because those are easy to conflate.”

While this plays, the deep pipeline can retrieve source passages and generate the first explanatory chunk.

OpenAI's realtime guidance explicitly treats short preambles before longer reasoning/tool workflows as a first-class behaviour. citeturn13view0 GPT‑Live illustrates the broader architecture: continuous voice interaction is decoupled from deeper work so conversational responsiveness can continue while a frontier model performs the difficult task. citeturn12view9

This is a fundamentally better latency strategy than:

> “We must keep every answer tiny because deeper answers take longer.”

### Produce a semantic answer object before speech adaptation

The deep model should not merely return free-form prose that is then aggressively summarised. It should return a structured internal representation such as:

```json
{
  "answer_goal": "Explain the paper's central mechanism",
  "core_claim": "...",
  "conceptual_explanation": ["...", "..."],
  "mechanism_steps": ["...", "...", "..."],
  "concrete_example": "...",
  "source_evidence": [
    {"source": "paper.pdf", "section": "3.2", "page": 4}
  ],
  "limitations": ["...", "..."],
  "misconceptions_to_avoid": ["..."],
  "optional_next_topics": ["derivation", "experiment"]
}
```

The voice realiser can then make this speakable without being allowed to delete required semantic fields.

That matters because OpenAI's responder–thinker guidance notes that raw text-model responses are not automatically ideal spoken output and recommends a speech-oriented rephrasing layer. citeturn13view2

For AREQA, though, the speech realiser must have a stricter contract than “summarise this briefly”:

> Preserve all required claims, evidence, examples and limitations. Change presentation, not substance.

### Display rich text concurrently with voice

A high-quality educational voice experience does not need to force every detail through the audio channel.

During a deep spoken explanation, the UI can simultaneously display:

- equations;
- source quotations/snippets within appropriate limits;
- paper section/page references;
- diagrams;
- structured bullets;
- key definitions;
- tables;
- follow-up exercises.

That lets speech carry the narrative while vision carries dense symbolic information.

This also makes the avatar layer less constraining: the avatar speaks natural prose, while AREQA's learning surface retains the structured richness associated with text mode.

## Prompt design recommendations

### Remove blanket brevity as the highest-priority change

A rule like:

> “Keep most responses to one to three short sentences.”

is reasonable as a default for simple turns but dangerous as a universal rule.

Replace it with task-conditioned verbosity. That follows current OpenAI realtime guidance, which specifically recommends defining appropriate length per task rather than applying a global “be concise” constraint. citeturn13view1

A starting AREQA prompt policy could be:

```text
# Spoken Response Depth

Choose response depth from the user's intent.

BRIEF
Use for greetings, confirmations, simple factual answers,
or when the user explicitly asks for a short answer.
Usually 1–3 short sentences.

EXPLAIN
Use when the user asks why/how, asks to understand a concept,
or is clearly learning something.
Give enough detail to explain the mechanism, not merely the conclusion.
Use several short spoken chunks with clear verbal signposts.
Include a concrete example whenever it would materially improve understanding.

DEEP
Use when the user asks for a deep/detailed explanation, a paper walkthrough,
methodology, derivation, comparison, critique, limitations, or multiple examples.
Do not apply the default sentence limit.
Substantively fulfil the full request.
Structure the explanation into interruptible spoken chunks.

The user may interrupt at any time.
Interruptibility is not a reason to omit requested substance.
```

### Stop forcing a question at the end of every turn

Replace:

```text
Always end with an open-ended question.
```

with:

```text
Do not ask a follow-up question until the user's current informational
request has been substantively answered.

Use a follow-up question when it improves learning, resolves genuine
ambiguity, checks understanding, or lets the learner choose between
meaningfully different next directions.

A follow-up question is optional, not mandatory.
```

This is particularly important for AREQA because a forced question can become an implicit stop signal. The model learns:

> answer briefly → hand conversational responsibility back to user.

For an educational explanation, the desired policy is:

> fulfil → then scaffold.

MRBench's tutoring taxonomy distinguishes guidance, actionability and coherence and specifically treats good guidance as potentially including explanation, elaboration, hints and examples; pedagogical interaction is therefore richer than merely maintaining conversational turn exchange. citeturn17view0

### Add an explicit “fulfil before scaffold” rule

A tutor often should *not* simply dump the final solution. But “Socratic tutoring” should not become a rationale for withholding the explanation the learner explicitly requested.

Recommended rule:

```text
# Fulfil Before Scaffold

First determine what the learner explicitly asked you to provide.

If they request an explanation, explanation is the task.
If they request an example, provide the example in this turn.
If they request methodology and limitations, cover both.
If they request a derivation, begin or provide the derivation.

Do not replace an explicit request for information with a generic
question such as "What would you like to know more about?"

After satisfying the requested content, use questions or exercises
when they improve learning.
```

The distinction matters because tutoring research finds that being a strong QA model and being a strong tutor are not identical capabilities. MathTutorBench reports a trade-off between raw subject expertise and pedagogical quality and increasing difficulty across longer tutoring interactions. citeturn14view0

### Make grounding behaviour explicit

Recommended prompt:

```text
# Source Grounding

For questions about an uploaded paper, document, slide, image or task:

- Treat retrieved source passages as authoritative for claims about that source.
- Use the available section/page/figure metadata when explaining where an idea appears.
- Distinguish what the source actually states from your interpretation.
- If the available context is only a summary and the user's question requires
  source-level detail, retrieve more context before answering.
- Never pretend to have read document content that is not present in context.
- Prefer source-specific explanation over generic background knowledge.
```

OpenAI's long-context realtime guidance similarly recommends distinguishing authoritative/current information from historical or background context instead of relying on an unstructured transcript. citeturn13view3

### Make examples automatic where pedagogically useful

Your observation that voice improves when explicitly asked for an example suggests examples may not be part of the default teaching policy.

Add:

```text
When a concept is abstract, causal, mathematical, procedural,
or easy to misunderstand, include one concrete example without
waiting for the learner to ask for it.

For deep mode, where appropriate:
1. give the intuition,
2. explain the mechanism,
3. give a concrete example,
4. connect the example back to the theory.
```

MRBench explicitly includes explanations, elaboration and examples within the notion of useful pedagogical guidance, while its learning-science grounding discusses structured elaboration and examples in manageable chunks. citeturn17view0

### Dynamically allocate reasoning effort

If AREQA adopts a current reasoning-capable realtime model, its configuration can also follow intent:

```text
simple conversational turn → minimal/low
ordinary explanation       → low/medium
multi-step technical task   → medium
deep/high-stakes reasoning  → deep text pipeline
```

Current OpenAI realtime guidance states that Realtime-2 can trade latency for deeper reasoning and recommends tuning reasoning effort to task complexity rather than always running the same setting. citeturn13view0turn13view5

### Preserve speech naturalness separately from depth

A deep answer need not sound like an essay.

LiveKit correctly notes that written-style output can sound unnatural when read aloud and therefore recommends voice-specific formatting and speech-realism instructions. citeturn16view4

The solution is a presentation policy such as:

```text
Speak in natural sentences.
Use verbal signposts instead of markdown:
"The first reason is..."
"Now here's the important part..."
"A concrete example makes this clearer..."
"The limitation is..."

Avoid reading URLs, markdown syntax, raw tables or long citation strings aloud.

Do not remove substantive content solely to make it conversational.
Transform dense written structure into spoken structure.
```

This separation — content planning versus speech realisation — is one of the most important changes AREQA can make.

## Evaluation metrics and test scenarios

The redesign should be judged using paired, controlled experiments, not impressions such as “voice feels better now”.

### First isolate the causes factorially

Before making a large architecture change, run controlled comparisons.

| Experiment | Hold constant | Change | What it diagnoses |
|---|---|---|---|
| Prompt A/B | Model, context, token budget | Existing terse prompt vs task-conditioned verbosity | Prompt-policy effect |
| Context A/B | Model, prompt, budget | Current bridge vs canonical retrieved document context | Grounding effect |
| Model A/B | Prompt, context, budget | Current realtime model vs stronger realtime/current reasoning model | Model ceiling |
| Pipeline A/B | Context and task | Realtime-only vs main text thinker + voice realiser | Architecture ceiling |
| Budget A/B | Model, prompt, context | Current cap vs generous cap | Hard truncation |
| Renderer A/B | Semantic answer | Voice-only vs video avatar | Avatar-induced latency or truncation |
| Modality parity | Prompt intent + sources | Text vs voice | End-to-end gap |

The most revealing experiment is probably:

> Same model + same complete source context + same user question; change only the voice prompt.

If the gap collapses, prompt policy is the main culprit.

Then:

> Same relaxed prompt; change only context bridge.

If source faithfulness and specificity jump, grounding is the next culprit.

Only after those tests should AREQA attribute the residual gap primarily to model choice.

### Build a paired text-versus-voice educational benchmark

Create a stable evaluation set representing actual AREQA use.

A sensible initial suite would contain several hundred turns across categories rather than only ten showcase examples. The important point is coverage and repeatability, not a magical sample count.

Include at least these scenarios:

| Scenario | Example |
|---|---|
| Simple factual | “What is gradient descent?” |
| Explicit short | “Give me the 20-second explanation.” |
| Ordinary conceptual | “Why does regularisation reduce overfitting?” |
| Explicit deep | “Teach me backpropagation properly and give an example.” |
| Paper overview | “Explain the main contribution of this paper.” |
| Paper methodology | “Walk me through the methodology and why the authors chose it.” |
| Source-specific limitation | “What limitations do the authors acknowledge?” |
| Equation/derivation | “Derive this equation step by step.” |
| Comparison | “Compare method A with method B and explain the trade-offs.” |
| Concrete example | “Show me a concrete example with numbers.” |
| Multiple attachments | “How does paper A disagree with paper B?” |
| Memory + paper | “Connect this to what we discussed yesterday.” |
| Long session | Ask after extended tutoring history |
| Interruption | Interrupt midway and ask a side question |
| Resume | “Continue from where I interrupted you.” |
| Depth escalation | “Go deeper.” |
| Depth reduction | “Okay, now just give me the takeaway.” |
| Avatar parity | Repeat identical test in audio-only and avatar mode |

LiveKit supports both turn-level tests and end-to-end simulated conversations; its documentation recommends text-based deterministic testing during iteration and audio simulation for behaviours specific to turn-taking and the speech pipeline. It explicitly calls out grounding, expected behaviour, tool use and multi-turn conversation flow as relevant test targets. citeturn12view6

### Score answer quality on separate dimensions

Do not use response length as a proxy for quality. A 500-word bad answer is still bad.

For each response, score:

| Metric | What it asks |
|---|---|
| Correctness | Are the claims factually correct? |
| Source faithfulness | Are claims about the paper actually supported by supplied context? |
| Coverage | Did it answer every explicit part of the user's request? |
| Conceptual depth | Does it explain *why/how*, not merely state conclusions? |
| Methodological specificity | Does it describe the actual mechanism/procedure? |
| Example quality | Is there an appropriate concrete example when needed? |
| Limitations/trade-offs | Does it discuss meaningful caveats when requested? |
| Coherence | Does it follow the learner's previous context correctly? |
| Actionability | Does the learner know what to do or think about next? |
| Pedagogical adaptation | Is explanation calibrated to the learner's current understanding? |
| Speech naturalness | Does it sound like good spoken teaching rather than written prose read aloud? |
| Fulfilment-before-follow-up | Did it answer before asking the learner another question? |

This is aligned with contemporary tutor-evaluation research rather than generic chatbot metrics. MRBench defines eight pedagogical dimensions and explicitly distinguishes tutoring quality from generic question-answering ability. citeturn14view1turn17view0 MathTutorBench similarly argues for holistic evaluation of tutor ability rather than assuming subject-solving performance implies teaching quality. citeturn14view0

### Introduce a voice-to-text quality parity score

For paired questions, use the text answer as an internal quality reference:

\[
\text{Voice Quality Parity}
=
\frac{\text{Voice rubric score}}
{\text{Text rubric score}}
\]

The current subjective description is roughly:

\[
60 / 120 = 50\%
\]

That is clearly not an acceptable educational-modality gap.

A useful product target would be to drive deep-mode voice to at least roughly 85–90% of text-mode semantic quality, while allowing the presentation to differ. This should be treated as an AREQA product objective rather than an industry-standard threshold.

Crucially, do not require:

\[
\text{voice words} \approx \text{text words}.
\]

Require instead:

\[
\text{voice semantic coverage} \approx \text{text semantic coverage}.
\]

The spoken version can compress formatting and redundancy without losing the core theory, mechanism, evidence, example and limitations.

### Measure “premature hand-back rate”

This may expose the present problem particularly clearly.

Define:

\[
\text{Premature Hand-back Rate}
=
\frac{\text{answers that ask a follow-up before fulfilling the request}}
{\text{complex explanation requests}}
\]

Examples of failures:

> “There are several reasons transformers work well. Would you like me to explain them?”

when the user already asked:

> “Explain why transformers work well.”

Or:

> “The authors use contrastive learning. Should I give you an example?”

when the user explicitly asked:

> “Explain the method and give me an example.”

For deep educational requests, this rate should approach zero.

### Measure “detail recovery” as a diagnostic metric

Your existing observation can become a formal metric.

Run:

Turn A

> “Explain this paper.”

then:

Turn B

> “Please give me much more detail and concrete examples.”

Score both.

Define:

\[
\text{Detail Recovery Gap}
=
Q_{\text{after explicit escalation}}
-
Q_{\text{initial}}
\]

A very large positive gap indicates the system already possessed capability but was suppressing it in the initial response.

After a successful prompt redesign, that gap should shrink because the first answer should correctly infer that “explain this paper” requires meaningful explanatory depth.

### Measure grounding directly

For every document-grounded test, record:

- retrieved chunk IDs;
- sections/pages supplied;
- claims made;
- claims supported by retrieved evidence;
- unsupported source-specific claims.

Useful metrics include:

\[
\text{Grounded Claim Precision}
=
\frac{\text{supported source-specific claims}}
{\text{all source-specific claims}}
\]

and the previously discussed context-parity score between voice and text.

OpenAI's Realtime API supports response-specific custom context, so this measurement can be tied directly to what evidence was actually placed in each realtime request. citeturn13view4

### Measure latency without confusing it with answer duration

AREQA should report at least:

- end-of-turn detection delay;
- time to first model output;
- TTS time to first audio where applicable;
- end-to-end response-start latency;
- avatar playback latency;
- total answer duration;
- interruption response time;
- resume success.

LiveKit already exposes relevant per-turn telemetry including `transcription_delay`, `end_of_turn_delay`, `llm_node_ttft`, `tts_node_ttfb`, `playback_latency` and `e2e_latency`; it notes that some model/TTS-specific metrics apply only to cascaded pipelines, while avatar workers can affect playback latency. citeturn12view5

This enables a much better engineering objective:

> Keep time-to-first-audio close to the current voice baseline while increasing complete-answer quality.

That is more useful than minimising total spoken duration.

### Explicitly test interruption and resumption

For deep voice, randomly interrupt at points such as:

> “Wait, why is that assumption valid?”

The system should:

1. stop speaking cleanly;
2. answer the interruption;
3. preserve its previous explanation state;
4. optionally resume from the appropriate conceptual checkpoint rather than restarting.

The state checkpoint should live outside transient audio playback. Otherwise interruption-related transcript truncation can destroy the deep answer plan.

### Include learner-outcome measures

Ultimately, AREQA is a learning product. Quality should not be measured only by whether experts like the wording.

For selected scenarios, ask a transfer or understanding question after the explanation:

> “Now explain the concept back in your own words.”

or:

> “Apply the method to this slightly different case.”

Measure learner correctness before versus after the interaction.

This is important because tutor benchmarking shows that pedagogical ability and raw question-answering capability are not equivalent. citeturn14view0turn14view1

## Risks and trade-offs

### Longer voice responses can become exhausting

Simply removing the sentence limit and making every answer five minutes long would create a different failure mode. LiveKit's voice guidance is correct that spoken interaction has different patience and formatting constraints from text. citeturn16view4

Mitigation: use staged chunks, clear verbal signposts and user depth controls. “Deep” should mean richer semantic content, not uninterrupted monologue.

### Hybrid routing adds engineering complexity

A responder–thinker design adds:

- another model call;
- task routing;
- shared state;
- retrieval orchestration;
- possible handoff failure;
- synchronisation between thinker output and spoken output.

This complexity is real, but both OpenAI and LiveKit now document model-specialisation/supervisor patterns for voice systems, and OpenAI's consumer GPT‑Live architecture explicitly separates continuous interaction from deeper work. citeturn13view2turn16view3turn12view9

Mitigation: begin with a narrow deep-route trigger rather than rebuilding every voice turn.

### A speech realiser can accidentally destroy answer quality

A strong thinker may produce:

> four causal points + two limitations + example + evidence

and a speech adapter may turn it into:

> “Basically, the method is more efficient.”

That simply moves the current problem one stage downstream.

Mitigation: pass a semantic answer object with required fields and assert coverage after speech conversion. The speech adapter should be evaluated for semantic preservation, not brevity.

### Better context increases token usage and retrieval cost

Giving voice access to full evidence increases input cost and can increase processing time. Current Realtime models also expose an explicit latency/output trade-off with reasoning effort. citeturn13view5

Mitigation: do not inject entire PDFs unnecessarily. Retrieve relevant source spans from the same canonical index used by text mode and preserve source metadata.

### Higher reasoning effort can harm conversational responsiveness

Running every utterance at high reasoning effort would be wasteful and could make even “yes” or “repeat that” feel slow. OpenAI explicitly advises choosing the lowest reasoning level that is sufficient for the task. citeturn13view0

Mitigation: dynamic routing:

> quick conversation → fast model/low effort  
> substantive explanation → elevated effort  
> complex document/reasoning task → deep pipeline.

### Fast and deep models may disagree

In a hybrid design, the realtime responder might begin framing an answer before the deep thinker has established the exact result.

Mitigation: the preamble should commit only to process and structure, not substantive facts.

Good:

> “I'll distinguish the theoretical claim from what the experiment actually demonstrates.”

Bad:

> “Yes, the experiment proves the hypothesis — let me explain why.”

before retrieval has finished.

### Context summaries can silently become authoritative

If AREQA passes old conversation summaries alongside newly retrieved paper content without source priority, the voice model may repeat stale or incorrect information. OpenAI specifically advises structuring long-context realtime inputs so current authoritative material is distinguishable from historical/background context. citeturn13view3

Mitigation: encode source status and recency explicitly.

### Deep explanations can conflict with good tutoring practice

A learner who is solving a problem may benefit more from a hint than a full solution, whereas a learner explicitly asking for a paper explanation may benefit from substantial direct teaching. Tutor evaluation research emphasises active learning and not unnecessarily revealing answers in mistake-remediation settings, while also requiring relevant guidance and explanation. citeturn17view0

Mitigation: distinguish *task intent*:

> “Solve this homework problem for me”  
> versus  
> “Teach me the underlying concept”  
> versus  
> “Explain this paper.”

Do not hard-code one Socratic policy for all three.

### Avatar rendering can disguise the true latency source

Teams may shorten semantic answers because “avatar mode feels slow” when the added delay is actually downstream playback or rendering.

LiveKit makes `playback_latency` measurable and specifically notes the remote-avatar case. citeturn12view5

Mitigation: measure:

> reasoning latency  
> TTS latency  
> transport latency  
> avatar playback latency

separately before shortening intellectual content.

## Recommended implementation priority and final diagnosis

The evidence supports a staged fix rather than immediately replacing the entire voice stack.

Highest priority: remove the global verbosity constraint. Convert “one to three sentences” from an unconditional response rule into a default for simple conversation. Add explicit `BRIEF / EXPLAIN / DEEP` task modes, make “explain”, “deep”, “why”, “methodology”, “paper”, “example”, “derive” and “limitations” activate richer responses, and remove mandatory end-of-turn questions. Current realtime guidance strongly supports task-specific rather than blanket response-length policies. citeturn13view1

At the same time, establish context parity. Voice and text should retrieve from the same attachment/document index and receive the same relevant source evidence. Use response-specific custom realtime context where necessary rather than depending on a short conversation bridge. Realtime APIs support custom context directly, and current models support substantially larger structured contexts than earlier realtime generations. citeturn13view4turn13view3

Then run the factorial evaluation before changing models. This will quantify how much quality is recovered by prompt and context alone. LiveKit's evaluation framework supports turn-level testing and multi-turn simulations, including audio testing for speech-specific issues. citeturn12view6

Next, upgrade or dynamically configure the realtime model where appropriate. Current OpenAI realtime systems support configurable reasoning rather than a single low-intelligence operating point; the latest realtime guidance points developers towards `gpt-realtime-2.1` for low-latency agents and describes reasoning-depth controls in the current realtime generation. citeturn13view6turn13view0

For true text-quality parity on difficult learning tasks, introduce a thinker–responder deep path. Reuse as much of AREQA's existing text answer pipeline as possible — PARTS context, document retrieval, task state, main reasoning model, visual/PDF grounding and larger response budget — rather than rebuilding a second, weaker educational intelligence stack inside the voice agent. The realtime layer should own conversational timing and spoken delivery; the deep pipeline should own difficult cognition and evidence synthesis. This matches the responder–thinker architecture documented for realtime systems and the deeper-work delegation model used by GPT‑Live. citeturn13view2turn12view9

Finally, treat video/avatar as an output modality. Feed it the same semantically strong spoken stream used by voice mode and optimise playback separately. LiveKit's architecture separates avatar capability from model choice and exposes avatar-sensitive playback telemetry. citeturn16view5turn12view5

The most likely causal picture is therefore:

\[
\boxed{
\text{Voice quality gap}
\approx
\text{over-aggressive brevity policy}
+
\text{weaker grounding}
+
\text{weaker/default-fast cognition}
+
\text{tight latency/output policy}
}
\]

rather than:

\[
\boxed{
\text{Voice quality gap}
=
\text{“voice models are bad”}
}
\]

The key product insight is that low latency and deep reasoning no longer need to be performed by the same component on the same timescale. Modern voice architectures increasingly separate the *interaction loop* from the *thinking loop*. OpenAI's current realtime ecosystem supports structured context, variable reasoning depth and responder–thinker designs, while GPT‑Live demonstrates an even stronger form of this separation by delegating complex work while maintaining continuous conversation. citeturn13view0turn13view2turn12view9

For AREQA specifically, the desirable end state is therefore not “make Live Voice talk much more”. It is:

> Make Live Voice understand when the learner has requested depth; give it the same authoritative learning context as text mode; route difficult cognition to the strongest appropriate pipeline; then express that content in short, interruptible spoken chunks rather than prematurely ending the explanation.

That architecture should preserve the central advantages of realtime interaction — fast first response, natural speech, interruptions and avatar presence — while eliminating the artificial “60/100 versus 120/100” intellectual-quality ceiling.