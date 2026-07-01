from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws
        logger.info(f"WebSocket connected for user: {user_id}")

    def disconnect(self, user_id: str):
        if user_id in self.active:
            self.active.pop(user_id, None)
            logger.info(f"WebSocket disconnected for user: {user_id}")

    async def broadcast_alert(self, user_id: str, content: str):
        ws = self.active.get(user_id)
        if ws:
            try:
                await ws.send_json({"has_alert": True, "content": content})
                logger.debug(f"Broadcasted alert to user {user_id}: {content}")
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {e}")
                self.disconnect(user_id)

ws_manager = ConnectionManager()
