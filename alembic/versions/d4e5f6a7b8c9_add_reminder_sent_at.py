"""add_reminder_sent_at

Revision ID: d4e5f6a7b8c9
Revises: c3f2e1b4d5a6
Create Date: 2026-02-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3f2e1b4d5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('appointments', sa.Column('reminder_sent_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('appointments', 'reminder_sent_at')
