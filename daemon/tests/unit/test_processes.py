# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
import sys
import time

from schoolbookd.content.processes import AppProcesses, executable


def test_debian_games_path_is_searched(monkeypatch):
    seen = []
    monkeypatch.setenv('PATH', '/usr/bin')
    monkeypatch.setattr('schoolbookd.content.processes.shutil.which',
                        lambda name, path: seen.append(path) or '/usr/games/gcompris-qt')
    assert executable('gcompris-qt') == '/usr/games/gcompris-qt'
    assert seen == ['/usr/bin:/usr/games']


def test_process_exit_is_reaped_and_killing_finished_process_is_harmless():
    apps = AppProcesses()
    pid = apps.launch([sys.executable, '-c', 'pass'])
    deadline = time.monotonic() + 3
    while apps.running(pid) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not apps.running(pid)
    assert pid not in apps.children
    apps.kill(pid)
