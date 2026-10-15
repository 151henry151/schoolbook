# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Exercise the real Openbox binding on an isolated display, never the live kiosk."""

import os
import select
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(
    any(shutil.which(name) is None for name in ("Xvfb", "openbox", "xdotool", "xmessage", "xprop")),
    reason="optional X11 integration tools are not installed",
)
def test_f11_restarts_only_kiosk_even_with_frozen_foreground_client(tmp_path: Path) -> None:
    trace = tmp_path / "restart-args"
    systemctl = tmp_path / "systemctl"
    systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$RESTART_TRACE"\n')
    systemctl.chmod(0o755)
    read_fd, write_fd = os.pipe()
    processes: list[subprocess.Popen[bytes]] = []
    client: subprocess.Popen[bytes] | None = None
    wm_log = (tmp_path / "openbox.log").open("wb")
    try:
        xvfb = subprocess.Popen(
            ["Xvfb", "-displayfd", str(write_fd), "-screen", "0", "1024x768x24", "-nolisten", "tcp"],
            pass_fds=(write_fd,),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(xvfb)
        os.close(write_fd)
        write_fd = -1
        assert select.select([read_fd], [], [], 5)[0], "Xvfb did not start"
        display = ":" + os.read(read_fd, 64).decode().strip()
        env = {
            **os.environ,
            "DISPLAY": display,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "RESTART_TRACE": str(trace),
        }
        processes.append(
            subprocess.Popen(
                ["openbox", "--config-file", str(Path("packaging/openbox/rc.xml").resolve())],
                env=env,
                stdout=wm_log,
                stderr=wm_log,
            )
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            wm = subprocess.check_output(["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"], env=env)
            if b"window id" in wm:
                break
            time.sleep(0.02)
        else:
            pytest.fail("Openbox did not start: " + (tmp_path / "openbox.log").read_text())
        client = subprocess.Popen(
            ["xmessage", "-name", "FrozenSchoolbookTest", "test"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(client)
        window = (
            subprocess.check_output(
                ["xdotool", "search", "--sync", "--name", "FrozenSchoolbookTest"],
                env=env,
                timeout=5,
            )
            .decode()
            .splitlines()[0]
        )
        subprocess.run(["xdotool", "windowactivate", "--sync", window], env=env, check=True, timeout=5)
        client.send_signal(signal.SIGSTOP)
        subprocess.run(["xdotool", "key", "F11"], env=env, check=True, timeout=5)
        deadline = time.monotonic() + 3
        while not trace.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert trace.read_text().splitlines() == ["--no-block", "restart", "schoolbook-kiosk.service"]
    finally:
        if client is not None and client.poll() is None:
            client.send_signal(signal.SIGCONT)
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)
        wm_log.close()
