#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
set -euo pipefail
export LANG="${LANG:-en_US.UTF-8}"
root="${SCHOOLBOOK_ROOT:-/root/schoolbook}"
# Prefer the real binary so Debian's wrapper cannot move --kiosk after the URL.
export PATH="/usr/lib/chromium:$root/.venv/bin:$HOME/.local/bin:$PATH"
export SCHOOLBOOK_DISABLE_GPU="${SCHOOLBOOK_DISABLE_GPU:-1}"
export SCHOOLBOOK_NO_CAGE=1
cd "$root"
if [[ "${SCHOOLBOOK_USE_CAGE:-0}" == "1" ]]; then
  exec "$root/.venv/bin/schoolbook" "$@"
fi
exec startx "$root/packaging/xinitrc" -- :0
