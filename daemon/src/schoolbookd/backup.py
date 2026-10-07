# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""restic command lines. The daemon builds them; it does not run them during tests."""

from __future__ import annotations

from pathlib import Path


def restic_backup_command(repository: str, paths: list[Path]) -> list[str]:
    if not repository.strip():
        raise ValueError("restic repository is required")
    if not paths:
        raise ValueError("backup needs at least one path")
    return ["restic", "-r", repository, "backup", *[str(path) for path in paths]]


def restic_restore_command(repository: str, target: Path) -> list[str]:
    if not repository.strip():
        raise ValueError("restic repository is required")
    return ["restic", "-r", repository, "restore", "latest", "--target", str(target)]
