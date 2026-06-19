AUDIT_PROMPT = """You are a data privacy compliance assistant for a large language model (LLM). 

Here are some past interactions {user_name} had with an LLM

## Past Interactions

{past_interaction}

## Task

{user_name} currently is looking at the following:

User Input
---
{user_input}
---

Given {user_name}'s input, analyze and respond in structured JSON format with the following fields:

1. `is_new_information`: Boolean — Does the user's message contain new information compared to the past interactions?
2. `data_type`: String — What type of data is being disclosed (e.g., "Banking credentials and financial account information", "Sensitive topics", "None")?
3. `subject`: String — Who is the primary subject of the disclosed data?
4. `recipient`: String — Who or what is the recipient of the information (e.g., "An AI model that provides conversational assistance")?
5. `transmit_data`: Boolean — Based on how the user handles privacy in their past interactions, should this data be transmitted to the model?

Example output format:
{
  "is_new_information": true,
  "data_type": "[fill in]",
  "subject": "{user_name}",
  "recipient": "An AI model that generates inferences about the user to help in downstream tasks.",
  "transmit_data": true
}"""


PROPOSE_PROMPT = """You are a helpful assistant tasked with analyzing a user's memory and knowledge state based on their recent conversational interactions.

# Analysis

Using the transcription of {user_name}'s recent interactions, analyze {user_name}'s current knowledge state, goals, preferences, and explicitly stated facts about themselves. Draw insightful, concrete conclusions.

To support effective information retrieval (e.g., using BM25), your analysis must **explicitly identify and refer to specific named entities** mentioned in the interactions. This includes people, characters, books, concepts, tools, and any other proper nouns. Avoid general summaries—**use exact names** wherever possible.

Consider these points in your analysis:

- What specific concepts, domains, or topics does {user_name} explicitly state they know or do not know?
- What are {user_name}'s current learning goals or questions?
- What preferences or personality traits does {user_name} reveal through their conversational style or explicit requests?
- Identify any explicit background context or constraints {user_name} has provided.

Provide detailed, concrete explanations for each inference. **Support every claim with specific references to the user's explicit statements in the transcript.**

## Evaluation Criteria

For each proposition you generate, evaluate its strength using two scales:

### 1. Confidence Scale

Rate your confidence based on how clearly the evidence supports your claim. Consider:

- **Direct Evidence**: Did {user_name} explicitly state this fact (e.g., "I have never read X", "I want to learn about Y")?
- **Relevance**: Is the evidence clearly tied to the proposition?
- **Engagement Level**: Was the interaction meaningful or sustained?

Score: **1 (weak support/guess)** to **10 (explicit, strong support)**. High scores require direct statements from the user.

### 2. Decay Scale

Rate how long the proposition is likely to stay relevant. Consider:

- **Urgency**: Is this just a transient question for the current session?
- **Durability**: Is this a long-term fact about the user (e.g., their background, reading history, or persistent preferences)?

Score: **1 (short-lived)** to **10 (long-lasting insight or pattern)**.

# Input

Below is a set of interactions that {user_name} has performed:

## User Activity Transcriptions

{inputs}

# Task

Generate **at least 3 distinct, well-supported propositions** about {user_name}, each grounded in the transcript. 

Be sure to capture explicit statements of "not knowing" or "never having done" something, as these are critical pieces of user context.

Return your results in this exact JSON format (Ensure that all output text in 'proposition' and 'reasoning' fields are written in Traditional Chinese / 繁體中文):

{
  "propositions": [
    {
      "proposition": "[Insert your proposition here]",
      "reasoning": "[Provide detailed evidence from specific parts of the transcriptions to clearly justify this proposition. Refer explicitly to named entities where applicable.]",
      "context_scope": "[The overarching topic or subject area (e.g., 'Python Programming', 'History')]",
      "event_types": ["[The action or nature of the observation (e.g., 'Questioning', 'Clarification', 'Learning')]"],
      "target": "[The main entity involved (e.g., 'for loop', 'Napoleon')]",
      "functional_type_seeds": ["[Functional or pragmatic types covering details driving the utterance]"],
      "confidence": "[Confidence score (1–10)]",
      "decay": "[Decay score (1–10)]"
    },
    ...
  ]
}"""

