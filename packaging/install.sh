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

say "install packages: greetd cage chromium pipewire grim piper gcompris tuxpaint kturtle stellarium marble"
say "create schoolbook system user and kid account in audio, video, and schoolbook-ui"
run id schoolbook >/dev/null 2>&1 || run useradd --system --home /var/lib/schoolbook --shell /usr/sbin/nologin schoolbook
run id kid >/dev/null 2>&1 || run useradd --create-home --groups audio,video --shell /usr/sbin/nologin kid
say "mask ctrl-alt-del.target"
say "set kernel.sysrq=0"
say "set NAutoVTs=0 and ReserveVT=0"
say "install chromium managed policy with URLBlocklist and DeveloperToolsAvailability 2"
say "install xdg-open stub for kid"
say "install polkit rule denying udisks mounts for kid"
say "install greetd autologin cage without -s"
say "offer Xorg and Openbox fallback when Wayland misbehaves"
say "ask disk encryption: tpm, partial, or none"
say "prompt for the parent password, child first name, birth year, Anthropic key, YouTube key, STT, and TTS"
say "write /etc/schoolbook/schoolbook.yaml and secrets.env mode 0600"
say "enable schoolbook-backup.timer"
say "run schoolbookd --check-config and schoolbookd --self-test"
say "reboot into the kiosk"
say "done"
