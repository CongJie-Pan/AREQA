# Learning Manager Orchestrator Manual Test Script

## Scope

This script validates realistic humanities learner turns after the learning manager orchestration layer is enabled. The expected behavior is that the orchestrator interprets the current turn in context, while `PelicanEngine` remains the owner of state writes and mastery evidence.

## Act 01: Active Prompt Short Answer

Setup: The tutor asks, "在這些改革中，你覺得哪一項對打破舊有階級影響最深？"

Input: `廢藩置縣`

Pass condition: The system treats the input as an answer attempt to the active prompt, routes to diagnosis, and does not ask the learner to clarify what `廢藩置縣` means before evaluating the answer.

## Act 02: Focused Turning Point Clarification

Setup: The previous tutor message mentions a `轉折點`.

Input: `什麼轉折點?`

Pass condition: The system gives a focused clarification of the specific turning point and does not replay the whole lesson. No mastery evidence is written for this turn.

## Act 03: Humanities Partial Understanding

Setup: The learner has just received a humanities explanation about Meiji Restoration reforms.

Input: `簡單來說，明治維新是日本推動西化和現代化的改革。`

Pass condition: The system responds to the substance of the learner's partial understanding, fills the missing political/social-structure link, and avoids forcing a mechanical full rephrase unless the pedagogical strategy explicitly requires a check.

## Act 04: Resume After Clarification

Setup: The learner has received a focused clarification and then gives a relevant answer to the original prompt.

Input: `我覺得是廢藩置縣，因為中央取代各藩，舊武士階級的政治基礎被削弱。`

Pass condition: The system resumes the active knowledge point, evaluates the answer, and only writes mastery evidence after engine-side diagnostic validation.
