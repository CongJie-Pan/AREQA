# Executive Summary  
We surveyed recent research on LLM-augmented educational agents focusing on **persistent user models**, **adaptive scaffolding/fading**, and **proactive support**. We identified 4–5 key works (2023–2026) that combine RAG or knowledge-tracing with LLMs in education and address ≥2 of {memory, scaffolding, proactivity}. These include *LOOM* (2025) and *TutorLLM* (2024), among others. We compare each to our AREQA vision (longitudinal user model + proficiency tracking + scaffold fading + proactivity). No existing system fully implements our proposed combination. We also distilled concrete **design patterns** for memory management (e.g. hierarchical agentic memory, semantic “note” graphs, short-term buffers→ long-term blocks) and for proactive UX (e.g. context-aware suggestion pipelines, summary-with-preview UIs, user-profile-driven agents). Finally, we suggest three immediate MVP features: (1) a **persistent conversation memory** that summarizes and stores key interactions for retrieval, (2) an **adaptive hinting module** that tracks mastery and gradually fades support, and (3) a **proactive suggestion interface** that uses the user model to propose next steps (see Conclusion). All claims are evidence-backed by recent high-impact sources.  

## 1. Similar Recent Systems (2023–2026)  
Below we list 5 representative works that integrate LLMs (often with RAG or knowledge-tracing) in educational settings and address two or more of {memory, scaffolding, proactivity}.  

- **LOOM: Dynamic Learner Memory Graph (2025)** – *Anonymous et al.* Introduces *LOOM*, a chat-based learning assistant that *observes everyday LLM conversations* to build a **dynamic learner memory graph** tracking each student’s mastery over concepts. The system segments user chats, summarizes emerging themes and gaps, and maintains a graph of concepts with inferred mastery. When appropriate, LOOM proactively **generates mini-course outlines** and content tailored to the learner’s needs (i.e. merging continuity with initiative). Architecturally, LOOM uses an LLM to summarize dialogue segments, a graph database to represent concept links, and RAG to retrieve educational content. In a formative 2-day study with 10 participants, LOOM produced lessons aligned with recent queries and helped learners identify “unknown unknowns”. Metrics reported include qualitative user ratings of relevance/coherence (via surveys) and demonstration of improved gap-awareness (no quantitative scores given). [**Addresses:** Memory (long-term graph), Scaffolding (lesson planning), Proactivity (unsolicited course suggestions)].

- **Yan et al. (2024) – Generative AI + Scaffolding in Visual Analytics** – *Yan, Martinez-Maldonado et al.* evaluate the pedagogical impact of AI agents on *visual learning analytics* comprehension. They compare three conditions: (a) **Standalone Scaffolding** (static prompts), (b) **Passive AI Agent** (LLM that answers queries), and (c) **Proactive AI Agent** (an LLM that *actively asks scaffolding questions* during the task). In a randomized trial with 117 university students, they found that **proactive agents significantly outperformed both** passive agents and static scaffolds on VLA comprehension, even at post-test. Architecturally, the system is a chat interface: the proactive agent monitors the student’s progress and injects guiding questions without prompting. Evaluation metrics include task performance (comprehension scores during and after) and survey feedback. [**Addresses:** Scaffolding (explicit prompts), Proactivity (unprompted questions); *not* persistent memory].

- **Cohn et al. (2025) – *LC-RAG* for Collaborative STEM Tutoring** – *Cohn et al.* present *Log-Contextualized RAG (LC-RAG)* to bridge the gap between student dialogue and domain knowledge in a collaborative modeling environment (C2STEM). The agent segments each pair’s **student actions and talk** into “problem-solving segments” and uses GPT-3.5 to generate a context-aware summary of each segment. These summaries (combining discourse + environment logs) seed a RAG retrieval over physics/computing textbook content, grounding responses in the task context. The team built *Copa*, an LLM-powered peer agent (with GPT-4o) using this method. They deployed it in an 8-week field study with 24 high-school students (9 hours of data, 2,275 actions, 2,786 utterances). Evaluation was two-fold: (1) an automated LLM-as-judge comparison (with GPT-4o) of LC-RAG vs baseline on relevance, accuracy, helpfulness, and (2) student perceptions via surveys/focus groups. Results showed LC-RAG improved retrieval quality and that students found *Copa* epistemically valuable. [**Addresses:** Scaffolding (contextual hints), Semi-memory (logs summary for context), *Not* proactive beyond answering queries].

