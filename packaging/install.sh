#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

say() {
  printf 'schoolbook install: %s\n' "$1"
}

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    say "would run: $*"
  else
    "$@"
  fi
}

if [[ "$DRY_RUN" != "1" && "${EUID}" -ne 0 ]]; then
  echo "schoolbook install: re-run with sudo, or pass --dry-run" >&2
  exit 1
fi

say "install greetd cage chromium pipewire grim gcompris tuxpaint"
run id schoolbook >/dev/null 2>&1 || run useradd --system --home /var/lib/schoolbook --shell /usr/sbin/nologin schoolbook
run id kid >/dev/null 2>&1 || run useradd --create-home --shell /usr/sbin/nologin kid
say "write /etc/schoolbook, systemd units, greetd, chromium policy, polkit, logind, sysctl"
say "prompt for the parent password, child name, and API keys"
say "run schoolbookd --check-config and schoolbookd --self-test"
say "done"
