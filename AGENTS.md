# AREQA Agent Notes

## Default Implementation Workflow

When implementing code in this repository, use this workflow by default.

### Task TODO List

Before editing files, write a concise task TODO list that covers:

1. Inspect the relevant architecture, files, tests, and existing conventions.
2. Identify the smallest safe implementation boundary.
3. Make scoped code changes that follow the current project patterns.
4. Add or update focused tests for the changed behavior.
5. Run the relevant tests and quality checks.
6. Report changed files, validation results, and any remaining unrelated failures.

### Investigate

- Use Drift project context when available for unfamiliar areas or architecture-sensitive changes.
- Read the relevant source files and matching tests before modifying code.
- Prefer `rg` / `rg --files` for search.
- Do not guess existing utilities, state stores, routes, environment variables, or framework patterns.
- Check the current git status before broad edits, and do not revert unrelated user changes.

### Design

- Fit changes into the existing module boundaries instead of introducing new architecture casually.
- Keep behavior backward-compatible unless the task explicitly asks for a breaking change.
- Make optional integrations fail soft when possible, especially provider, avatar, voice, memory, and search features.
- Keep secrets server-side. Never add provider keys, client secrets, JWT secrets, or tokens to frontend bundles.
- Add abstractions only when they remove real duplication or isolate a real ownership boundary.

### Execute

- Keep edits scoped to files required by the task.
- Use existing stores, service modules, route patterns, logging utilities, and styling conventions.
- Add concise comments only where they explain non-obvious boundaries, fallback behavior, concurrency, security, or compatibility.
- New code comments must be in English.
- Add safe structured logs for important provider calls, fallback paths, state transitions, and error boundaries.
- Logs must not include raw user text, prompts, model output, credentials, API keys, tokens, or unnecessary personal data.

### Tests And Quality Gates

- Add or update tests proportional to the risk and behavior changed.
- Prefer focused unit tests for pure UI/state/service behavior.
- Add integration or e2e-style tests when wiring crosses components, stores, services, or routes.
- For frontend changes, run the most relevant Vitest files first.
- Run `npm run check:report:strict` before considering frontend work complete.
- If the full suite has unrelated failures, report them clearly with file/test names and keep the task-scoped tests green.

### Final Report

After implementation, summarize:

- What changed.
- Which tests/checks passed.
- Which checks could not be run or failed for unrelated reasons.
- Any follow-up that is required before production rollout.

### Completion

- After implementation and validation are complete, commit the task changes to git without waiting for extra confirmation.
- Mark the task as completed after the commit succeeds.

## Anam Live Tutor Avatar

- Keep AREQA Live Tutor's existing STT, LLM, and TTS pipeline owned by the voice agent.
- Use Anam as the avatar face renderer only. Do not configure Anam to replace AREQA prompts, tools, voice logic, or memory/context routing.
- Keep `ANAM_API_KEY` server-side. Never place Anam, OpenAI, LiveKit, or other provider secrets in frontend bundles.
- Prefer the official LiveKit Anam avatar plugin when wiring production avatar video. The avatar must be optional: if `ANAM_AVATAR_ID` is unset or the avatar fails, voice mode should continue with the AREQA logo fallback.
- Do not manually pipe TTS audio when using the LiveKit Anam plugin. The plugin listens to the agent session audio output and publishes synchronized avatar media tracks.
- For audio passthrough experiments, match Anam's required PCM format and explicitly end each audio sequence on completion or interruption.

### LiveKit Integration Shape

- Live Tutor is voice-first by default. Keep `avatarEnabled` defaulting to `false`; only switch to LiveKit/Anam when the user turns the avatar on.
- The browser must request a short-lived LiveKit token through the Next.js proxy route `/api/realtime/livekit-avatar-session`, which forwards to FastAPI `/api/v1/realtime/livekit-avatar-session`.
- Mint LiveKit room tokens only in the backend. The frontend may receive `livekit_url`, `room_name`, `participant_identity`, `expires_at`, and the signed token, but never receives LiveKit API keys or secrets.
- Dispatch the configured LiveKit agent with `RoomConfiguration` and keep the agent name aligned through `LIVEKIT_AGENT_NAME`.
- Run the LiveKit worker from `livekit_agent/` as a separate service. It owns the OpenAI Realtime voice session plus Anam avatar plugin startup for the LiveKit room.
- If LiveKit config, token minting, room connection, or avatar startup fails, fall back to the direct OpenAI Realtime voice path and leave the logo fallback visible.
- Keep debug logs structured and safe. Log provider selection, session creation, fallback, track subscription, and elapsed timings, but never log room tokens, API secrets, raw prompts, user messages, or model output.
