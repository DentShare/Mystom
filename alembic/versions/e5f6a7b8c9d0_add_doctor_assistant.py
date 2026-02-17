"""add_doctor_assistant role owner_id and doctor_assistant table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('role', sa.String(20), nullable=False, server_default='owner'))
    op.add_column('users', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_owner_id', 'users', 'users', ['owner_id'], ['id'], ondelete='SET NULL')

    op.create_table(
        'doctor_assistant',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assistant_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=False),
        sa.Column('invite_code', sa.String(32), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint('uq_doctor_assistant_doctor_assistant', 'doctor_assistant', ['doctor_id', 'assistant_id'])
    op.create_index('ix_doctor_assistant_doctor_id', 'doctor_assistant', ['doctor_id'])
    op.create_index('ix_doctor_assistant_assistant_id', 'doctor_assistant', ['assistant_id'])
    op.create_index('ix_doctor_assistant_invite_code', 'doctor_assistant', ['invite_code'])

    op.create_table(
        'invite_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code', sa.String(12), nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint('uq_invite_codes_code', 'invite_codes', ['code'])
    op.create_index('ix_invite_codes_doctor_id', 'invite_codes', ['doctor_id'])


def downgrade() -> None:
    op.drop_table('invite_codes')
    op.drop_table('doctor_assistant')
    op.drop_constraint('fk_users_owner_id', 'users', type_='foreignkey')
    op.drop_column('users', 'owner_id')
    op.drop_column('users', 'role')
