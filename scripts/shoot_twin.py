"""Screenshot the live 3D digital-twin page (overview + deep-linked inspector). Headless Chrome
with software WebGL (SwiftShader) so the three.js canvas renders."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://forge-sight-one.vercel.app"
OUT = Path(__file__).resolve().parents[1] / "generated_app_images"
ENG_EMAIL, ENG_PASS = "engineer@demo.forgesight", "forgesight-demo"
GL_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
           "--ignore-gpu-blocklist", "--enable-webgl"]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=GL_ARGS)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()

        print("login…")
        page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
        page.fill("input[type=email]", ENG_EMAIL)
        page.fill("input[type=password]", ENG_PASS)
        page.get_by_role("button", name="Log in").click()
        try:
            page.wait_for_url("**/dashboard", timeout=30000)
            page.get_by_role("button", name="Logout").wait_for(timeout=15000)  # session established
        except Exception:
            page.wait_for_timeout(5000)
        page.wait_for_timeout(2500)
        print(f"  logged in, url={page.url}")

        shots = [("/dashboard/twin", "twin-3d"),
                 ("/dashboard/twin?asset=sinter-fan-2", "twin-3d-inspect")]
        for route, name in shots:
            print(f"capture {name}…")
            page.goto(BASE + route, wait_until="domcontentloaded", timeout=45000)
            try:  # wait for the loader to vanish
                page.get_by_text("Loading 3D plant twin").wait_for(state="hidden", timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(6000)  # let r3f render the scene + shadows
            fp = OUT / f"{name}.png"
            page.screenshot(path=str(fp), full_page=False)
            print(f"  shot {fp.name}")

        ctx.close()
        browser.close()
    print("done")


if __name__ == "__main__":
    sys.exit(main())
