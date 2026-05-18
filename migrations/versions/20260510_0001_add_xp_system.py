"""add xp system

Revision ID: 20260510_0001
Revises:
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260510_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("xp_total", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("level", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("profile_xp_awarded_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_users_xp_total", ["xp_total"])
        batch.create_index("ix_users_level", ["level"])

    op.create_table(
        "xp_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("awarded_at", sa.DateTime(), nullable=False),
        sa.Column("bucket_key", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "action", "source_type", "source_id", name="uq_xp_source_once"),
        sa.UniqueConstraint("user_id", "action", "bucket_key", name="uq_xp_bucket_once"),
    )
    op.create_index("ix_xp_transactions_user_id", "xp_transactions", ["user_id"])
    op.create_index("ix_xp_transactions_action", "xp_transactions", ["action"])
    op.create_index("ix_xp_transactions_source_type", "xp_transactions", ["source_type"])
    op.create_index("ix_xp_transactions_source_id", "xp_transactions", ["source_id"])
    op.create_index("ix_xp_transactions_awarded_at", "xp_transactions", ["awarded_at"])
    op.create_index("ix_xp_transactions_bucket_key", "xp_transactions", ["bucket_key"])

    op.create_table(
        "project_stars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "project_id", name="uq_project_star"),
    )
    op.create_index("ix_project_stars_user_id", "project_stars", ["user_id"])
    op.create_index("ix_project_stars_project_id", "project_stars", ["project_id"])
    op.create_index("ix_project_stars_created_at", "project_stars", ["created_at"])


def downgrade():
    op.drop_index("ix_project_stars_created_at", table_name="project_stars")
    op.drop_index("ix_project_stars_project_id", table_name="project_stars")
    op.drop_index("ix_project_stars_user_id", table_name="project_stars")
    op.drop_table("project_stars")
    op.drop_index("ix_xp_transactions_bucket_key", table_name="xp_transactions")
    op.drop_index("ix_xp_transactions_awarded_at", table_name="xp_transactions")
    op.drop_index("ix_xp_transactions_source_id", table_name="xp_transactions")
    op.drop_index("ix_xp_transactions_source_type", table_name="xp_transactions")
    op.drop_index("ix_xp_transactions_action", table_name="xp_transactions")
    op.drop_index("ix_xp_transactions_user_id", table_name="xp_transactions")
    op.drop_table("xp_transactions")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_level")
        batch.drop_index("ix_users_xp_total")
        batch.drop_column("profile_xp_awarded_at")
        batch.drop_column("level")
        batch.drop_column("xp_total")
