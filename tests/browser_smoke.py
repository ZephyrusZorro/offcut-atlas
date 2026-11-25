"""Optional Chromium acceptance test. Run from the repository root.

    python -m pip install playwright
    python -m playwright install chromium
    python tests/browser_smoke.py [--executable PATH] [--screens PATH]
"""
import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atlas.ledger import Ledger
from atlas.server import Server
from atlas.worker import Worker


def require_fit(page):
    widths = page.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
    assert widths[0] <= widths[1], f"Horizontal page overflow: {widths}"


def exercise(browser, width, height, screens, studio):
    ledger = Ledger(studio / f"studio-{width}.sqlite")
    ledger.initialize()
    worker = Worker(ledger)
    server = Server(("127.0.0.1", 0), ledger, worker)
    worker.start()
    http = threading.Thread(target=server.serve_forever, daemon=True)
    http.start()
    base = f"http://127.0.0.1:{server.server_port}"
    context = browser.new_context(viewport={"width": width, "height": height},
                                  reduced_motion="reduce", locale="en-US")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        start = time.perf_counter()
        page.goto(base)
        expect(page.get_by_role("heading", name="Rail layout")).to_be_visible()
        first_render = int((time.perf_counter() - start) * 1000)
        require_fit(page)
        if screens:
            screens.mkdir(exist_ok=True, parents=True)
            page.screenshot(path=screens / f"cutting-desk-{width}.png")
        layouts = page.locator(".bar-row")
        expect(layouts.first).to_be_visible()
        layouts.nth(1).click()
        expect(page.locator(".inspect")).to_have_attribute("open", "")
        expect(page.locator(".inspect summary")).to_contain_text("Rail 02")
        page.get_by_text("Verification checks", exact=False).click()
        expect(page.get_by_text("Exact demand quantities", exact=True)).to_be_visible()

        page.get_by_role("link", name="Two-order replay").click()
        expect(page.locator(".policy")).to_have_count(2)
        page.locator("#length").fill("750")
        page.get_by_role("button", name="Compare policies").click()
        expect(page.locator(".policy")).to_have_count(2)
        require_fit(page)
        if screens:
            page.screenshot(path=screens / f"two-order-replay-{width}.png")
        page.get_by_role("button", name="Evaluate current setup").click()
        expect(page.locator("#joint-output")).to_contain_text("exceeds the joint search limit")
        page.get_by_role("button", name="Run worked example").click()
        expect(page.locator("#joint-output")).to_contain_text("Planning together saves 1 full rail")
        expect(page.locator("#joint-output")).to_contain_text("MAPLE-R")
        require_fit(page)
        if screens and width == 1440:
            page.locator("#lookahead").screenshot(path=screens / "two-order-lookahead.png")
        page.get_by_role("link", name="Cutting desk", exact=False).last.click()
        expect(page.get_by_role("heading", name="Rail layout")).to_be_visible()

        with page.expect_download() as download:
            page.get_by_role("link", name="Export packet").click()
        packet = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        assert packet["verification"]["valid"]

        page.get_by_role("button", name="Edit brief").click()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.get_by_role("button", name="Add part").click()
        page.locator(".editor-row").last.get_by_role("button").click()
        page.get_by_label("Order name").fill("Gallery proof")
        require_fit(page)
        page.get_by_role("button", name="Generate plan").click()
        expect(page.get_by_role("heading", name="Gallery proof")).to_be_visible()
        expect(page.get_by_role("heading", name="Rail layout")).to_be_visible()

        page.get_by_role("link", name="Stock ledger").click()
        page.get_by_role("button", name="Receive stock").click()
        page.get_by_role("dialog").get_by_label("Material", exact=True).fill("Wenge")
        page.get_by_label("Rail length (mm)").fill("2050")
        def lost_ack(route):
            response = route.fetch()
            assert response.ok
            route.abort()

        page.route("**/api/v1/stock", lost_ack, times=1)
        page.get_by_role("dialog").get_by_role("button", name="Receive stock").click()
        expect(page.locator(".form-error")).to_be_visible()
        page.get_by_role("dialog").get_by_role("button", name="Receive stock").click()
        expect(page.get_by_role("cell", name="Wenge")).to_have_count(1)
        page.locator("#stock-filter").select_option("remnant")
        expect(page.get_by_role("cell", name="Wenge")).to_have_count(0)
        require_fit(page)
        page.get_by_role("link", name="Cutting desk", exact=True).click()
        page.get_by_role("button", name="Apply to ledger").click()
        page.get_by_role("dialog").get_by_role("button", name="Cancel").click()
        page.get_by_role("button", name="Apply to ledger").click()
        page.get_by_role("dialog").get_by_role("button", name="Apply to ledger").click()
        expect(page.get_by_text("Applied to the stock ledger.", exact=True)).to_be_visible()
        page.get_by_role("link", name="Print cut sheet").click()
        expect(page.get_by_role("heading", name="Returned stock labels")).to_be_visible()
        require_fit(page)
        page.emulate_media(media="print")
        assert page.pdf(format="A4").startswith(b"%PDF")
        page.emulate_media(media="screen")
        page.get_by_role("link", name="Cutting desk").click()

        page.get_by_role("link", name="Plan history").click()
        page.get_by_role("button", name="Northlight exhibition").click()
        expect(page.locator(".stale")).to_be_visible()
        expect(page.get_by_role("button", name="Apply to ledger")).to_have_count(0)
        page.get_by_role("link", name="Activity log").click()
        expect(page.get_by_text("committed", exact=True)).to_be_visible()
        require_fit(page)

        page.route("**/api/v1/workspace", lambda route: route.abort())
        page.get_by_role("button", name="Refresh").click()
        expect(page.get_by_role("button", name="Retry")).to_be_visible()
        page.unroute("**/api/v1/workspace")
        page.get_by_role("button", name="Retry").click()
        expect(page.locator("#connection")).to_have_attribute("data-live", "true")
        assert not errors, errors
        print(f"{width}x{height}: drawing ready in {first_render} ms; "
              "plan/edit/intake-retry/replay/export/print/commit/conflict/history/retry passed.")
    finally:
        context.close()
        server.shutdown()
        http.join()
        server.server_close()
        worker.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--executable", type=Path)
    ap.add_argument("--screens", type=Path)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.executable, headless=True)
        try:
            for width, height in ((1440, 960), (390, 844)):
                exercise(browser, width, height, args.screens, Path(directory))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
