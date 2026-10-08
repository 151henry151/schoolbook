# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""App manifests. The command line is built from the file, never from model text."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    skills: list[str] = Field(default_factory=list)
    ages: list[int] = Field(default_factory=list)


class AppManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    exec: list[str] = Field(min_length=1)
    activity_arg: list[str] = Field(default_factory=list)
    level_arg: list[str] = Field(default_factory=list)
    observe: bool = False
    activities: list[Activity] = Field(default_factory=list)


def load_manifests(directory: Path) -> dict[str, AppManifest]:
    found: dict[str, AppManifest] = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        manifest = AppManifest.model_validate(raw)
        found[manifest.id] = manifest
    return found


def build_argv(
    manifest: AppManifest,
    activity: str | None = None,
    level: int | None = None,
) -> list[str]:
    argv = list(manifest.exec)
    if activity is not None:
        known = {item.id for item in manifest.activities}
        if activity not in known:
            raise ValueError(f"activity {activity} is not in {manifest.id}")
        argv.extend(part.format(activity=activity) for part in manifest.activity_arg)
    if level is not None:
        argv.extend(part.format(level=level) for part in manifest.level_arg)
    return argv
