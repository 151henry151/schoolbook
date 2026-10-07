# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Run the session agent over stdin JSON lines, or as a cage kiosk child."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from schoolbook_session.agent import handle_line
from schoolbook_session.kiosk import KioskError, find_chromium, run_chromium_kiosk


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="schoolbook-session")
    parser.add_argument("--allowlist", type=Path)
    sub = parser.add_subparsers(dest="command")
    kiosk = sub.add_parser("kiosk", help="start Chromium in kiosk mode")
    kiosk.add_argument("--url", required=True)
    kiosk.add_argument("--data-dir", type=Path, required=True)
    kiosk.add_argument("--chromium")
    args = parser.parse_args(argv)
    if args.command == "kiosk":
        try:
            chromium = args.chromium or find_chromium()
            run_chromium_kiosk(args.url, args.data_dir, chromium=chromium)
        except KioskError as exc:
            print(f"schoolbook-session: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.allowlist is None:
        parser.error("--allowlist is required")
    names = {
        line.strip()
        for line in args.allowlist.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            result = handle_line(line, names)
        except Exception as exc:
            result = {"type": "error", "message": str(exc)}
        print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
