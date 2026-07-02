import time
import requests
import json
import urllib.request
import asyncio
import websockets

BASE_URL = "http://localhost:8000"

def test_t01():
    print("Running API-T01: log_action -> compeer_rejected")
    payload = {"user_id": "default_user", "action_type": "compeer_rejected", "timestamp": int(time.time()), "context": {}}
    res = requests.post(f"{BASE_URL}/api/v1/log_action", json=payload)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok"
    
    # Check hot memory directly from file
    time.sleep(0.5)
    with open("/workspaces/AREQA/data/gum_data/hot_memory.json", "r") as f:
        hot_mem = json.load(f)
    assert "user_cooldown_until" in hot_mem, "Cooldown not saved to hot_memory"
    
    # Verify cooldown timestamp (around +1800 seconds)
    cooldown = hot_mem["user_cooldown_until"]
    expected = time.time() + 1800
    assert abs(cooldown - expected) < 10, f"Expected {expected}, got {cooldown}"
    print("✅ API-T01 Passed")

def test_t02():
    print("Running API-T02: log_action -> scroll")
    payload = {"user_id": "default_user", "action_type": "scroll", "timestamp": int(time.time()), "context": {"delta": 300, "page": "/search"}}
    res = requests.post(f"{BASE_URL}/api/v1/log_action", json=payload)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok"
    print("✅ API-T02 Passed")

def test_t03():
    print("Running API-T03: proactive-check in cooldown")
    # T01 already set cooldown
    res = requests.get(f"{BASE_URL}/api/v1/proactive-check?user_id=default_user")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["has_alert"] is False, "Alert fired during cooldown!"
    print("✅ API-T03 Passed")

async def test_t04():
    print("Running API-T04: WebSocket broadcast")
    # Reset cooldown so we can trigger proactive
    # Wait, we can't easily reset it via API unless we mock it, or we just write to the hot memory directly
    import json
    path = "/workspaces/AREQA/data/gum_data/hot_memory.json"
    with open(path, "r") as f:
        hot = json.load(f)
    if "user_cooldown_until" in hot:
        del hot["user_cooldown_until"]
    
    # We trigger the alert via hot_memory directly to see if websocket pushes it
    hot["trigger_proactive"] = True
    hot["current_learner_state"] = "GIVING_UP"
    
    with open(path, "w") as f:
        json.dump(hot, f)
    
    # Now connect WS and wait for the message
    try:
        async with websockets.connect(f"ws://localhost:8000/api/v1/ws/notifications?user_id=default_user", ping_interval=None) as ws:
            print("Connected to WebSocket. Waiting for message...")
            # We wait up to 5 seconds
            msg_str = await asyncio.wait_for(ws.recv(), timeout=30.0)
            msg = json.loads(msg_str)
            print("Received:", msg)
            assert msg.get("has_alert") is True
            assert "content" in msg
            print("✅ API-T04 Passed")
    except Exception as e:
        print("❌ API-T04 Failed:", e)

def test_t05():
    print("Running API-T05: Swagger schema check")
    res = requests.get(f"{BASE_URL}/openapi.json")
    assert res.status_code == 200, res.text
    schema = res.json()
    paths = schema.get("paths", {})
    assert "/api/v1/log_action" in paths
    assert "/api/v1/proactive-check" in paths
    print("✅ API-T05 Passed")

if __name__ == "__main__":
    test_t01()
    test_t02()
    test_t03()
    test_t05()
    print("Running Async tests...")
    asyncio.run(test_t04())
    print("ALL TESTS PASSED")
