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

Render should run this as a Background Worker, not as the FastAPI web service:

```bash
cd livekit_agent && pip install -r requirements.txt && python agent.py start
```

The included `Dockerfile` uses the same production command. Production
deployment uses the same environment and agent name. The frontend token endpoint
embeds a room dispatch for `LIVEKIT_AGENT_NAME`, so the worker must be running
before users enable avatar mode.

Successful startup logs include:

```text
livekit_agent.worker_config_ready ... livekit_configured=True openai_configured=True anam_configured=True avatar_configured=True
```

Successful avatar sessions include:

```text
livekit_agent.session_starting ...
livekit_agent.avatar_joined ...
```
