# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Update secrets.env without echoing values back to the console."""

from __future__ import annotations

from pathlib import Path


def upsert_secrets(path: Path, updates: dict[str, str]) -> None:
    current: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            current[key.strip()] = value
    for key, value in updates.items():
        current[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{key}={value}" for key, value in current.items()) + "\n"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
