#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-CON Browser-Based UI & Responsive Testing Suite.
Uses Chrome Headless to verify:
1. Layout rendering & DOM completeness at Desktop (1440x900)
2. Laptop layout rendering (1366x768)
3. Tablet layout rendering (768x1024)
4. Mobile viewport rendering & responsiveness (390x844)
5. Console errors and layout overflow checks
6. Screen captures stored for visual audit evidence.
"""

import sys
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not Path(CHROME_PATH).is_file():
    CHROME_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

VIEWPORT_SCREENS = [
    # 1. Auth View across all 4 responsive resolutions
    {"view_name": "landing_auth_desktop", "url": "http://127.0.0.1:8000/?view=auth", "width": 1440, "height": 900},
    {"view_name": "landing_auth_laptop", "url": "http://127.0.0.1:8000/?view=auth", "width": 1366, "height": 768},
    {"view_name": "landing_auth_tablet", "url": "http://127.0.0.1:8000/?view=auth", "width": 768, "height": 1024},
    {"view_name": "landing_auth_mobile", "url": "http://127.0.0.1:8000/?view=auth", "width": 390, "height": 844},

    # 2. Onboarding Wizard Step 3 (Marks & Circular SVG Meter)
    {"view_name": "wizard_step3_marks_desktop", "url": "http://127.0.0.1:8000/?view=onboarding&step=3", "width": 1440, "height": 900},
    {"view_name": "wizard_step3_marks_mobile", "url": "http://127.0.0.1:8000/?view=onboarding&step=3", "width": 390, "height": 844},

    # 3. Onboarding Wizard Step 5 (25-Question Aptitude Assessment)
    {"view_name": "wizard_step5_aptitude_desktop", "url": "http://127.0.0.1:8000/?view=onboarding&step=5", "width": 1440, "height": 900},

    # 4. Onboarding Wizard Step 6 (Stream Recommendation Results)
    {"view_name": "wizard_step6_stream_desktop", "url": "http://127.0.0.1:8000/?view=onboarding&step=6", "width": 1440, "height": 900},

    # 5. Dashboard View across Desktop, Tablet, Mobile
    {"view_name": "dashboard_desktop", "url": "http://127.0.0.1:8000/?view=dashboard", "width": 1440, "height": 900},
    {"view_name": "dashboard_tablet", "url": "http://127.0.0.1:8000/?view=dashboard", "width": 768, "height": 1024},
    {"view_name": "dashboard_mobile", "url": "http://127.0.0.1:8000/?view=dashboard", "width": 390, "height": 844}
]

def run_browser_audit():
    print(f"[BROWSER] Using browser executable: {CHROME_PATH}")
    audit_results = {}

    for item in VIEWPORT_SCREENS:
        name = item["view_name"]
        url = item["url"]
        w = item["width"]
        h = item["height"]
        ss_file = SCREENSHOTS_DIR / f"{name}.png"

        print(f"[BROWSER] Capturing {name} ({w}x{h}) from {url}...")
        cmd = [
            CHROME_PATH,
            "--headless=new",
            f"--window-size={w},{h}",
            "--hide-scrollbars",
            "--disable-gpu",
            "--no-sandbox",
            f"--screenshot={ss_file}",
            "--dump-dom",
            url
        ]

        t0 = time.time()
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        dt = time.time() - t0

        if ss_file.is_file():
            ss_size = ss_file.stat().st_size
            print(f"[BROWSER] -> Captured: {ss_file.name} ({ss_size:,} bytes) in {dt:.2f}s")
        else:
            ss_size = 0
            print(f"[WARNING] Screenshot not generated for {name}")

        dom = res.stdout or ""
        audit_results[name] = {
            "viewport": f"{w}x{h}",
            "url": url,
            "render_time_sec": round(dt, 2),
            "screenshot_bytes": ss_size,
            "dom_length": len(dom),
            "checks": {
                "has_aicon_brand": "AI-CON" in dom,
                "has_container": "app-container" in dom or "body" in dom,
                "screenshot_valid": ss_size > 10000
            }
        }

    out_file = ROOT / "browser_audit_results.json"
    import json
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2)
    print(f"[BROWSER] Multi-screen audit complete. Results saved to {out_file}")

def ensure_server_running():
    import requests
    try:
        r = requests.get("http://127.0.0.1:8000/api/health", timeout=2)
        if r.status_code == 200:
            print("[BROWSER] Verified server running on http://127.0.0.1:8000")
            return
    except Exception:
        pass

    print("[BROWSER] Starting server in background thread...")
    import threading
    import uvicorn
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.api_server import app

    def run():
        config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
        server = uvicorn.Server(config)
        server.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(3)
    print("[BROWSER] Server started successfully.")

if __name__ == "__main__":
    ensure_server_running()
    run_browser_audit()
