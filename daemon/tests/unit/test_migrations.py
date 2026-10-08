# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from sqlalchemy import inspect

from schoolbookd.db.engine import backup_database, expected_tables, make_engine, migrate


def test_upgrade_creates_spec_tables(tmp_path: Path) -> None:
    database = tmp_path / "schoolbook.db"
    engine = make_engine(database)
    migrate(engine)
    names = set(inspect(engine).get_table_names())
    assert expected_tables() <= names
    for required in (
        "learners",
        "sessions",
        "turns",
        "tool_calls",
        "skills",
        "skill_states",
        "observations",
        "interests",
        "notes",
        "videos",
        "video_tags",
        "video_skills",
        "images",
        "content_requests",
        "flags",
        "settings",
        "audit_log",
    ):
        assert required in names


def test_migrate_copies_an_existing_database_first(tmp_path: Path) -> None:
    database = tmp_path / "schoolbook.db"
    engine = make_engine(database)
    migrate(engine)
    original = database.read_bytes()
    backup = backup_database(database, tmp_path / "backups")
    assert backup is not None
    assert backup.read_bytes() == original
    migrate(engine)
    assert "learners" in inspect(engine).get_table_names()
