# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Record per-response speech and transcription usage counters."""
from alembic import op
from sqlalchemy import Table

from schoolbookd.db.models import ApiUsage

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = ApiUsage.__table__
    assert isinstance(table, Table)
    table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    table = ApiUsage.__table__
    assert isinstance(table, Table)
    table.drop(op.get_bind(), checkfirst=True)
