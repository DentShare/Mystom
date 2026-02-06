"""add_service_duration

Revision ID: c3f2e1b4d5a6
Revises: bac78a7d1a7d
Create Date: 2026-02-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3f2e1b4d5a6'
down_revision: Union[str, None] = 'bac78a7d1a7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('services', sa.Column('duration_minutes', sa.Integer(), nullable=True))
    op.execute("UPDATE services SET duration_minutes = 30 WHERE duration_minutes IS NULL")
    op.alter_column('services', 'duration_minutes', nullable=False, server_default='30')

    op.add_column('appointments', sa.Column('duration_minutes', sa.Integer(), nullable=True))
    op.execute("UPDATE appointments SET duration_minutes = 30 WHERE duration_minutes IS NULL")
    op.alter_column('appointments', 'duration_minutes', nullable=False, server_default='30')


def downgrade() -> None:
    op.drop_column('appointments', 'duration_minutes')
    op.drop_column('services', 'duration_minutes')
