"""Add message attachments.

Revision ID: 20260521_0007
Revises: 20260519_0006
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260521_0007"
down_revision = "20260519_0006"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("attachment_filename", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("attachment_original_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("attachment_mime", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("attachment_size", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("attachment_size")
        batch.drop_column("attachment_mime")
        batch.drop_column("attachment_original_name")
        batch.drop_column("attachment_filename")
