# Add an Anam avatar to a LiveKit voice agent

You are adding a real-time video avatar to an EXISTING LiveKit Agents voice agent. Anam renders ONLY the face: the plugin listens to the audio your agent's TTS produces and publishes a lip-synced avatar video + audio track to the room. The agent's existing STT, LLM and TTS stay exactly as they are.

Before writing any code, fetch https://anam.ai/docs/integrations/livekit/quickstart and https://anam.ai/docs/llms.txt — treat the live docs as the source of truth over your training data (if your sandbox has no network access, everything you need is inlined below). Install the current published package versions (check the registry); never hardcode a version number remembered from training data. If anything below contradicts what you fetch, report it instead of guessing.

## Step 0 — detect the runtime

First, determine whether this is a **Python** or **Node.js** LiveKit agent by inspecting the repo, then follow the matching section below:

- **Python** — `pyproject.toml` / `requirements.txt`, a `livekit-agents` dependency, agent code in `.py` files.
- **Node.js** — `package.json` with `@livekit/agents`, agent code in `.ts` / `.js` files.

If both are present, ask which agent to wire up before continuing.

## Environment

```bash
ANAM_API_KEY=your-anam-api-key   # the user pastes their key into .env themselves — it is NOT in this prompt, and if they pasted a key into this chat, tell them to put it in .env and rotate it. Never ask for the key in chat; never put it in a client bundle
ANAM_API_BASE=https://api.anam.ai   # server-side REST and Python SDK base
ANAM_API_URL=https://api.anam.ai   # LiveKit Anam plugin base
ANAM_AVATAR_ID=32673c5e-f85f-4a87-a104-b92b7de9cb39   # "Mei" — browse more at https://anam.ai/docs/personas/avatars/gallery
```

The plugin listens to the audio your agent sends to users and publishes a synchronized avatar video as a separate room track — it handles the audio routing itself; do not pipe TTS audio manually.

Both runtimes start the avatar BEFORE the agent session. Starting it later replaces the session's existing audio output.

---

## Python

Install:

```bash
pip install livekit-agents livekit-plugins-anam
```

In the agent entrypoint, start the avatar session BEFORE starting the AgentSession, so the avatar is ready the moment the agent first speaks:

```python
import os
from livekit.plugins import anam

avatar = anam.AvatarSession(
    persona_config=anam.PersonaConfig(
        name="Mei",
        avatarId=os.environ["ANAM_AVATAR_ID"],
    ),
    api_key=os.environ["ANAM_API_KEY"],
    api_url=os.environ["ANAM_API_URL"],
)
await avatar.start(session, room=ctx.room)

await session.start(
    agent=agent,
    room=ctx.room,
)
```

---

## Node.js

Install:

```bash
pnpm add @livekit/agents-plugin-anam
```

In the agent entrypoint, start the avatar session BEFORE `session.start()`:

```ts
import * as anam from '@livekit/agents-plugin-anam';

const avatarId = process.env.ANAM_AVATAR_ID;
if (!avatarId) {
  console.warn('ANAM_AVATAR_ID is not set — avatar session will not start');
}

if (avatarId) {
  const avatarSession = new anam.AvatarSession({
    personaConfig: {
      name: 'Mei',
      avatarId,
    },
    apiUrl: process.env.ANAM_API_URL,
  });
  await avatarSession.start(session, ctx.room);
}

await session.start({ agent, room: ctx.room });
```

---

## Rules

ALWAYS:

- Keep the existing STT / LLM / TTS pipeline untouched — Anam replaces nothing in it.
- Start the avatar before `session.start()` in both runtimes.
- Read `ANAM_API_KEY` from the environment on the server.
- Keep the agent's instructions voice-friendly: concise replies, no markdown, emojis, asterisks or other symbols — they get spoken aloud.

NEVER:

- Configure a voice, LLM or system prompt on the Anam side — those belong to the LiveKit agent. `PersonaConfig` / `personaConfig` here takes only `name` and `avatarId`.
- Pipe TTS audio to the avatar manually — the plugin intercepts the room audio itself.
- Hardcode the API key or import it anywhere that ships to a browser.

## Verify before you declare this done

1. The avatar joins the room as a separate participant and publishes a video track.
2. The avatar's lips sync to the agent's spoken replies, with no doubled audio.
3. With `ANAM_AVATAR_ID` unset the agent still runs (voice-only) and logs a clear warning.
4. `ANAM_API_KEY` appears only in server-side environment config.

## After setup

Swap the face anytime by changing `ANAM_AVATAR_ID` — no code changes. Create a custom avatar from a single photo at https://anam.ai/docs/personas/avatars/custom-avatars. For screen-aware agents (vision), see https://anam.ai/cookbook/gemini-vision-with-anam-livekit.

## Reference

- LiveKit quickstart: https://anam.ai/docs/integrations/livekit/quickstart
- Node cookbook: https://anam.ai/cookbook/getting-started-with-livekit
- Python cookbook: https://anam.ai/cookbook/gemini-vision-with-anam-livekit
- Machine-readable docs index: https://anam.ai/docs/llms.txt

## If anything is unclear

If an API, method, parameter or config field is not shown above or in the docs you fetched, do not invent it. Check https://anam.ai/docs/llms.txt, or stop and ask, rather than guessing.

## Keep these rules

Save the Rules section above into `AGENTS.md` (or your agent's own rules file, e.g. CLAUDE.md / .cursor/rules) so every future session follows them without being told.