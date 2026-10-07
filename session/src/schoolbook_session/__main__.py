# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Run the session agent over stdin JSON lines. Used by tests and by the socket server."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from schoolbook_session.agent import handle_line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="schoolbook-session")
    parser.add_argument("--allowlist", type=Path, required=True)
    args = parser.parse_args(argv)
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
