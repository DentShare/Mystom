"""add indexes on FK columns and expires_at to invite_codes

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-02-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # InviteCode: expires_at + index on doctor_id
    op.add_column("invite_codes", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_invite_codes_doctor_id", "invite_codes", ["doctor_id"])

    # Indexes on doctor_id for all tables that query by doctor
    op.create_index("ix_patients_doctor_id", "patients", ["doctor_id"])
    op.create_index("ix_appointments_doctor_id", "appointments", ["doctor_id"])
    op.create_index("ix_services_doctor_id", "services", ["doctor_id"])
    op.create_index("ix_treatments_doctor_id", "treatments", ["doctor_id"])
    op.create_index("ix_treatments_patient_id", "treatments", ["patient_id"])
    op.create_index("ix_implant_logs_doctor_id", "implant_logs", ["doctor_id"])
    op.create_index("ix_implant_logs_patient_id", "implant_logs", ["patient_id"])
    op.create_index("ix_clinic_locations_doctor_id", "clinic_locations", ["doctor_id"])


def downgrade() -> None:
    op.drop_index("ix_clinic_locations_doctor_id", "clinic_locations")
    op.drop_index("ix_implant_logs_patient_id", "implant_logs")
    op.drop_index("ix_implant_logs_doctor_id", "implant_logs")
    op.drop_index("ix_treatments_patient_id", "treatments")
    op.drop_index("ix_treatments_doctor_id", "treatments")
    op.drop_index("ix_services_doctor_id", "services")
    op.drop_index("ix_appointments_doctor_id", "appointments")
    op.drop_index("ix_patients_doctor_id", "patients")
    op.drop_index("ix_invite_codes_doctor_id", "invite_codes")
    op.drop_column("invite_codes", "expires_at")
