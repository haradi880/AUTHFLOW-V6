"""add xp system

Revision ID: 20260510_0001
Revises:
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260510_0001"
down_revision = None
branch_labels = None
depends_on = None


# -----------------------------
# Helper Functions
# -----------------------------

def get_inspector():
    bind = op.get_bind()
    return inspect(bind)


def table_exists(table_name):
    inspector = get_inspector()
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    inspector = get_inspector()

    if not table_exists(table_name):
        return False

    columns = inspector.get_columns(table_name)

    return column_name in [col["name"] for col in columns]


def index_exists(table_name, index_name):
    inspector = get_inspector()

    if not table_exists(table_name):
        return False

    indexes = inspector.get_indexes(table_name)

    return index_name in [idx["name"] for idx in indexes]


# -----------------------------
# Upgrade
# -----------------------------

def upgrade():

    # ---------------------------------
    # USERS TABLE
    # ---------------------------------

    if table_exists("users"):

        with op.batch_alter_table("users") as batch:

            if not column_exists("users", "xp_total"):
                batch.add_column(
                    sa.Column(
                        "xp_total",
                        sa.Integer(),
                        nullable=False,
                        server_default=sa.text("0")
                    )
                )

            if not column_exists("users", "level"):
                batch.add_column(
                    sa.Column(
                        "level",
                        sa.Integer(),
                        nullable=False,
                        server_default=sa.text("1")
                    )
                )

            if not column_exists("users", "profile_xp_awarded_at"):
                batch.add_column(
                    sa.Column(
                        "profile_xp_awarded_at",
                        sa.DateTime(),
                        nullable=True
                    )
                )

        if not index_exists("users", "ix_users_xp_total"):
            op.create_index(
                "ix_users_xp_total",
                "users",
                ["xp_total"]
            )

        if not index_exists("users", "ix_users_level"):
            op.create_index(
                "ix_users_level",
                "users",
                ["level"]
            )

    # ---------------------------------
    # XP TRANSACTIONS TABLE
    # ---------------------------------

    if not table_exists("xp_transactions"):

        op.create_table(
            "xp_transactions",

            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
                nullable=False
            ),

            sa.Column(
                "user_id",
                sa.Integer(),
                nullable=False
            ),

            sa.Column(
                "action",
                sa.String(length=50),
                nullable=False
            ),

            sa.Column(
                "points",
                sa.Integer(),
                nullable=False
            ),

            sa.Column(
                "source_type",
                sa.String(length=50),
                nullable=True
            ),

            sa.Column(
                "source_id",
                sa.Integer(),
                nullable=True
            ),

            sa.Column(
                "meta",
                sa.JSON(),
                nullable=True
            ),

            sa.Column(
                "awarded_at",
                sa.DateTime(),
                nullable=False
            ),

            sa.Column(
                "bucket_key",
                sa.String(length=120),
                nullable=True
            ),

            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE"
            ),

            sa.UniqueConstraint(
                "user_id",
                "action",
                "source_type",
                "source_id",
                name="uq_xp_source_once"
            ),

            sa.UniqueConstraint(
                "user_id",
                "action",
                "bucket_key",
                name="uq_xp_bucket_once"
            ),
        )

    xp_indexes = [
        ("ix_xp_transactions_user_id", ["user_id"]),
        ("ix_xp_transactions_action", ["action"]),
        ("ix_xp_transactions_source_type", ["source_type"]),
        ("ix_xp_transactions_source_id", ["source_id"]),
        ("ix_xp_transactions_awarded_at", ["awarded_at"]),
        ("ix_xp_transactions_bucket_key", ["bucket_key"]),
    ]

    for index_name, columns in xp_indexes:

        if not index_exists("xp_transactions", index_name):

            op.create_index(
                index_name,
                "xp_transactions",
                columns
            )

    # ---------------------------------
    # PROJECT STARS TABLE
    # ---------------------------------

    if not table_exists("project_stars"):

        op.create_table(
            "project_stars",

            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
                nullable=False
            ),

            sa.Column(
                "user_id",
                sa.Integer(),
                nullable=False
            ),

            sa.Column(
                "project_id",
                sa.Integer(),
                nullable=False
            ),

            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False
            ),

            sa.ForeignKeyConstraint(
                ["project_id"],
                ["projects.id"],
                ondelete="CASCADE"
            ),

            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE"
            ),

            sa.UniqueConstraint(
                "user_id",
                "project_id",
                name="uq_project_star"
            ),
        )

    project_indexes = [
        ("ix_project_stars_user_id", ["user_id"]),
        ("ix_project_stars_project_id", ["project_id"]),
        ("ix_project_stars_created_at", ["created_at"]),
    ]

    for index_name, columns in project_indexes:

        if not index_exists("project_stars", index_name):

            op.create_index(
                index_name,
                "project_stars",
                columns
            )


# -----------------------------
# Downgrade
# -----------------------------

def downgrade():

    # ---------------------------------
    # PROJECT STARS
    # ---------------------------------

    if table_exists("project_stars"):

        indexes = [
            "ix_project_stars_created_at",
            "ix_project_stars_project_id",
            "ix_project_stars_user_id"
        ]

        for idx in indexes:
            if index_exists("project_stars", idx):
                op.drop_index(idx, table_name="project_stars")

        op.drop_table("project_stars")

    # ---------------------------------
    # XP TRANSACTIONS
    # ---------------------------------

    if table_exists("xp_transactions"):

        indexes = [
            "ix_xp_transactions_bucket_key",
            "ix_xp_transactions_awarded_at",
            "ix_xp_transactions_source_id",
            "ix_xp_transactions_source_type",
            "ix_xp_transactions_action",
            "ix_xp_transactions_user_id"
        ]

        for idx in indexes:
            if index_exists("xp_transactions", idx):
                op.drop_index(idx, table_name="xp_transactions")

        op.drop_table("xp_transactions")

    # ---------------------------------
    # USERS TABLE
    # ---------------------------------

    if table_exists("users"):

        with op.batch_alter_table("users") as batch:

            if index_exists("users", "ix_users_level"):
                batch.drop_index("ix_users_level")

            if index_exists("users", "ix_users_xp_total"):
                batch.drop_index("ix_users_xp_total")

            if column_exists("users", "profile_xp_awarded_at"):
                batch.drop_column("profile_xp_awarded_at")

            if column_exists("users", "level"):
                batch.drop_column("level")

            if column_exists("users", "xp_total"):
                batch.drop_column("xp_total")