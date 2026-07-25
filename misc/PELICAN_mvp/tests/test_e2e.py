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

from pelican_mvp.llm import LlmConfig

# Monkey patch LlmConfig to force rule mode in E2E tests
_original_from_env = LlmConfig.from_environment
LlmConfig.from_environment = classmethod(lambda cls: None) # type: ignore

def assert_fully_clickable_in_viewport(page: Page, selector: str) -> None:
    locator = page.locator(selector)
    box = locator.bounding_box()
    assert box is not None
    viewport = page.viewport_size
    assert viewport is not None
    assert box["width"] > 0
    assert box["height"] > 0
    assert 0 <= box["x"]
    assert 0 <= box["y"]
    assert box["x"] + box["width"] <= viewport["width"]
    assert box["y"] + box["height"] <= viewport["height"]
    center_x = box["x"] + box["width"] / 2
    center_y = box["y"] + box["height"] / 2
    assert page.evaluate(
        """([x, y, selector]) => {
            const top = document.elementFromPoint(x, y);
            return Boolean(top && top.closest(selector));
        }""",
        [center_x, center_y, selector],
    )

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

def test_dynamic_intake_and_diagnosis_flow(page: Page) -> None:
    page.goto(URL)
    
    # Wait for initial page load and message
    page.wait_for_selector(".message.teacher")
    
    # Ensure clean state and rule mode
    page.select_option("#mode-select", "rule")
    page.click("#reset-btn")
    time.sleep(0.5)
    
    # Check that phase is onboarding
    expect(page.locator("#phase-display")).to_have_text("onboarding", ignore_case=True)
    expect(page.locator("#methodology-stages")).to_be_visible()
    
    # Complete calibration-first onboarding.
    page.fill("#chat-input", "深度學習")
    page.click(".send-btn")
    expect(page.locator("#phase-display")).to_have_text("onboarding", ignore_case=True)
    page.fill("#chat-input", "想理解原理")
    page.click(".send-btn")
    expect(page.locator("#phase-display")).to_have_text("onboarding", ignore_case=True)
    page.fill("#chat-input", "完全沒有基礎")
    page.click(".send-btn")

    # Wait for the foundation-first diagnostic question.
    page.wait_for_selector(".tree-node")
    expect(page.locator(".tree-node").first).to_be_visible()
    expect(page.locator("#phase-display")).to_have_text("diagnosis", ignore_case=True)
    expect(page.locator("#plan-source-display")).to_have_text("generated", ignore_case=True)
    expect(page.locator(".methodology-stage-name")).to_contain_text(["Goal", "Skill", "Diagnosis", "State", "EDF", "Tutor"])
    expect(page.locator("#skill-artifact-summary")).to_contain_text("deep_learning")
    expect(page.locator("#agent-executor-trace")).to_contain_text("skill_agent")
    
    # Answer the first question correctly
    page.fill("#chat-input", "用來衡量預測與目標之間的差距")
    page.click(".send-btn")
    
    # Check that tree updates the node to mastered
    expect(page.locator(".tree-node.mastered").first).to_be_visible()
    expect(page.locator("#agent-proposals")).to_contain_text("state_agent")
    expect(page.locator("#agent-executor-trace")).to_contain_text("state_agent")
    expect(page.locator("#learner-progress-snapshot")).to_contain_text("mastered")
    page.fill("#chat-input", "我不知道")
    page.click(".send-btn")
    expect(page.locator("#tutor-proposal-trace")).to_contain_text("scaffold")
    expect(page.locator("#agent-executor-trace")).to_contain_text("slow_simulator_agent")


@pytest.mark.parametrize("viewport", [
    {"width": 1920, "height": 840},
    {"width": 1366, "height": 768},
    {"width": 390, "height": 844},
    {"width": 390, "height": 667},
])
def test_chat_composer_remains_usable_at_supported_viewports(page: Page, viewport: dict[str, int]) -> None:
    page.set_viewport_size(viewport)
    page.goto(URL)
    page.wait_for_selector(".message.teacher")

    expect(page.locator("#methodology-stages")).to_be_visible()
    expect(page.locator(".methodology-details")).not_to_have_attribute("open", "")
    expect(page.locator("#chat-input")).to_be_visible()
    expect(page.locator(".send-btn")).to_be_visible()
    assert_fully_clickable_in_viewport(page, "#reset-btn")
    assert_fully_clickable_in_viewport(page, "#chat-input")
    assert_fully_clickable_in_viewport(page, ".send-btn")

    page.locator(".methodology-details summary").click()
    expect(page.locator("#skill-artifact-summary")).to_be_visible()
    expect(page.locator("#agent-executor-trace")).to_be_visible()
    expect(page.locator("#tutor-proposal-trace")).to_be_visible()
    assert_fully_clickable_in_viewport(page, "#chat-input")
    assert_fully_clickable_in_viewport(page, ".send-btn")
    page.click("#reset-btn")
    expect(page.locator("#phase-display")).to_have_text("onboarding", ignore_case=True)
    
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
