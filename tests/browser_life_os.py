"""Real Edge layout check for the life-os shell; no database or AI calls."""
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from playwright.sync_api import expect, sync_playwright

from app.core.config import Settings
from app.main import create_app


def run():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(Settings(_env_file=None, database_url=None, migration_database_url=None, log_level="ERROR"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/life-os")
            expect(page.get_by_role("heading", name="人生运行系统")).to_be_visible()
            expect(page.locator(".life-os-panel")).to_have_count(8)
            clock = page.locator("#life-os-time")
            expect(clock).not_to_have_text("--:--:--")
            first_time = clock.inner_text()
            page.wait_for_timeout(1200)
            assert clock.inner_text() != first_time
            expect(page.locator("#life-os-form")).to_be_visible()
            output = Path(tempfile.gettempdir()) / "life-os-step1"
            output.mkdir(exist_ok=True)
            page.screenshot(path=str(output / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            expect(page.locator("#sidebar")).to_have_css("visibility", "hidden")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#menu-button").click()
            expect(page.locator("#sidebar")).to_have_css("visibility", "visible")
            page.locator("#scrim").click(position={"x": 380, "y": 800})
            expect(page.locator("#sidebar")).to_have_css("visibility", "hidden")
            page.screenshot(path=str(output / "mobile.png"), full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(10)


if __name__ == "__main__":
    run()
    print("PASS life-os desktop/mobile layout, eight sections, live clock, chat entry and no browser errors")
