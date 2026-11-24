"""Screenshot the Metabase dashboard into docs/img/dashboard.png with headless Chrome/Edge.

    python scripts/dashboard_screenshot.py     # make dashboard-screenshot

Runs scripts/metabase_setup.py --public to get a public (login-free) link, then renders it in a throwaway
browser profile. The browser is found on PATH or in the usual Windows/macOS/Linux install locations.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/img/dashboard.png"
CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
]


def find_browser() -> str:
    for c in CANDIDATES:
        path = shutil.which(c) or (c if Path(c).exists() else None)
        if path:
            return path
    raise SystemExit("no Chrome/Edge/Chromium found")


def main() -> int:
    setup = subprocess.run(
        [sys.executable, str(ROOT / "scripts/metabase_setup.py"), "--public"],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    url = json.loads(setup.stdout.strip().splitlines()[-1])["public_url"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                find_browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                "--window-size=1600,1640", "--virtual-time-budget=60000", "--run-all-compositor-stages-before-draw",
                f"--screenshot={OUT}", url,
            ],
            check=True, capture_output=True,
        )  # fmt: skip
    print(f"wrote {OUT.relative_to(ROOT)} from {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
