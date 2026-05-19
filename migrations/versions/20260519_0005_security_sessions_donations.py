"""Add login device history and donation logging.

Revision ID: 20260519_0005
Revises: 20260519_0004
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260519_0005"
down_revision = "20260519_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("device_label", sa.String(length=160), nullable=True),
        sa.Column("browser", sa.String(length=80), nullable=True),
        sa.Column("platform", sa.String(length=80), nullable=True),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_login_sessions_public_id", "login_sessions", ["public_id"], unique=True)
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    op.create_index("ix_login_sessions_ip_address", "login_sessions", ["ip_address"])
    op.create_index("ix_login_sessions_fingerprint", "login_sessions", ["fingerprint"])
    op.create_index("ix_login_sessions_is_current", "login_sessions", ["is_current"])
    op.create_index("ix_login_sessions_revoked_at", "login_sessions", ["revoked_at"])
    op.create_index("ix_login_sessions_last_seen_at", "login_sessions", ["last_seen_at"])
    op.create_index("ix_login_sessions_created_at", "login_sessions", ["created_at"])
    op.create_index("ix_login_sessions_user_revoked_seen", "login_sessions", ["user_id", "revoked_at", "last_seen_at"])
    op.create_index("ix_login_sessions_user_fingerprint", "login_sessions", ["user_id", "fingerprint"])

    op.create_table(
        "login_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(length=160), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("fingerprint", sa.String(length=128), nullable=True),
        sa.Column("suspicious", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_login_events_user_id", "login_events", ["user_id"])
    op.create_index("ix_login_events_email", "login_events", ["email"])
    op.create_index("ix_login_events_event_type", "login_events", ["event_type"])
    op.create_index("ix_login_events_success", "login_events", ["success"])
    op.create_index("ix_login_events_reason", "login_events", ["reason"])
    op.create_index("ix_login_events_ip_address", "login_events", ["ip_address"])
    op.create_index("ix_login_events_fingerprint", "login_events", ["fingerprint"])
    op.create_index("ix_login_events_suspicious", "login_events", ["suspicious"])
    op.create_index("ix_login_events_created_at", "login_events", ["created_at"])
    op.create_index("ix_login_events_user_created", "login_events", ["user_id", "created_at"])
    op.create_index("ix_login_events_email_created", "login_events", ["email", "created_at"])
    op.create_index("ix_login_events_success_created", "login_events", ["success", "created_at"])

    op.create_table(
        "donation_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("upi_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="qr_generated"),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_donation_intents_public_id", "donation_intents", ["public_id"], unique=True)
    op.create_index("ix_donation_intents_user_id", "donation_intents", ["user_id"])
    op.create_index("ix_donation_intents_status", "donation_intents", ["status"])
    op.create_index("ix_donation_intents_ip_address", "donation_intents", ["ip_address"])
    op.create_index("ix_donation_intents_created_at", "donation_intents", ["created_at"])
    op.create_index("ix_donation_intents_user_created", "donation_intents", ["user_id", "created_at"])
    op.create_index("ix_donation_intents_status_created", "donation_intents", ["status", "created_at"])


def downgrade():
    op.drop_table("donation_intents")
    op.drop_table("login_events")
    op.drop_table("login_sessions")
