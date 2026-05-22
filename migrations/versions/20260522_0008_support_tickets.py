"""Add support tickets.

Revision ID: 20260522_0008
Revises: 20260521_0007
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260522_0008"
down_revision = "20260521_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False, server_default="general"),
        sa.Column("subject", sa.String(length=180), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("handled_by_id", sa.Integer(), nullable=True),
        sa.Column("admin_note", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["handled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_support_tickets_public_id", "support_tickets", ["public_id"], unique=True)
    op.create_index("ix_support_tickets_email", "support_tickets", ["email"])
    op.create_index("ix_support_tickets_category", "support_tickets", ["category"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])
    op.create_index("ix_support_tickets_priority", "support_tickets", ["priority"])
    op.create_index("ix_support_tickets_created_at", "support_tickets", ["created_at"])
    op.create_index("ix_support_tickets_status_created", "support_tickets", ["status", "created_at"])
    op.create_index("ix_support_tickets_category_status", "support_tickets", ["category", "status"])


def downgrade():
    op.drop_table("support_tickets")
