"""
Banamex BancaNet MVP via CDP attach: bypass automation detection by
piggybacking on a real Chrome that you launch and log into manually.

Why this exists:
    Banamex blocks Playwright's bundled Chromium on sight. Connecting to a
    real Chrome via DevTools Protocol presents essentially zero automation
    fingerprint because it *is* a real user browser.

How to run:
    1. Quit your normal Chrome (or use a separate user-data-dir, below).
    2. Launch Chrome with remote debugging enabled. macOS example:

        /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
            --remote-debugging-port=9222 \\
            --user-data-dir="$HOME/banamex_chrome_profile"

       The separate --user-data-dir keeps this isolated from your daily
       Chrome profile so both can run side-by-side.

    3. In that Chrome window: go to BancaNet, log in like a human.
    4. In a separate terminal:  python scripts/banamex_mvp_cdp.py
    5. Back in Chrome: navigate to 'Descargar movimientos', trigger the
       download. The script catches and describes the file.

Required .env keys:
    BANAMEX_CDP_URL=http://localhost:9222   # optional; default shown
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import Download, Page, sync_playwright

load_dotenv()

CDP_URL = os.getenv("BANAMEX_CDP_URL", "http://localhost:9222")

ROOT = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = ROOT / "downloads"
DOWNLOAD_TIMEOUT_SEC = 10 * 60


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
    print(f"  saved to:         {path}")
    print(f"  suggested name:   {suggested_name}")
    print(f"  size:             {size} bytes")
    print(f"  sniffed encoding: {encoding}")
    print()
    print("--- first ~2KB ---")
    if encoding != "unknown":
        print(head_bytes.decode(encoding, errors="replace"))
    else:
        print(repr(head_bytes[:512]))
    print("--- end ---")


def main() -> int:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    downloads_seen: list[Download] = []

    def on_download(d: Download) -> None:
        print(f"[event] download fired: {d.suggested_filename}")
        downloads_seen.append(d)

    def attach_listeners(p: Page) -> None:
        p.on("download", on_download)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"[error] could not connect to Chrome at {CDP_URL}: {e}")
            print("  Is Chrome running with --remote-debugging-port=9222 ?")
            return 1

        print(f"[ok] connected to Chrome via CDP at {CDP_URL}")
        contexts = browser.contexts
        print(f"[info] found {len(contexts)} browser context(s)")

        if not contexts:
            print("[warn] no contexts found — open at least one tab in Chrome.")
            return 1

        # Attach to every existing page and any new page in any context.
        # Banamex often pops the download in a fresh tab/window.
        for ctx in contexts:
            ctx.on("page", lambda p: attach_listeners(p))
            for page in ctx.pages:
                attach_listeners(page)
                print(f"[info] watching page: {page.url[:80]}")

        print()
        print("=" * 64)
        print("Waiting for download...")
        print("=" * 64)
        print("  In Chrome: navigate to 'Descargar movimientos' and trigger")
        print(f"  the download. Timeout: {DOWNLOAD_TIMEOUT_SEC // 60} minutes.")
        print("=" * 64)
        print()

        start = time.time()
        while not downloads_seen:
            if time.time() - start > DOWNLOAD_TIMEOUT_SEC:
                print("[error] no download within timeout — exiting.")
                return 1
            time.sleep(0.5)

        download = downloads_seen[0]
        suggested = download.suggested_filename
        target = DOWNLOAD_DIR / suggested
        try:
            download.save_as(str(target))
            describe_download(target, suggested)
        except Exception as e:
            # When attached to real Chrome, save_as can fail because Chrome's
            # own download manager already wrote the file. Tell the user where.
            print(f"[warn] save_as failed ({e}). Check Chrome's default")
            print(f"       downloads folder for: {suggested}")

        if len(downloads_seen) > 1:
            print(f"\n[note] {len(downloads_seen) - 1} extra download(s) seen; only first handled.")

        # Do NOT call browser.close() — it would close the user's real Chrome.
        # Exiting the sync_playwright() context disconnects cleanly.
        print("\n[done] disconnected from Chrome (window stays open).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
