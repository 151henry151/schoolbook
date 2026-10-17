# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Engine, migrations, and the pre-migration backup."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from schoolbookd.db.models import Base


def make_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def backup_database(database_path: Path, backups_dir: Path) -> Path | None:
    if not database_path.is_file():
        return None
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
    dest = backups_dir / f"schoolbook-{stamp}.db"
    shutil.copy2(database_path, dest)
    return dest


def migrate(engine: Engine) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(config, "head")


def expected_tables() -> set[str]:
    return set(Base.metadata.tables)
