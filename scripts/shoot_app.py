"""Web-agent screenshotter: drives the live Vercel app and saves a screenshot per route into
generated_app_images/, named after the link. Uses the system Chrome (channel='chrome')."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://forge-sight-one.vercel.app"
OUT = Path(__file__).resolve().parents[1] / "generated_app_images"
OUT.mkdir(exist_ok=True)

ENG_EMAIL = "engineer@demo.forgesight"
ENG_PASS = "forgesight-demo"

# (route, filename) — public first, then protected (after login)
PUBLIC = [("/", "home"), ("/login", "login"), ("/signup", "signup")]
PROTECTED = [
    ("/dashboard", "dashboard"),
    ("/dashboard/evidence", "dashboard-evidence"),
    ("/dashboard/work-orders", "dashboard-work-orders"),
    ("/dashboard/incidents", "dashboard-incidents"),
    ("/dashboard/spares", "dashboard-spares"),
    ("/dashboard/reliability", "dashboard-reliability"),
    ("/dashboard/leadership", "dashboard-leadership"),
    ("/dashboard/twin", "dashboard-twin"),
    ("/equipment/sinter-fan-2", "equipment-sinter-fan-2"),
    ("/equipment/hsm-f3-stand", "equipment-hsm-f3-stand"),
]

manifest: list[str] = []


def shot(page, route: str, name: str, settle: int = 3500):
    url = BASE + route
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(settle)
    fp = OUT / f"{name}.png"
    page.screenshot(path=str(fp), full_page=True)
    manifest.append(f"{fp.name}  <-  {url}")
    print(f"  shot {fp.name}  ({url})")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()

        print("public routes…")
        for route, name in PUBLIC:
            shot(page, route, name)

        print("logging in as engineer…")
        page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        page.fill("input[type=email]", ENG_EMAIL)
        page.fill("input[type=password]", ENG_PASS)
        page.get_by_role("button", name="Log in").click()
        try:
            page.wait_for_url("**/dashboard", timeout=30000)
        except Exception:
            page.wait_for_timeout(4000)
        page.wait_for_timeout(2000)
        print(f"  logged in, url={page.url}")

        print("protected routes…")
        for route, name in PROTECTED:
            shot(page, route, name, settle=4000)

        # bonus: a live diagnosis card in the copilot on the fan page
        try:
            print("capturing a live copilot diagnosis…")
            page.goto(BASE + "/equipment/sinter-fan-2", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            box = page.get_by_placeholder("Ask the maintenance copilot…")
            box.fill("What's causing the DE bearing vibration on the sinter ID fan?")
            box.press("Enter")
            page.wait_for_timeout(14000)  # let the governed pipeline + Groq synthesis return
            fp = OUT / "equipment-sinter-fan-2-diagnosis.png"
            page.screenshot(path=str(fp), full_page=True)
            manifest.append(f"{fp.name}  <-  {BASE}/equipment/sinter-fan-2 (copilot diagnosis)")
            print(f"  shot {fp.name}")
        except Exception as e:  # noqa: BLE001
            print(f"  (copilot capture skipped: {e})")

        ctx.close()
        browser.close()

    (OUT / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"\nwrote {len(manifest)} screenshots + manifest.txt to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