- **Cohn et al. (2025) – *Inquizzitor* (Adaptive LLM Tutoring)** – *Cohn et al.* also propose *Inquizzitor*, an LLM-based formative assessment agent grounded in **Evidence-Centered Design and Social Cognitive Theory**. Applied to a middle-school Earth Science curriculum, Inquizzitor quizzes students with open-ended questions and uses an LLM (via careful prompt templates) to *score answers and give feedback*. A key mechanism is multi-turn dialogue: the agent can ask clarification questions, offer hints, etc., shaped by the student’s estimated Zone of Proximal Development. In a controlled evaluation on real student data (104 students’ responses across 3 assessments), Inquizzitor’s **scoring accuracy** matched or exceeded human inter-rater agreement (weighted κ ≈ 0.87–0.94). It also incorporated scaffolding principles (fading hints as mastery grew) though details are high-level. Key metrics: weighted kappa for scoring, plus qualitative surveys. [**Addresses:** Scaffolding (adaptive feedback), *Not* long-term memory, *Not* proactive beyond reactive tutoring].

- **Li et al. (2024) – *TutorLLM* (KT + RAG Recommender)** – *Li et al.* introduce *TutorLLM*, a personalized learning recommender that fuses **Knowledge Tracing (KT)** with RAG. The system uses a BERT-based KT model (MLFBK) to maintain each student’s latent learning state, and a “Scraper” component that grabs context-relevant text during online study sessions. Inputs from KT and Scraper feed a GPT-4-based RAG agent that answers queries and **recommends next study materials**. As architecture, students use a browser plugin to interact and the system tracks their course performance. In a 2-week crossover field study (30 undergraduates in a linear algebra course), TutorLLM produced a **10% lift in user satisfaction (SUS)** and **5% higher quiz scores** versus a baseline LLM tutor. [**Addresses:** Scaffolding (personalized recommendations), *Limited* memory (KT model as short-term state), *Proactivity* (pushes tailored study tips)].

**Table: Similar Systems (2023–2026)**

| System (Citation)                                         | Domain       | LLM+Technique                   | Memory                   | Scaffolding                      | Proactivity                | Data/ Eval Metrics                                 |
|-----------------------------------------------------------|--------------|---------------------------------|--------------------------|-----------------------------------|----------------------------|----------------------------------------------------|
| LOOM (2025)                                          | General      | LLM + Dynamic Memory Graph      | *Yes* (longitudinal graph) | Yes (adaptive lesson planning)   | Yes (auto-initiated lessons) | 10 users, qualitative: task relevance, gap-awareness |
| Yan et al. (2024)                                    | Visual Analytics| Conversational Agent + Scaffolding | *No* (one-off)           | Yes (scaffold questions)         | Yes (agent asks questions)  | 117 students, comprehension scores pre/post        |
| Cohn et al. (2025) – LC-RAG                           | STEM Tutor    | LLM + RAG (dialogue+log)        | *Partial* (session context) | Yes (contextual hints)           | No (reactive)             | 24 students, LLM-judge relevance/accuracy (win %)  |
| Cohn et al. (2025) – Inquizzitor                      | Science Tutor | LLM (hybrid) + ECD/SCT          | *No*                     | Yes (adaptive feedback)          | No                        | 104 students, weighted κ for scoring (≈0.9)       |
| Li et al. (2024) – TutorLLM                          | Math Tutor    | LLM + RAG + Knowledge Tracing   | *Limited* (short-term)   | Yes (personalized recs)          | Partial (recommendations) | 30 students, +10% SUS, +5% quiz scores             |

## 2. Gap Analysis (AREQA vs Existing Work)  
Each of the above systems provides elements of our vision, but **none covers all**.  

- **LOOM** builds a persistent learner model from chat history and even plans micro-lessons, but it is *preliminary* and not fully evaluated for long-term learning gains. It **tracks some user state** (mastery graph) and issues guided content (scaffolding) *proactively* (without user prompt). However, LOOM’s study was very small-scale (10 users over 2 days) and focused on content planning – it did not implement adaptive scaffold *fading* or fine-grained proficiency updates. Our AREQA goes further by continuously updating a unified user model (across any dialogue) and adjusting scaffold support as mastery changes.  

- **Yan et al. (2024)** demonstrate that *proactive* AI agents (with built-in scaffolding) outperform passive bots. This confirms the value of mixed-initiative in education. However, their work is limited to a single VLA task and does *not* include a longitudinal user model or memory – each session is independent. They also use hard-coded scaffolding prompts rather than dynamic, personalized scaffolding. In contrast, AREQA envisions an agent that **remembers a student’s evolving knowledge** across sessions and gradually *fades* hints (unlike one-shot scaffolds) based on mastery.  

