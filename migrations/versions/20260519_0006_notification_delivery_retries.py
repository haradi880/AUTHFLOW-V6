"""Add notification delivery retry fields.

Revision ID: 20260519_0006
Revises: 20260519_0005
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260519_0006"
down_revision = "20260519_0005"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("email_status", sa.String(length=30), nullable=False, server_default="pending"))
        batch.add_column(sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_error", sa.String(length=500), nullable=True))
        batch.create_index("ix_notifications_email_status", ["email_status"])


def downgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.drop_index("ix_notifications_email_status")
        batch.drop_column("last_error")
        batch.drop_column("retry_count")
        batch.drop_column("email_status")
