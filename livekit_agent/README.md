# AREQA LiveKit Avatar Agent

This worker handles the optional avatar path for Live Tutor. The main AREQA app
continues to support OpenAI-direct voice mode; this worker is only needed when
the learner enables the avatar button.

Required environment:

```bash
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
OPENAI_API_KEY=...
ANAM_API_KEY=...
ANAM_AVATAR_ID=...
LIVEKIT_AGENT_NAME=areqa-live-tutor
```

Run locally:

```bash
cd livekit_agent
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python agent.py dev
```

Production start command:

```bash
python agent.py start
```

Deploy to LiveKit Agent Cloud from the repository root:

```bash
scripts/livekit-agent.sh deploy
```

Sync secrets from the repository `.env` to LiveKit Agent Cloud:

```bash
scripts/livekit-agent.sh sync-secrets
```

The helper script never prints secret values and clears its temporary secrets
file after upload. Set `AREQA_ENV_FILE=/path/to/.env` to sync from a different
env file.

Render can also run this as a Background Worker, but LiveKit Agent Cloud is the
preferred deployment target for this integration. The included `Dockerfile` uses
the same production command and installs Python dependencies with `uv` for
faster cloud builds. Production deployment uses the same environment and agent
name. The frontend token endpoint embeds a room dispatch for
`LIVEKIT_AGENT_NAME`, so the worker must be running before users enable avatar
mode.

Successful startup logs include:

```text
livekit_agent.worker_config_ready ... livekit_configured=True openai_configured=True anam_configured=True avatar_configured=True
```

Successful avatar sessions include:

```text
livekit_agent.session_starting ...
livekit_agent.avatar_joined ...
```