- **LC-RAG (2025)** improves retrieval by summarizing the *current* collaborative context (adding a lightweight memory of the environment). This yields more relevant hints *within* a session. But LC-RAG does not accumulate a *persistent* model of the user across sessions, nor does it track proficiency or proactively offer future tasks. AREQA incorporates LC-RAG’s insight (contextual summarization) but extends it with *true long-term memory* and automated scaffold management.  

- **Inquizzitor (2025)** is strong on theory-driven scaffolding (ECD/SCT) and shows LLMs can provide high-quality feedback on student answers. However, it’s essentially a *single-lesson* tutoring agent: each assessment is standalone. It does not maintain a user profile or adjust scaffolds beyond the immediate task. AREQA will generalize this idea by using assessment results to update a longitudinal mastery model and trigger future scaffolds/activities adaptively.  

- **TutorLLM (2024)** uniquely combines KT with RAG, yielding a simple recommendation system that *implicitly* models learning state. It shows RAG can boost LLM accuracy in an ed-tech plugin. But TutorLLM’s user model is limited (score traces), and its recommendations are issued on a fixed schedule (post-class). It does not integrate into a dialog agent or provide on-the-fly hints. In AREQA, we would integrate such personalization *during* interaction (e.g. next-question suggestions mid-dialog) and tie it to a richer general user model (GUM).  

**Novelty of AREQA:** No existing system combines **a continuous, multimodal learner model with real-time adaptive scaffolding and proactive guidance**. Prior work has some pieces (e.g. long-term graphs, RAG retrieval, scheduling hints), but AREQA’s full pipeline – *observe → update GUM & proficiency → decide scaffold (or UI adaptation) → follow up* – is novel. The main risks are complexity of maintaining an accurate GUM and ensuring helpful (not intrusive) proactivity. We plan to evaluate via mixed-methods: automated metrics (e.g. retention of knowledge over weeks, scaffold usage logs) plus user studies on learning gains and experience. Publication should be strong: combining LLMs with rigorous learning science in a longitudinal field study is high-impact territory (ML conference HCI overlap like CHI or AIED).

## 3. Memory Management Design Patterns (HCI/AI)  
We identify **three concrete architectures** for handling memory (short-term vs long-term) in AI agents, drawn from literature and industry:

- **Hierarchical Memory (RAM vs Disk):** Inspired by OS design, systems like Mem0 introduce a *two-tiered memory*. The LLM’s *working memory* (context window) holds current instructions, recent conversation, and *working buffers*. An *external memory* (infinite store) keeps all prior conversation and background data. The agent can “page” information between them via function calls: when context exceeds limits, it retrieves relevant bits from external memory. This ensures the LLM only attends to salient context (RAM) while preserving long-term knowledge (Disk). In practice, this looks like: short-term chat buffers are held locally, and a document store (e.g. vector DB) holds older summaries. At inference time, the agent queries the store for relevant chunks. 

- **Agentic Memory Graph (Interconnected Notes):** Building on Mem0, the *A-Mem* model treats memory as an evolving graph of “notes”. Each note contains an event or fact (with keywords, metadata) captured by the agent. When adding new memory, A-Mem semantically retrieves similar notes and uses an LLM to form explicit links (e.g. note topics, causal ties). Crucially, **notes are dynamically updated**: if a new event relates to old ones, their content/attributes are refined. Retrieval then uses semantic similarity over this graph. Thus memory isn’t static: it **continually consolidates** and deepens context. (In effect, it blurs episodic traces into a semantic web.) Such graph-based linking prevents context pollution by providing only tightly relevant memories when needed, rather than dumping all text.  

   *Figure:* This example (Mem0 Fig.1) contrasts “No Memory” vs “With Memory” in conversation. Without memory, the assistant forgets user preferences (“vegetarian, no dairy”) and gives a bad suggestion. With hierarchical memory, it retains that info and suggests a suitable meal.

- **Short-Term Buffer + Long-Term Blocks:** In practice, many frameworks use a *hybrid scheme*. For instance, LlamaIndex’s memory component stores up to a token limit in a chat history buffer, then **flushes** overflow into structured long-term memory blocks. These blocks can be (a) *static info* (e.g. user profile), (b) *fact lists* (extracted by an LLM during conversation), and (c) *vector store* of past chats. This pattern works as follows: during a session, messages go into short-term memory. If the buffer is full, the oldest messages are pushed into the appropriate long-term blocks (the “vector block” ingests them as embeddings, the “fact block” extracts key facts, etc.). On new queries, the agent can then retrieve from these blocks. This design neatly separates **working memory** from **semantic/episodic memory**: the former is the active chat stream, while the latter is curated knowledge. It also naturally supports **memory consolidation**: only salient items (facts, embeddings) are kept long-term, reducing noise.

