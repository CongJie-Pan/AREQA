"""WebSocket notification routes for the backend app."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket

from auth import get_current_user
from services.connection_manager import ws_manager

router = APIRouter()

from services.connection_manager import ws_manager

@router.post("/api/v1/ws/ticket")
async def generate_ws_ticket(current_user_id: str = Depends(get_current_user)):
    from services.memory.store.service import get_global_store
    import secrets
    store = get_global_store()
    if not store:
        raise HTTPException(status_code=500, detail="Redis store not initialized")

    ticket = secrets.token_urlsafe(32)
    # Store ticket with TTL 30 seconds
    await store.redis.setex(f"ws_ticket:{ticket}", 30, current_user_id)
    return {"ticket": ticket}

@router.websocket("/api/v1/ws/notifications")
async def ws_notifications(websocket: WebSocket, ticket: str):
    # 手動驗證 Origin（CORSMiddleware 不覆蓋 WebSocket）
    origin = websocket.headers.get("origin")
    allowed = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
    if origin and origin not in allowed and not origin.endswith(".onrender.com"):
        await websocket.close(code=4001)  # Policy Violation
        return

    from services.memory.store.service import get_global_store
    store = get_global_store()
    if not store:
        await websocket.close(code=1011)
        return

    user_id_bytes = await store.redis.getdel(f"ws_ticket:{ticket}")
    if not user_id_bytes:
        await websocket.close(code=4001)
        return

    user_id = user_id_bytes.decode("utf-8") if isinstance(user_id_bytes, bytes) else user_id_bytes

    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # 維持連線存活
    except Exception:
        ws_manager.disconnect(user_id)
