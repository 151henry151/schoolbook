# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Remember videos watched at least halfway, separately from song history."""
from alembic import op
from sqlalchemy import Table

from schoolbookd.db.models import VideoWatch

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = VideoWatch.__table__
    assert isinstance(table, Table)
    table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    table = VideoWatch.__table__
    assert isinstance(table, Table)
    table.drop(op.get_bind(), checkfirst=True)
