#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.chromium_cdp import DEFAULT_CDP_PORT, DEFAULT_CDP_PROFILE, ensure_chromium_cdp  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Start or verify the local Chromium CDP session used by OSGE.")
    parser.add_argument("--port", type=int, default=DEFAULT_CDP_PORT)
    parser.add_argument("--profile-dir", default=str(DEFAULT_CDP_PROFILE))
    parser.add_argument("--headless", action="store_true", help="Start Chromium without a visible window.")
    args = parser.parse_args()

    status = ensure_chromium_cdp(
        port=args.port,
        profile_dir=args.profile_dir,
        headless=args.headless,
    )
    if not status.ok:
        raise SystemExit(f"CDP unavailable: {status.error}")

    print(f"CDP ready: {status.url}")
    print(f"Browser: {status.browser or 'unknown'}")
    print(f"Profile: {status.profile_dir}")
    print(f"Started now: {status.started}")


if __name__ == "__main__":
    main()
