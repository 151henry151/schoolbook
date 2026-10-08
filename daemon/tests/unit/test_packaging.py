# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import subprocess
from pathlib import Path


def test_dry_run_lists_the_lockdown_steps() -> None:
    script = Path("packaging/install.sh")
    completed = subprocess.run(["bash", str(script), "--dry-run"], check=True, capture_output=True, text=True)
    text = completed.stdout
    for phrase in (
        "mask ctrl-alt-del.target",
        "kernel.sysrq=0",
        "NAutoVTs=0",
        "URLBlocklist",
        "xdg-open stub",
        "udisks",
        "cage without -s",
        "disk encryption",
        "schoolbookd --check-config",
        "schoolbook-backup.timer",
    ):
        assert phrase in text
    policy = Path("packaging/chromium/policy.json").read_text(encoding="utf-8")
    assert '"URLBlocklist": ["*"]' in policy
    assert "DeveloperToolsAvailability" in policy
    greetd = Path("packaging/greetd/config.toml").read_text(encoding="utf-8")
    assert "cage -- schoolbook-session" in greetd
    assert " -s" not in greetd
