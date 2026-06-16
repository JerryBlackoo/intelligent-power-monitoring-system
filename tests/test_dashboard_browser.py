from pathlib import Path

from playwright.sync_api import sync_playwright


def test_dashboard_browser_flow() -> None:
    screenshot = Path("static/reports/dashboard-smoke.png")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.goto("http://127.0.0.1:8000/dashboard")
        page.wait_for_load_state("networkidle")
        assert "电力智能巡检工作台" in page.title()
        page.get_by_text("上传模拟推理").click()
        page.wait_for_selector("text=一般告警")
        page.get_by_text("解释首条告警").click()
        page.wait_for_selector("text=处理建议")
        page.screenshot(path=str(screenshot), full_page=True)
        browser.close()

    assert screenshot.exists()
