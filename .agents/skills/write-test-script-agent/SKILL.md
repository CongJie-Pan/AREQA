---
name: write-test-script-agent
description: Write structured, traceable manual test scripts for product features, bug fixes, experiments, integrations, and background workflows. Use when Codex needs to create or revise a human-executable test scenario document with Acts, exact inputs or actions, expected outputs, backend verification, success criteria, and final acceptance. Write in Traditional Chinese by default unless the user requests another language.
---

# Write Test Script Agent

Create a manual test script that a tester can execute without guessing the intended behavior. Use clear, natural Traditional Chinese by default. Base the script on the relevant requirements, experiment reports, implementation plans, existing test scripts, code paths, and tests; do not treat a clean UI alone as proof that backend state is correct.

## Workflow

1. Read the requested scope and the relevant product documents, implementation plan, existing scripts, source entry points, and tests.
2. Identify the user-visible behavior, the protected backend state, the failure modes, observability data, and any timing or environment requirements.
3. Start with concrete test preconditions: test account state, separate conversations or users, required configuration, available logs or database access, and any fault-injection setup.
4. Divide the script into narrow sequential Acts. Give each Act one behavior to prove. Do not combine unrelated checks into one Act.
5. End with an overall acceptance decision and a failure-record template that makes the defect reproducible.

## Required Document Format

Use this format unless the user explicitly provides another one:

```markdown
# <Product or Feature> 人工測試劇本：<Scope>

<One short paragraph explaining the goal and the risk being verified.>

## 測試前置條件

- <Clean test account or required seeded state>
- <Required distinct conversations, users, permissions, or devices>
- <Required configuration, timing window, logs, database access, or fault injection>

## 第一幕：<One Behavior>

### 輸入

<Exact user message in a code block, or an exact tester action/setup.>

### 預期輸出

- <Visible response, UI state, notification, or API result>

### 後端查核

- <Required persisted record, source/provenance, state transition, log event, or absence of a forbidden write>

### 成功標準

<One decisive, observable pass condition.>

## 第二幕：<Next Behavior>

...

## 最終判定

<State that all Acts must pass. For a failure, record the Act number, test account, exact input/action, timestamps, conversation ID, message ID, task ID, visible result, and relevant backend events.>
```

## Act Writing Rules

- Give every Act all four subsections: `輸入`, `預期輸出`, `後端查核`, and `成功標準`.
- Put literal chat messages, commands, and payloads in fenced code blocks. Make tester actions unambiguous: name the page, button, wait period, and state transition where relevant.
- Make expected output specific. Do not write vague assertions such as "works normally" or "the system handles it correctly." State what must appear, what must not appear, and when it must happen.
- Make backend checks verify the actual risk. For memory behavior, check the source role, provenance, candidate/promotion state, and absence of an unauthorized profile write. For queues, verify durable scheduling, claim, delivery, retry, idempotency, and correlated task IDs. For streaming, verify event ordering, terminal semantics, and cancellation where relevant.
- State explicit timing windows for delayed workflows. Define the boundary that marks a failure, rather than merely saying "wait a while."
- Use distinct conversation IDs or users whenever the requirement depends on independent evidence, isolation, deduplication, or permissions. Do not use a question as evidence for a declarative preference or fact.
- Keep one Act focused on one behavior. Add another Act for recovery, retry, idempotency, permission isolation, or UI consistency rather than hiding those checks inside a broad checklist.
- Include both positive and negative paths when the risk requires them: for example, valid evidence promotes only after its threshold, while a question, assistant text, or one-off context cannot promote.

## Final Review

Before delivering, confirm that the script is in Traditional Chinese unless another language was requested; every Act has the four required subsections; inputs/actions are reproducible; expected outcomes are measurable; backend checks are applicable and concrete; timing boundaries are explicit; and the final decision describes exactly what evidence to retain when a test fails.
