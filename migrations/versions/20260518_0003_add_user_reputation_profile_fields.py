"""add user reputation and profile fields

Revision ID: 20260518_0003
Revises: 20260510_0002
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260518_0003"
down_revision = "20260510_0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("reputation_points", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("trust_level", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("contributor_tier", sa.String(length=30), nullable=False, server_default="newcomer"))
        batch.add_column(sa.Column("is_verified_creator", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("open_to_work", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("availability_status", sa.String(length=30), nullable=False, server_default="not-specified"))
        batch.add_column(sa.Column("job_title", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("years_experience", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("preferred_work_type", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("is_recruiter", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("robotics_specialties", sa.Text(), nullable=True))
        batch.add_column(sa.Column("portfolio_score", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("last_analyzed_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_users_reputation_points", ["reputation_points"])


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_reputation_points")
        batch.drop_column("last_analyzed_at")
        batch.drop_column("portfolio_score")
        batch.drop_column("robotics_specialties")
        batch.drop_column("is_recruiter")
        batch.drop_column("preferred_work_type")
        batch.drop_column("years_experience")
        batch.drop_column("job_title")
        batch.drop_column("availability_status")
        batch.drop_column("open_to_work")
        batch.drop_column("is_verified_creator")
        batch.drop_column("contributor_tier")
        batch.drop_column("trust_level")
        batch.drop_column("reputation_points")
