"""Web-agent: capture one screenshot per agent response from the live copilot. Logs in, then for
each prompt reloads the equipment page (fresh copilot) → sends the prompt → waits for the governed
pipeline to finish → screenshots. Saves into generated_app_images/ named by agent/card."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://forge-sight-one.vercel.app"
EQ = "/equipment/sinter-fan-2"
OUT = Path(__file__).resolve().parents[1] / "generated_app_images"
OUT.mkdir(exist_ok=True)
ENG_EMAIL, ENG_PASS = "engineer@demo.forgesight", "forgesight-demo"

# (filename, prompt) — one per agent / card type
PROMPTS = [
    ("agent-diagnostic-diagnosis", "What's causing the DE bearing vibration on the sinter ID fan?"),
    ("agent-diagnostic-checklist", "Give me the step-by-step LOTO procedure to replace the DE bearing safely."),
    ("agent-reliability-rul", "How many days of life are left on this fan before it trips?"),
    ("agent-reliability-wait", "Can it wait until Sunday's shutdown?"),
    ("agent-supervisor-priority", "What's the maintenance priority for this fan, and how urgent is it?"),
    ("agent-planner-spares", "Do we have the replacement DE bearing in stock, and what's the lead time?"),
    ("agent-analyst-sql", "Which equipment has had the most downtime?"),
]

manifest: list[str] = []


def capture(page, name: str, prompt: str):
    page.goto(BASE + EQ, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)
    box = page.get_by_placeholder("Ask the maintenance copilot…")
    box.fill(prompt)
    box.press("Enter")
    # wait for the governed pipeline: busy indicator appears, then disappears when the card is ready
    try:
        page.get_by_text("Running governed pipeline").wait_for(state="visible", timeout=8000)
    except Exception:
        pass
    try:
        page.get_by_text("Running governed pipeline").wait_for(state="hidden", timeout=40000)
    except Exception:
        pass
    page.wait_for_timeout(2500)
    fp = OUT / f"{name}.png"
    page.screenshot(path=str(fp), full_page=True)
    manifest.append(f"{fp.name}  <-  {BASE}{EQ}  |  prompt: {prompt}")
    print(f"  shot {fp.name}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()

        print("logging in…")
        page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        page.fill("input[type=email]", ENG_EMAIL)
        page.fill("input[type=password]", ENG_PASS)
        page.get_by_role("button", name="Log in").click()
        try:
            page.wait_for_url("**/dashboard", timeout=30000)
        except Exception:
            page.wait_for_timeout(4000)
        print(f"  logged in, url={page.url}")

        for name, prompt in PROMPTS:
            print(f"agent prompt: {name}")
            try:
                capture(page, name, prompt)
            except Exception as e:  # noqa: BLE001
                print(f"  (failed: {e})")

        ctx.close()
        browser.close()

    (OUT / "agent_manifest.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"\nwrote {len(manifest)} agent screenshots + agent_manifest.txt")


if __name__ == "__main__":
    sys.exit(main())
