# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Remember selections without counting them as half-watched videos."""
from alembic import op
from sqlalchemy import Table

from schoolbookd.db.models import VideoSelection

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = VideoSelection.__table__
    assert isinstance(table, Table)
    table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    table = VideoSelection.__table__
    assert isinstance(table, Table)
    table.drop(op.get_bind(), checkfirst=True)
