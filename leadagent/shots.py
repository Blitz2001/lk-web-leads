"""Optional: screenshot each prospect's site as it looks on a phone (free, uses Playwright).

A 'this is how your site looks on a phone today' picture is the strongest thing you can attach
to a WhatsApp pitch. Install once:  pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

import os
from pathlib import Path


def _launch(p):
    """Try: LEADAGENT_CHROME path → Playwright's own Chromium → installed Google Chrome → Microsoft Edge."""
    attempts = []
    if os.environ.get("LEADAGENT_CHROME"):
        attempts.append({"executable_path": os.environ["LEADAGENT_CHROME"]})
    attempts += [{}, {"channel": "chrome"}, {"channel": "msedge"}]
    for kw in attempts:
        try:
            return p.chromium.launch(**kw)
        except Exception:
            continue
    return None


def capture(targets: list[tuple[str, str]], out_dir: str) -> dict[str, str]:
    """targets: [(lead_id, url)] → {lead_id: relative image path (from out_dir)}"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("! screenshots need Playwright:  pip install playwright && python -m playwright install chromium")
        return {}
    shots = Path(out_dir) / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    done: dict[str, str] = {}
    with sync_playwright() as p:
        browser = _launch(p)
        if browser is None:
            print("! couldn't start a browser. Install Google Chrome, or run:  python -m playwright install chromium")
            return {}
        ctx = browser.new_context(**p.devices["iPhone 13"])
        page = ctx.new_page()
        for lid, url in targets:
            path = shots / f"{lid}.png"
            try:
                page.goto(url, timeout=30000, wait_until="load")
                page.wait_for_timeout(1500)
                page.screenshot(path=str(path))
                done[lid] = f"shots/{lid}.png"
                print(f"  📱 {url}")
            except Exception:
                continue
        browser.close()
    return done
