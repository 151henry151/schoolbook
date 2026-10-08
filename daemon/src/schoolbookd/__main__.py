# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""schoolbookd command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from schoolbookd.config import ConfigError, check_config, explain_startup, load_config, load_secrets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="schoolbookd")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("command", nargs="?", choices=["serve"])
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        for error in exc.errors:
            print(f"schoolbookd: invalid config: {error}", file=sys.stderr)
        return 1
    secrets = load_secrets(config.secrets_file)
    if args.check_config:
        errors = check_config(config)
        if errors:
            for error in errors:
                print(f"schoolbookd: {error}", file=sys.stderr)
            return 1
        print("schoolbookd: config ok")
        return 0
    errors = explain_startup(config, secrets)
    if errors and (args.command == "serve" or args.self_test):
        for error in errors:
            print(f"schoolbookd: {error}", file=sys.stderr)
        return 1
    if args.self_test:
        from schoolbookd.selftest import run_self_test

        return run_self_test(config, secrets)
    if args.command == "serve":
        from schoolbookd.server import serve

        serve(config, secrets)
        return 0
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
