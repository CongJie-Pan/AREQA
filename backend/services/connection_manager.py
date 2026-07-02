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

    async def broadcast_alert(self, user_id: str, content: str, sender_name: str = None):
        ws = self.active.get(user_id)
        if ws:
            try:
                payload = {"has_alert": True, "content": content}
                if sender_name:
                    payload["sender_name"] = sender_name
                await ws.send_json(payload)
                logger.debug(f"Broadcasted alert to user {user_id}: {content}")
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {e}")
                self.disconnect(user_id)

ws_manager = ConnectionManager()
