# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Launch allowlisted apps and reap them when the child leaves an activity."""

from __future__ import annotations

import os
import shutil
import subprocess


def executable(name: str) -> str | None:
    # Debian places educational games outside root/systemd's usual PATH.
    return shutil.which(name, path=os.environ.get('PATH', os.defpath) + ':/usr/games')


class AppProcesses:
    def __init__(self) -> None:
        self.children: dict[int, subprocess.Popen[bytes]] = {}

    def launch(self, argv: list[str]) -> int:
        program = executable(argv[0])
        if program is None:
            raise FileNotFoundError(argv[0])
        process = subprocess.Popen([program, *argv[1:]], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        self.children[process.pid] = process
        return process.pid

    def running(self, pid: int) -> bool:
        process = self.children.get(pid)
        if process is not None and process.poll() is None:
            return True
        self.children.pop(pid, None)
        return False

    def kill(self, pid: int) -> None:
        process = self.children.pop(pid, None)
        if process is None or process.poll() is not None:
            return
        process.terminate()
        # Reap without blocking speech/UI callbacks on process shutdown.
        import threading

        def reap() -> None:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        threading.Thread(target=reap, daemon=True).start()
