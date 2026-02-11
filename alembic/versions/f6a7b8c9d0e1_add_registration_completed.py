"""add registration_completed to users

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("registration_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Существующие пользователи, уже прошедшие регистрацию (врач с специализацией или ассистент с привязкой)
    op.execute("""
        UPDATE users
        SET registration_completed = true
        WHERE (specialization IS NOT NULL AND specialization != '')
           OR (role = 'assistant' AND owner_id IS NOT NULL)
    """)


def downgrade() -> None:
    op.drop_column("users", "registration_completed")