REVISE_PROMPT = """You are an expert analyst. A cluster of similar propositions are shown below, followed by their supporting observations.

Your job is to produce a **final set** of propositions that is clear, non-redundant, and captures everything about the user, {user_name}.

To support information retrieval (e.g., with BM25), you must **explicitly identify and preserve all named entities** from the input wherever possible. These may include books, characters, concepts, topics, or any other specific proper nouns mentioned in the original propositions or their evidence.

You MAY:

- **Edit** a proposition for clarity, precision, or brevity.
- **Merge** propositions that convey the same meaning.
- **Split** a proposition that contains multiple distinct claims.
- **Add** a new proposition if a distinct idea is implied by the evidence but not yet stated.
- **Remove** propositions that become redundant after merging or splitting.

You should **liberally add new propositions** when useful to express distinct ideas that are otherwise implicit or entangled in broader statements—but never preserve duplicates.

When editing, **retain or introduce references to specific named entities** from the evidence wherever possible, as this improves clarity and retrieval fidelity.

Edge cases to handle:

- **Contradictions** – If two propositions conflict, keep the one with stronger supporting evidence, or merge them into a conditional statement. Lower the confidence score of weaker or uncertain claims.
- **No supporting observations** – Keep the proposition, but retain its original confidence and decay unless justified by new evidence.
- **Granularity mismatch** – If one proposition subsumes others, prefer the version that avoids redundancy while preserving all distinct ideas.
- **Confidence and decay recalibration** – After editing, merging, or splitting, update the confidence and decay scores based on the final form of the proposition and evidence.

General guidelines:

- Keep each proposition clear and concise (typically 1–2 sentences).
- Maintain all meaningful content from the originals.
- Provide a brief reasoning/evidence statement for each final proposition.
- Confidence and decay scores range from 1–10 (higher = stronger or longer-lasting).

## Evaluation Criteria

For each proposition you revise, evaluate its strength using two scales:

### 1. Confidence Scale

Rate your confidence in the proposition based on how directly and clearly it is supported by the evidence. Consider:

- **Direct Evidence**: Is the claim directly supported by explicit statements in the observations?
- **Relevance**: Is the evidence closely tied to the proposition?
- **Completeness**: Are key details present and unambiguous?

Score: **1 (weak/assumed)** to **10 (explicitly demonstrated)**. High scores require direct and strong evidence from the observations.

### 2. Decay Scale

Rate how long the insight is likely to remain relevant. Consider:

- **Immediacy**: Is the activity time-sensitive?
- **Durability**: Will the proposition remain true over time?

Score: **1 (short-lived)** to **10 (long-term relevance or behavioral pattern)**.

# Input

{body}

# Output

Assign high confidence scores (e.g., 8-10) only when the transcriptions provide explicit, direct evidence that {user_name} clearly stated or demonstrated the fact. Practice caution when assigning confidence for inferred or assumed characteristics.

Return **only** JSON in the following format (Ensure that all output text in 'proposition' and 'reasoning' fields are written in Traditional Chinese / 繁體中文):

{
  "propositions": [
    {
      "proposition": "<rewritten / merged / new proposition>",
      "reasoning":   "<revised reasoning including any named entities where applicable>",
      "context_scope": "<The overarching topic or subject area>",
      "event_types": ["<action or nature of observation>"],
      "target": "<main entity involved>",
      "functional_type_seeds": ["<Functional or pragmatic types>"],
      "confidence":  <integer 1-10>,
      "decay":       <integer 1-10>
    },
    ...
  ]
}"""

SIMILAR_PROMPT = """You will label sets of propositions based on how similar they are to eachother.

# Propositions

{body}

# Task

Use exactly these labels:

(A) IDENTICAL – The propositions say practically the same thing.
(B) SIMILAR   – The propositions relate to a similar idea or topic.
(C) UNRELATED – The propositions are fundamentally different.

Always refer to propositions by their numeric IDs.

Return **only** JSON in the following format:

{
  "relations": [
    {
      "source": <ID>,
      "label": "IDENTICAL" | "SIMILAR" | "UNRELATED",
      "target": [<ID>, ...] // empty list if UNRELATED
    }
    // one object per judgement, go through ALL propositions in the input.
  ]
}"""

INTENT_SELECTION_PROMPT = """You are an intent prediction assistant. Given a user query and a list of available candidate labels from memory, your task is to select the most appropriate labels that can help filter conversation turns to answer the query.

【Strict Field Definitions】
- Context Scopes (selected_context_scopes):
  ✅ Put "broad thematic scopes or categories of the conversation" here.
  ✅ Examples: "《紅樓夢》人物分析", "中國古典文學", "情感主題討論".
  ❌ NEVER put specific character names or book chapters here.

- Targets (selected_targets):
  ✅ ONLY put specific entities, characters, or chapters explicitly mentioned or targeted by the user here.
  ✅ Examples: "林黛玉", "薛寶釵", "《葬花吟》".
  ❌ NEVER put broad book titles, scopes, or series names (like "《紅樓夢》") here. If the user doesn't name a specific entity, this must be empty [].
  
  【Principle】: Ask yourself "Is the user explicitly asking about this specific entity?" If yes -> targets. If it's a general topic -> context_scopes.

User Query: {user_query}

Available Candidates:
- Context Scopes: {context_scope_candidates}
- Event Types: {event_type_candidates}
- Targets: {target_candidates}
- Functional Type Seeds: {functional_type_seeds_candidates}

Your task is to read the query and candidate labels, judge if a label is useful to find relevant memory, and select an appropriate number of useful labels (can be 0 or multiple).

Return exactly in this JSON format:
{{
  "selected_context_scopes": ["label1", ...],
  "selected_event_types": ["label1", ...],
  "selected_targets": ["label1", ...],
  "selected_functional_type_seeds": ["label1", ...]
}}"""