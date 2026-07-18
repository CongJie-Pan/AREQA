import pytest
import threading
import time
import uvicorn
from playwright.sync_api import Page, expect
from pelican_mvp.server import app

PORT = 8123
URL = f"http://127.0.0.1:{PORT}"

class UvicornTestServer(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        pass

@pytest.fixture(scope="module", autouse=True)
def run_server() -> None:
    config = uvicorn.Config(app=app, host="127.0.0.1", port=PORT, log_level="error")
    server = UvicornTestServer(config=config)
    
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    
    time.sleep(1) # wait for startup
    yield
    
    server.should_exit = True
    thread.join(timeout=2)

def test_homepage_loads(page: Page) -> None:
    page.goto(URL)
    expect(page).to_have_title("PELICAN Knowledge Tracing MVP")
    expect(page.locator(".sidebar h2")).to_have_text("PELICAN MVP")

def test_diagnosis_flow_and_tree_updates(page: Page) -> None:
    page.goto(URL)
    
    # Wait for initial page load and message
    page.wait_for_selector(".message.teacher")
    
    # Ensure clean state and rule mode
    page.select_option("#mode-select", "rule")
    time.sleep(0.5)
    page.click("#reset-btn")
    time.sleep(0.5)
    
    # Check tree is visible
    expect(page.locator(".tree-node").first).to_be_visible()
    
    # Wait for the teacher to ask the first diagnostic question
    expect(page.locator(".message.teacher").first).to_contain_text("診斷題：輸入圖片為 10x10")
    
    # Answer the first question correctly (8)
    page.fill("#chat-input", "8")
    page.click(".send-btn")
    
    # Check that tree updates the node to mastered
    expect(page.locator(".tree-node.mastered").first).to_be_visible()
    
def test_mode_switch(page: Page) -> None:
    page.goto(URL)
    page.wait_for_selector(".message.teacher")
    
    # Auto-accept any alerts
    page.on("dialog", lambda dialog: dialog.accept())
    
    # Change mode
    page.select_option("#mode-select", "llm")
    
    # Mode switch happens async, we can check value
    # If no LLM key, it reverts to rule, if there is a key, it stays llm.
    # We just ensure it doesn't crash the UI.
    time.sleep(0.5)
    expect(page.locator("#mode-select")).to_be_visible()
