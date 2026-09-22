# Pedagogy General Skill Cases

Source: `eval/datasets/pedagogy_general_skill_cases.jsonl`

Total cases: 8

## general_reference_zpd_001

- Category: General Concept Explanation
- Subject area: Learning Science
- Subtopic: Zone of Proximal Development
- Learning goal: Teach Me X
- Setting: Self-Taught

### Learner Persona

- asks direct conceptual questions
- wants clear definitions
- gets annoyed by unnecessary questions

### Scenario Instructions

Answer directly and concisely. Demonstrate REFERENCE behavior: explain the concept without forcing Socratic questioning.

### Initial Query

> What is the Zone of Proximal Development? Explain it simply.

### Expected Tutor Behavior

- defines ZPD clearly
- uses a simple example
- keeps cognitive load low
- does not force a follow-up question

## general_practice_math_hint_002

- Category: Math Reasoning
- Subject area: Math
- Subtopic: Linear Equations
- Learning goal: Practice
- Setting: Classroom

### Learner Persona

- wants the final answer
- can do arithmetic with hints
- needs practice rather than copying

### Scenario Instructions

Do not simply solve the equation for the learner. Give a small hint or next step and invite the learner to continue.

### Initial Query

> Solve 3x + 5 = 20 for me. I just need the answer.

### Expected Tutor Behavior

- does not only output x = 5
- gives the first reasoning step
- asks learner to perform the next step
- keeps tone supportive

## general_metacognition_debug_003

- Category: Debugging Reasoning
- Subject area: Programming
- Subtopic: Loop Logic
- Learning goal: Practice
- Setting: Self-Taught

### Learner Persona

- is frustrated
- assumes the code is randomly broken
- needs to inspect reasoning

### Scenario Instructions

Use metacognitive guidance. Help the learner inspect the loop condition rather than rewriting the whole solution.

### Initial Query

> My loop never stops and I don't know why. It checks while i != 10, but sometimes i jumps by 2. What's going on?

### Expected Tutor Behavior

- identifies the likely skipped value issue
- asks learner to trace values
- does not rewrite a full program
- helps self-check the condition

## general_cognitive_load_science_004

- Category: Science Explanation
- Subject area: Science
- Subtopic: Photosynthesis
- Learning goal: Teach Me X
- Setting: Classroom

### Learner Persona

- beginner
- gets overwhelmed by terminology
- benefits from analogy

### Scenario Instructions

Explain with cognitive load control: one core idea first, then minimal terms, then a small check or example.

### Initial Query

> Photosynthesis has so many words. Can you explain what actually happens without making it complicated?

### Expected Tutor Behavior

- starts with the core idea
- uses simple language before terms
- limits details
- may include one check-for-understanding

## general_curiosity_history_005

- Category: Historical Thinking
- Subject area: History
- Subtopic: Cause And Consequence
- Learning goal: Learn
- Setting: Classroom

### Learner Persona

- finds history boring
- likes concrete examples
- needs curiosity

### Scenario Instructions

Make the topic approachable with a small information gap or concrete contrast while still answering the question.

### Initial Query

> Why do teachers always say historical events have multiple causes? Isn't there usually one main reason?

### Expected Tutor Behavior

- answers the question
- uses a concrete example or analogy
- stimulates curiosity without rambling
- invites causal comparison

## general_adaptive_scaffold_006

- Category: Study Strategy
- Subject area: General Study Skills
- Subtopic: Learning Plan
- Learning goal: Learn
- Setting: Self-Taught

### Learner Persona

- beginner
- does not know where to start
- needs structure but not a giant plan

### Scenario Instructions

Give beginner-friendly scaffolding and avoid an overwhelming master plan. Offer the next small action.

### Initial Query

> I want to learn statistics but I don't even know what to ask first. Where should I start?

### Expected Tutor Behavior

- acknowledges beginner uncertainty
- offers a small structured path
- does not overload with many resources
- gives one immediate next step

## general_domain_orientation_007

- Category: Domain Orientation
- Subject area: Design
- Subtopic: Product Design Scope
- Learning goal: Reference
- Setting: Self-Taught

### Learner Persona

- asks a broad but simple field-scope question
- wants orientation not a curriculum
- may be browsing interests

### Scenario Instructions

Answer as a compact domain orientation. Do not turn it into a staged roadmap, full study plan, or resource list unless asked.

### Initial Query

> 產品設計學什麼？

### Expected Tutor Behavior

- gives one plain-language framing sentence
- lists three to five core areas
- does not produce a full roadmap
- may ask one concise goal question

## general_need_clarification_008

- Category: Learning Start
- Subject area: Data Science
- Subtopic: Starting Point
- Learning goal: Learn
- Setting: Self-Taught

### Learner Persona

- has a vague learning intention
- has not stated goal or current level
- could be overwhelmed by a big plan

### Scenario Instructions

Clarify the learner's goal before producing a full plan. Keep any orientation minimal.

### Initial Query

> 我想學資料科學，該從哪裡開始？

### Expected Tutor Behavior

- does not output a giant roadmap immediately
- asks one concise question about goal level or use case
- may provide a tiny orientation
- keeps the answer short
