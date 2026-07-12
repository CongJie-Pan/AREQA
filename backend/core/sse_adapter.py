from __future__ import annotations

import json

from .events import AgentEvent, EventType, TERMINAL_EVENT_TYPES


class SSEAdapter:
    """Serialize typed runtime events while enforcing stream invariants."""

    def __init__(self) -> None:
        self._last_sequence = 0
        self._terminal_emitted = False
        self._transport_closed = False

    def encode(self, event: AgentEvent) -> str:
        self._accept(event)
        payload = event.payload
        if event.type is EventType.METADATA:
            if not isinstance(payload, dict):
                raise TypeError("metadata payload must be an object")
            payload = dict(payload)
            payload.setdefault("runId", event.run_id)
            payload.setdefault("schemaVersion", event.schema_version)

        return f"event: {event.type.value}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _accept(self, event: AgentEvent) -> None:
        if self._transport_closed:
            raise ValueError("cannot emit an event after the transport is closed")
        if self._terminal_emitted:
            raise ValueError("cannot emit an event after a terminal event")
        if event.sequence <= self._last_sequence:
            raise ValueError("event sequence must be strictly increasing")

        self._last_sequence = event.sequence
        self._terminal_emitted = event.type in TERMINAL_EVENT_TYPES

    def encode_legacy(self, block: str, run_id: str) -> str:
        """Validate and pass through an event from the legacy producer path."""
        if self._transport_closed:
            raise ValueError("cannot emit data after the transport is closed")
        if block.startswith(":"):
            return block
        if block.strip() == "data: [DONE]":
            self._transport_closed = True
            return block
        if self._terminal_emitted:
            raise ValueError("cannot emit an event after a terminal event")

        event_line = next((line for line in block.splitlines() if line.startswith("event: ")), None)
        data_line = next((line for line in block.splitlines() if line.startswith("data: ")), None)
        event_name = event_line.removeprefix("event: ").strip() if event_line else ""
        payload = None
        if data_line:
            try:
                payload = json.loads(data_line.removeprefix("data: "))
            except json.JSONDecodeError:
                payload = data_line.removeprefix("data: ")

        try:
            event_type = EventType(event_name) if event_name else EventType.ANSWER_DELTA
        except ValueError:
            # Internal compatibility markers are validated as answer deltas but
            # retain their old wire representation during migration.
            event_type = EventType.ANSWER_DELTA
        typed_event = AgentEvent(
            type=event_type,
            payload=payload,
            run_id=run_id,
            sequence=self._last_sequence + 1,
        )
        self._accept(typed_event)
        return block
