"""
Banamex BancaNet MVP: capture a manually-triggered movements download.

Run once to validate three unknowns:
  1) Can Playwright catch the file BancaNet generates?
  2) What format/encoding/columns does it use?
  3) Does a persistent context skip login on a second run?

Login + 2FA + navigation happen manually in a headed browser. Credentials
from .env are auto-filled when the form is detected; if selectors don't
match, fill them by hand and continue.

Required .env keys:
    BANAMEX_LOGIN_URL=https://bancanet.banamex.com   # or current entry URL
    BANAMEX_USERNAME=...
    BANAMEX_PASSWORD=...

Setup:
    pip install playwright
    playwright install chromium
    python scripts/banamex_mvp.py
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import (
    Download,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

load_dotenv()

LOGIN_URL = os.getenv("BANAMEX_LOGIN_URL", "https://bancanet.banamex.com")
USERNAME = os.getenv("BANAMEX_USERNAME")
PASSWORD = os.getenv("BANAMEX_PASSWORD")

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "banamex_state"
DOWNLOAD_DIR = ROOT / "downloads"
DOWNLOAD_TIMEOUT_SEC = 10 * 60


def try_autofill_login(page: Page) -> None:
    """Best-effort autofill. BancaNet's DOM shifts; fall back to manual entry."""
    if not USERNAME or not PASSWORD:
        print("[autofill] BANAMEX_USERNAME/PASSWORD not set in .env — fill manually.")
        return

    user_selectors = [
        'input[name*="user" i]',
        'input[name*="usuario" i]',
        'input[id*="user" i]',
        'input[id*="usuario" i]',
    ]
    pass_selectors = [
        'input[type="password"]',
        'input[name*="pass" i]',
        'input[id*="pass" i]',
    ]

    filled_user = False
    for sel in user_selectors:
        try:
            page.locator(sel).first.fill(USERNAME, timeout=2000)
            print(f"[autofill] username filled via: {sel}")
            filled_user = True
            break
        except (PlaywrightTimeoutError, Exception):
            continue
    if not filled_user:
        print("[autofill] username field not found — fill manually.")

    filled_pass = False
    for sel in pass_selectors:
        try:
            page.locator(sel).first.fill(PASSWORD, timeout=2000)
            print(f"[autofill] password filled via: {sel}")
            filled_pass = True
            break
        except (PlaywrightTimeoutError, Exception):
            continue
    if not filled_pass:
        print("[autofill] password field not found — fill manually.")


def describe_download(path: Path, suggested_name: str) -> None:
    size = path.stat().st_size
    with open(path, "rb") as f:
        head_bytes = f.read(2048)

    encoding = "unknown"
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            head_bytes.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue

    print()
    print("=" * 64)
    print("Download captured")
    print("=" * 64)
    print(f"  saved to:        {path}")
    print(f"  suggested name:  {suggested_name}")
    print(f"  size:            {size} bytes")
    print(f"  sniffed encoding: {encoding}")
    print()
    print("--- first ~2KB ---")
    if encoding != "unknown":
        print(head_bytes.decode(encoding, errors="replace"))
    else:
        print(repr(head_bytes[:512]))
    print("--- end ---")


def main() -> int:
    STATE_DIR.mkdir(exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    downloads_seen: list[Download] = []

    def on_download(d: Download) -> None:
        print(f"[event] download fired: {d.suggested_filename}")
        downloads_seen.append(d)

    def attach_listeners(p: Page) -> None:
        p.on("download", on_download)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(STATE_DIR),
            headless=False,
            accept_downloads=True,
        )

        # BancaNet may open the download in a popup — listen on every page.
        ctx.on("page", lambda new_page: attach_listeners(new_page))
        for existing in ctx.pages:
            attach_listeners(existing)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print(f"[nav] opening {LOGIN_URL}")
        page.goto(LOGIN_URL)

        try_autofill_login(page)

        print()
        print("=" * 64)
        print("MANUAL STEP")
        print("=" * 64)
        print("  1. Submit login + complete 2FA in the browser.")
        print("  2. Navigate to 'Descargar movimientos' (or equivalent).")
        print("  3. Trigger the download.")
        print(f"  Timeout: {DOWNLOAD_TIMEOUT_SEC // 60} minutes.")
        print("=" * 64)
        print()

        start = time.time()
        while not downloads_seen:
            if time.time() - start > DOWNLOAD_TIMEOUT_SEC:
                print("[error] no download within timeout — exiting.")
                ctx.close()
                return 1
            page.wait_for_timeout(500)

        download = downloads_seen[0]
        suggested = download.suggested_filename
        target = DOWNLOAD_DIR / suggested
        download.save_as(str(target))
        describe_download(target, suggested)

        if len(downloads_seen) > 1:
            print(f"\n[note] {len(downloads_seen) - 1} extra download(s) seen; only first saved.")

        input("\nPress Enter to close the browser...")
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
