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
lk agent dev
```

Production deployment uses the same environment and agent name. The frontend
token endpoint embeds a room dispatch for `LIVEKIT_AGENT_NAME`, so the worker
must be running before users enable avatar mode.
