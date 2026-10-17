# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Remember confirmed song playback per learner."""
from alembic import op
from sqlalchemy import Table

from schoolbookd.db.models import SongPlay

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 uses current metadata, so a fresh installation already has this table.
    table = SongPlay.__table__
    assert isinstance(table, Table)
    table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    table = SongPlay.__table__
    assert isinstance(table, Table)
    table.drop(op.get_bind(), checkfirst=True)
