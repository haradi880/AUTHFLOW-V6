"""Add production notification, hiring, and collaboration workflow fields.

Revision ID: 20260519_0004
Revises: 20260518_0003
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260519_0004"
down_revision = "20260518_0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("seen_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("read_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("delivered_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch.add_column(sa.Column("email_sent_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"))
        batch.add_column(sa.Column("entity_type", sa.String(length=60), nullable=True))
        batch.add_column(sa.Column("entity_id", sa.Integer(), nullable=True))
        batch.create_index("ix_notifications_delivered_at", ["delivered_at"])
        batch.create_index("ix_notifications_priority", ["priority"])
        batch.create_index("ix_notifications_entity_type", ["entity_type"])
        batch.create_index("ix_notifications_entity_id", ["entity_id"])
        batch.create_index("ix_notifications_user_read_created", ["user_id", "is_read", "created_at"])
        batch.create_index("ix_notifications_entity", ["entity_type", "entity_id"])

    with op.batch_alter_table("job_applications") as batch:
        batch.add_column(sa.Column("recruiter_response", sa.String(length=1000), nullable=True))
        batch.add_column(sa.Column("status_changed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch.add_column(sa.Column("reviewed_by_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_job_applications_reviewed_by_id_users", "users", ["reviewed_by_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_job_applications_status_changed_at", ["status_changed_at"])
        batch.create_index("ix_job_applications_reviewed_by_id", ["reviewed_by_id"])
        batch.create_index("ix_job_applications_job_status_created", ["job_id", "status", "created_at"])
        batch.create_index("ix_job_applications_user_status_created", ["user_id", "status", "created_at"])

    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.create_index("ix_jobs_status_category_type_mode", "jobs", ["status", "category", "job_type", "work_mode"])
    op.create_index("ix_jobs_company_status", "jobs", ["company_id", "status"])

    op.create_table(
        "teams",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teams_created_at", "teams", ["created_at"])
    op.create_index("ix_teams_slug", "teams", ["slug"], unique=True)
    op.create_index("ix_teams_visibility", "teams", ["visibility"])
    op.create_index("ix_teams_owner_id", "teams", ["owner_id"])

    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])
    op.create_index("ix_team_members_role", "team_members", ["role"])
    op.create_index("ix_team_members_user_role", "team_members", ["user_id", "role"])

    op.create_table(
        "team_invitations",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("inviter_id", sa.Integer(), nullable=True),
        sa.Column("invitee_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False, server_default="member"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invitee_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "invitee_id", "status", name="uq_team_invitation_status"),
    )
    op.create_index("ix_team_invitations_created_at", "team_invitations", ["created_at"])
    op.create_index("ix_team_invitations_team_id", "team_invitations", ["team_id"])
    op.create_index("ix_team_invitations_inviter_id", "team_invitations", ["inviter_id"])
    op.create_index("ix_team_invitations_invitee_id", "team_invitations", ["invitee_id"])
    op.create_index("ix_team_invitations_status", "team_invitations", ["status"])
    op.create_index("ix_team_invitations_invitee_status", "team_invitations", ["invitee_id", "status"])

    op.create_table(
        "collaboration_requests",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=True),
        sa.Column("requested_role", sa.String(length=60), nullable=False, server_default="collaborator"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_collaboration_requests_created_at", "collaboration_requests", ["created_at"])
    op.create_index("ix_collaboration_requests_requester_id", "collaboration_requests", ["requester_id"])
    op.create_index("ix_collaboration_requests_recipient_id", "collaboration_requests", ["recipient_id"])
    op.create_index("ix_collaboration_requests_project_id", "collaboration_requests", ["project_id"])
    op.create_index("ix_collaboration_requests_job_id", "collaboration_requests", ["job_id"])
    op.create_index("ix_collaboration_requests_team_id", "collaboration_requests", ["team_id"])
    op.create_index("ix_collaboration_requests_status", "collaboration_requests", ["status"])
    op.create_index("ix_collab_requests_recipient_status", "collaboration_requests", ["recipient_id", "status"])
    op.create_index("ix_collab_requests_requester_status", "collaboration_requests", ["requester_id", "status"])

    op.create_table(
        "activity_updates",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_activity_updates_created_at", "activity_updates", ["created_at"])
    op.create_index("ix_activity_updates_actor_id", "activity_updates", ["actor_id"])
    op.create_index("ix_activity_updates_team_id", "activity_updates", ["team_id"])
    op.create_index("ix_activity_updates_project_id", "activity_updates", ["project_id"])
    op.create_index("ix_activity_updates_job_id", "activity_updates", ["job_id"])
    op.create_index("ix_activity_updates_action", "activity_updates", ["action"])
    op.create_index("ix_activity_updates_team_created", "activity_updates", ["team_id", "created_at"])
    op.create_index("ix_activity_updates_project_created", "activity_updates", ["project_id", "created_at"])
    op.create_index("ix_activity_updates_job_created", "activity_updates", ["job_id", "created_at"])


def downgrade():
    op.drop_table("activity_updates")
    op.drop_table("collaboration_requests")
    op.drop_table("team_invitations")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_index("ix_jobs_company_status", table_name="jobs")
    op.drop_index("ix_jobs_status_category_type_mode", table_name="jobs")
    op.drop_index("ix_jobs_status_created", table_name="jobs")
    with op.batch_alter_table("job_applications") as batch:
        batch.drop_index("ix_job_applications_user_status_created")
        batch.drop_index("ix_job_applications_job_status_created")
        batch.drop_index("ix_job_applications_reviewed_by_id")
        batch.drop_index("ix_job_applications_status_changed_at")
        batch.drop_constraint("fk_job_applications_reviewed_by_id_users", type_="foreignkey")
        batch.drop_column("reviewed_by_id")
        batch.drop_column("status_changed_at")
        batch.drop_column("recruiter_response")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_index("ix_notifications_entity")
        batch.drop_index("ix_notifications_user_read_created")
        batch.drop_index("ix_notifications_entity_id")
        batch.drop_index("ix_notifications_entity_type")
        batch.drop_index("ix_notifications_priority")
        batch.drop_index("ix_notifications_delivered_at")
        batch.drop_column("entity_id")
        batch.drop_column("entity_type")
        batch.drop_column("priority")
        batch.drop_column("email_sent_at")
        batch.drop_column("delivered_at")
        batch.drop_column("read_at")
        batch.drop_column("seen_at")
