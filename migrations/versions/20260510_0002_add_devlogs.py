"""add devlogs

Revision ID: 20260510_0002
Revises: 20260510_0001
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260510_0002"
down_revision = "20260510_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "devlogs",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("milestone", sa.String(length=160), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="public"),
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reposts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bookmarks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_devlogs_created_at", "devlogs", ["created_at"])
    op.create_index("ix_devlogs_updated_at", "devlogs", ["updated_at"])
    op.create_index("ix_devlogs_progress", "devlogs", ["progress"])
    op.create_index("ix_devlogs_is_pinned", "devlogs", ["is_pinned"])
    op.create_index("ix_devlogs_visibility", "devlogs", ["visibility"])
    op.create_index("ix_devlogs_user_id", "devlogs", ["user_id"])

    op.create_table(
        "devlog_tags",
        sa.Column("devlog_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["devlog_id"], ["devlogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("devlog_id", "tag_id"),
    )

    op.create_table(
        "devlog_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False, server_default="image"),
        sa.Column("alt_text", sa.String(length=200), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("devlog_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["devlog_id"], ["devlogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_devlog_media_devlog_id", "devlog_media", ["devlog_id"])

    op.create_table(
        "devlog_comments",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("devlog_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["devlog_id"], ["devlogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_devlog_comments_created_at", "devlog_comments", ["created_at"])
    op.create_index("ix_devlog_comments_updated_at", "devlog_comments", ["updated_at"])
    op.create_index("ix_devlog_comments_user_id", "devlog_comments", ["user_id"])
    op.create_index("ix_devlog_comments_devlog_id", "devlog_comments", ["devlog_id"])

    op.create_table(
        "devlog_likes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("devlog_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["devlog_id"], ["devlogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "devlog_id", name="uq_devlog_like"),
    )
    op.create_index("ix_devlog_likes_user_id", "devlog_likes", ["user_id"])
    op.create_index("ix_devlog_likes_devlog_id", "devlog_likes", ["devlog_id"])

    op.create_table(
        "devlog_bookmarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("devlog_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["devlog_id"], ["devlogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "devlog_id", name="uq_devlog_bookmark"),
    )
    op.create_index("ix_devlog_bookmarks_user_id", "devlog_bookmarks", ["user_id"])
    op.create_index("ix_devlog_bookmarks_devlog_id", "devlog_bookmarks", ["devlog_id"])

    op.create_table(
        "devlog_reposts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("devlog_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["devlog_id"], ["devlogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "devlog_id", name="uq_devlog_repost"),
    )
    op.create_index("ix_devlog_reposts_user_id", "devlog_reposts", ["user_id"])
    op.create_index("ix_devlog_reposts_devlog_id", "devlog_reposts", ["devlog_id"])


def downgrade():
    op.drop_index("ix_devlog_reposts_devlog_id", table_name="devlog_reposts")
    op.drop_index("ix_devlog_reposts_user_id", table_name="devlog_reposts")
    op.drop_table("devlog_reposts")
    op.drop_index("ix_devlog_bookmarks_devlog_id", table_name="devlog_bookmarks")
    op.drop_index("ix_devlog_bookmarks_user_id", table_name="devlog_bookmarks")
    op.drop_table("devlog_bookmarks")
    op.drop_index("ix_devlog_likes_devlog_id", table_name="devlog_likes")
    op.drop_index("ix_devlog_likes_user_id", table_name="devlog_likes")
    op.drop_table("devlog_likes")
    op.drop_index("ix_devlog_comments_devlog_id", table_name="devlog_comments")
    op.drop_index("ix_devlog_comments_user_id", table_name="devlog_comments")
    op.drop_index("ix_devlog_comments_updated_at", table_name="devlog_comments")
    op.drop_index("ix_devlog_comments_created_at", table_name="devlog_comments")
    op.drop_table("devlog_comments")
    op.drop_index("ix_devlog_media_devlog_id", table_name="devlog_media")
    op.drop_table("devlog_media")
    op.drop_table("devlog_tags")
    op.drop_index("ix_devlogs_user_id", table_name="devlogs")
    op.drop_index("ix_devlogs_visibility", table_name="devlogs")
    op.drop_index("ix_devlogs_is_pinned", table_name="devlogs")
    op.drop_index("ix_devlogs_progress", table_name="devlogs")
    op.drop_index("ix_devlogs_updated_at", table_name="devlogs")
    op.drop_index("ix_devlogs_created_at", table_name="devlogs")
    op.drop_table("devlogs")
