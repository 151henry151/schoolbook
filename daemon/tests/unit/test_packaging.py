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
        "network-manager",
        "child Wi-Fi picker",
        "hide the GRUB menu",
    ):
        assert phrase in text
    boot = subprocess.run(
        ["bash", str(Path("packaging/kiosk-boot.sh")), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for phrase in (
        "NetworkManager",
        "hide the GRUB menu",
        "boot Debian 13 first",
        "autologin",
        "start Schoolbook",
    ):
        assert phrase in boot
    policy = Path("packaging/chromium/policy.json").read_text(encoding="utf-8")
    assert '"URLBlocklist": ["*"]' in policy
    assert "DeveloperToolsAvailability" in policy
    greetd = Path("packaging/greetd/config.toml").read_text(encoding="utf-8")
    assert "cage -- schoolbook-session" in greetd
    assert " -s" not in greetd
    xinitrc = Path("packaging/xinitrc").read_text(encoding="utf-8")
    assert "PULSE_SERVER=unix:/tmp/schoolbook-audio/pulse/native" in xinitrc
    assert "/root/.config/pulse/client.conf" in xinitrc
    assert "default-server = unix:/tmp/schoolbook-audio/pulse/native" in xinitrc
    assert 'rm -f "$PULSE_RUNTIME_PATH/native"' in xinitrc
    assert "pactl info" in xinitrc
    assert "pactl set-default-source" in xinitrc
    assert "alsa_input" in xinitrc
    assert "module-remap-source" in xinitrc
    assert "schoolbook-mic" in xinitrc
    assert "default-source" in xinitrc
    assert "PULSE_SOURCE" in xinitrc
    assert "Mic Boost" in xinitrc
    assert "pactl set-sink-volume" in xinitrc
    assert 'sset Master 100%' in xinitrc
    assert "exec /root/schoolbook/.venv/bin/schoolbook" not in xinitrc
