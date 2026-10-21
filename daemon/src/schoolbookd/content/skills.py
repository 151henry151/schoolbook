# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Load the shipped skills tree."""

from __future__ import annotations

from pathlib import Path

import yaml

from schoolbookd.db.models import Skill


def load_skill_rows(path: Path, source: str = "core") -> list[Skill]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows: list[Skill] = []

    def walk(nodes: list[dict[str, object]], parent: str | None) -> None:
        for node in nodes:
            skill_id = str(node["id"])
            rows.append(
                Skill(
                    id=skill_id,
                    parent_id=parent,
                    title=str(node["title"]),
                    kid_description=str(node.get("kid_description", "")),
                    age_min=int(str(node.get("age_min", 4))),
                    age_max=int(str(node.get("age_max", 8))),
                    source=source,
                )
            )
            children = node.get("children", [])
            if isinstance(children, list):
                walk(children, skill_id)

    walk(list(raw["skills"]), None)
    return rows