Each pattern has supporting citations: Mem0’s OS-like hierarchy, A-Mem’s graph notes, and LlamaIndex’s buffer-to-blocks scheme illustrate them. 

## 4. Proactive Agency / UX Design Patterns  
We also identify key mixed-initiative design patterns for proactive educational agents, based on HCI research and industry examples:

- **Context-Aware Suggestion Pipeline:** The agent continuously monitors the user’s workspace/utterances and generates timed suggestions. For example, Chen et al. (2024) built a **proactive coding assistant** that ingests the user’s entire code file and chat history, then **generates suggestion items** (each with a summary, implementation, explanation) and decides whether to display them. The core elements are: (a) *Context input* (code + dialog), (b) *LLM suggestion generator*, (c) *Timing logic* (when to interrupt with suggestions), and (d) *UI integration*. The agent only sends a suggestion when certain triggers fire (e.g. user idle, task milestone reached). This mixed-initiative pipeline (detect → suggest → integrate) can be adapted to education: e.g. watch a student’s problem-solving steps and pop up hints or next-question prompts at the right time. (Chen et al. found that **excessive suggestions** hurt UX even if task completion rose, underscoring the need for smart timing.)

- **Summary-Preview Suggestion UI:** Closely related, many systems display proactive hints initially in **summary form** to avoid overwhelming the user. In the coding assistant example, a proactive message **shows only a high-level description by default**; the full code or detailed hint is hidden under a “preview” button that the user can click. This lets the user accept, dismiss, or expand the suggestion on demand. We call this *progressive disclosure for proactive hints*. In education, this pattern means the system might say “It looks like you’re stuck on solving for x. I have a hint.” (summary), and only upon click reveal the full hint or worked example. The agent thus doesn’t monopolize the user’s view but still offers scaffolding.  

- **User-Profile–Driven Automation:** Drawing on GUM (General User Model) concepts, a proactive agent can turn the user’s profile into action. Shaikh et al. (2025) describe *GUMBOs* – assistants that “discover and execute useful suggestions on a user’s behalf” using a multimodal user model. For example, if the user profile shows “Project report due Friday” and “Needs thesis guidance”, a GUMBO might pre-populate an outline or set a reminder. In educational software, this could translate to automatically **personalizing the UI**: e.g. reshuffling dashboards to highlight next learning goals, scheduling study reminders based on past performance, or even auto-creating a quiz draft. The pattern is: maintain rich user preferences/progress, then **autonomously perform routine tasks** (like organizing materials, drafting recommendations) to reduce cognitive load. Crucially, the user must retain veto power (consent/undo).

Each viewpoint above is supported by specific evidence: Chen et al.’s proactive assistant prototype, Shaikh et al.’s GUMBO framework, and mixed-initiative literature on timing and control.  

## 5. Tables & Charts  

**Table 1: Comparison of Similar Systems** (as above).

**Table 2: Design Patterns** (Memory / Proactive) – examples and sources:

| Pattern                    | Description                                                      | Example / Source                                    |
|----------------------------|------------------------------------------------------------------|-----------------------------------------------------|
| **Hierarchical Memory**    | Split “working” vs “long-term” memory (context vs persistent store). LLM pages info between them, like OS RAM/disk. | *Mem0 (Chhikara et al. 2025) demonstrates this architecture.* |
| **Agentic Memory Graph**   | Memory as evolving graph of notes; new memories semantically linked to old, with dynamic updating. | *A-Mem / Mem0g (Chhikara et al. 2025) builds inter-connected memory nodes.* |
| **Buffer + Blocks**        | Keep short-term chat up to a limit, then **flush** old content into long-term blocks (facts/static/vector). | *LlamaIndex (2025) uses a token-limited chat buffer that offloads data to static, fact, and vector memory blocks.* |
| **Proactive Suggestion Pipeline** | Continuously sense user context → generate candidate hints → decide when to show → display in UI. | *Proactive coding assistant (Chen et al. 2024) monitors code context and injects timed suggestions.* |
| **Summary-Preview UI**     | Present proactive hints only as a brief summary by default; user expands to view full content. | *In Chen et al., proactive messages show short description with a “preview” button for details.* |
| **Profile-Driven Actions**| Use the general user model to perform tasks for the user (e.g. reminders, tool changes). | *GUMBOs (Shaikh et al. 2025) act on inferences (scheduling, content prep) derived from the user model.* |

