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


def test_song_history_upgrade_preserves_existing_data(tmp_path: Path) -> None:
    from sqlalchemy import text

    engine = make_engine(tmp_path / "schoolbook.db")
    migrate(engine)
    with engine.begin() as db:
        db.execute(text("DROP TABLE song_plays"))
        db.execute(text("UPDATE alembic_version SET version_num = '0001'"))
        db.execute(text("INSERT INTO settings (key, value_json) VALUES ('keep', '42')"))
    migrate(engine)
    assert "song_plays" in inspect(engine).get_table_names()
    with engine.connect() as db:
        assert db.scalar(text("SELECT value_json FROM settings WHERE key = 'keep'")) == "42"


def test_video_history_upgrade_preserves_prior_song_history_schema(tmp_path: Path) -> None:
    from sqlalchemy import text

    engine = make_engine(tmp_path / 'schoolbook.db')
    migrate(engine)
    with engine.begin() as db:
        db.execute(text('DROP TABLE video_watches'))
        db.execute(text("UPDATE alembic_version SET version_num = '0002'"))
        db.execute(text("INSERT INTO settings (key, value_json) VALUES ('keep', '42')"))
    migrate(engine)
    assert {'video_watches', 'song_plays'} <= set(inspect(engine).get_table_names())
    with engine.connect() as db:
        assert db.scalar(text("SELECT value_json FROM settings WHERE key = 'keep'")) == '42'


def test_selection_upgrade_preserves_watches_without_inventing_selections(tmp_path: Path):
    from sqlalchemy import text

    from schoolbookd.db.models import Video
    from schoolbookd.db.engine import session_factory
    from schoolbookd.db.store import Store

    engine = make_engine(tmp_path / 'schoolbook.db')
    migrate(engine)
    store = Store(session_factory(engine))
    store.upsert_learner(learner_id='kid', first_name='Arum', birth_year=2020)
    store.save_video(Video(id='oldvideo123', source='youtube', source_ref='oldvideo123',
                           title='Snake history', verdict='approved', times_played=10))
    store.record_video_watch('kid', 'oldvideo123')
    with engine.begin() as db:
        db.execute(text('DROP TABLE video_selections'))
        db.execute(text("UPDATE alembic_version SET version_num = '0004'"))
    migrate(engine)
    assert store.selected_video_ids('kid') == {'oldvideo123'}
    history = store.video_selection_history('kid')
    assert history[0]['watch_count'] == 1
    assert history[0]['selection_count'] == 0  # Global play counts cannot identify the learner.
    assert store.video('oldvideo123').times_played == 10