**Memory Lifecycle (mermaid flow):**

```mermaid
flowchart TD
    A[User Interaction / Workspace] -->|Memory Extraction| B[Working Memory (Context Window)]
    B -->|Summarization / Consolidation| C[Long-Term Memory (Knowledge Store)]
    C -->|Retrieval| B
    B -->|Decay / Forget| D[Discard Unused Info]
    style A fill:#f9f,stroke:#333,stroke-width:1px
    style C fill:#ff9,stroke:#333,stroke-width:1px
    style B fill:#9ff,stroke:#333,stroke-width:1px
```

**Proactive UX Decision Flow (mermaid flow):**

```mermaid
flowchart LR
    S[User State & Context] --> T{Should Agent Suggest?}
    T -- Yes --> G[Generate Suggestion (LLM or Rule)]
    T -- No --> End[No Action]
    G --> D[Apply Filtering/Timing Heuristics]
    D --> V{Display to User?}
    V -- Yes --> U[Show Summary Hint in UI]
    V -- No --> End
    U --> C{User Response}
    C -- Accept --> I[Integrate Suggestion (e.g. fill answer, highlight tip)]
    C -- Dismiss --> End
    C -- Explore --> DFull[Show Full Hint/Explanation]
    DFull --> E{User Accept?}
    E -- Yes --> I
    E -- No --> End
```

## 6. Conclusion & MVP Recommendations  
**Identical Systems?** We found no existing end-to-end system identical to AREQA. The closest are research prototypes that tackle parts of the problem (LOOM, TutorLLM, LC-RAG, etc.), but our combination of *longitudinal GUM + real-time adaptation + progressive scaffold fading + proactive companions* is novel. This suggests strong publication potential, though careful evaluation will be needed (e.g. A/B tests, longitudinal studies) and guardrails to prevent over-assistance or privacy risks.

**3 Developer-Ready MVP Features:** Based on our findings, we recommend implementing these minimum features now:

1. **Persistent Memory Store:** Integrate a memory component that **captures and summarizes past user interactions**. For example, after each tutoring session, the system would extract key facts or decisions (via an LLM prompt) and store them in a knowledge base (see LC-RAG or Mem0). In practice, this could use an embedding store or LlamaIndex blocks to retain user profile (e.g. *“Student understands concept A but struggles with B”*). On each new session, the agent queries this store to recall prior context, preventing redundant teaching and enabling continuity. (This yields an immediate improvement in coherence and personalization.)

2. **Adaptive Hint/Scaffold Module:** Build an engine that **tracks the student’s performance** on practice questions (a simple KT model or point-tracking) and **adjusts hint levels**. Initially offer substantial hints or partial solutions; as the student demonstrates proficiency (tracked via quiz scores or correctness), gradually reduce hint detail (fading). This can be driven by ECD/SCT logic (as in Inquizzitor) combined with the user model. For example, if a student repeatedly answers similar questions correctly, the next hint might be a nudge rather than a solution. This scaffolding ensures cognitive support without overdependence. (E.g. if a user misses 3 questions on algebra, the agent intervenes with a worked example; as mastery grows, it only provides minimal cues.)

3. **Proactive Suggestion Interface:** Implement a UI feature where the agent can **occasionally push short suggestions or next-steps** based on the user model. For instance, after a learning task, a sidebar popup could suggest “Review linked concept: X” or “Try this practice problem” – phrased as summaries the user can click to accept or ignore. Behind this, the logic monitors student progress and deadlines (e.g. if a deadline is near, or if the student hasn’t used a topic for a while). The popup should show only a concise hint/title with a “details” button. On click, the agent would present the full explanation or auto-navigate to the resource. This prototype follows mixed-initiative principles: it anticipates needs (profile-driven) but leaves final control to the user. 

Each MVP is small but crucial: (1) **memory** ensures the agent “remembers” the learner, (2) **adaptive hints** operationalize scaffolding/fading, and (3) **suggestion UI** brings proactivity to the front-end. These features are grounded in the cited designs and can be implemented with existing LLM frameworks (e.g. LangChain/LlamaIndex memory modules, React UI for suggestions). Future work would refine them and integrate them into a cohesive long-term learning platform.

