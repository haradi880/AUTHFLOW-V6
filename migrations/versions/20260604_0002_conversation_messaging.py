"""add conversation based messaging

Revision ID: 20260604_0002
Revises: 20260604_0001
Create Date: 2026-06-04 18:30:00.000000

"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20260604_0002"
down_revision = "20260604_0001"
branch_labels = None
depends_on = None


def _backfill_direct_conversations(connection):
    conversations = sa.table(
        "conversations",
        sa.column("id", sa.Integer),
        sa.column("public_id", sa.String),
        sa.column("type", sa.String),
        sa.column("title", sa.String),
        sa.column("created_by_id", sa.Integer),
        sa.column("last_message_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    conversation_members = sa.table(
        "conversation_members",
        sa.column("conversation_id", sa.Integer),
        sa.column("user_id", sa.Integer),
        sa.column("role", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("joined_at", sa.DateTime),
        sa.column("last_read_message_id", sa.Integer),
        sa.column("last_read_at", sa.DateTime),
    )
    messages = sa.table(
        "messages",
        sa.column("id", sa.Integer),
        sa.column("sender_id", sa.Integer),
        sa.column("recipient_id", sa.Integer),
        sa.column("conversation_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("delivered_at", sa.DateTime),
        sa.column("read_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
        sa.column("is_read", sa.Boolean),
    )
    receipts = sa.table(
        "message_receipts",
        sa.column("message_id", sa.Integer),
        sa.column("user_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("delivered_at", sa.DateTime),
        sa.column("read_at", sa.DateTime),
    )

    rows = connection.execute(
        sa.text(
            """
            SELECT id, sender_id, recipient_id, created_at, is_read
            FROM messages
            WHERE conversation_id IS NULL AND recipient_id IS NOT NULL
            ORDER BY created_at ASC, id ASC
            """
        )
    ).mappings().all()
    grouped = {}
    for row in rows:
        pair = tuple(sorted((row["sender_id"], row["recipient_id"])))
        grouped.setdefault(pair, []).append(row)

    for pair, pair_messages in grouped.items():
        first = pair_messages[0]
        last = pair_messages[-1]
        created_at = first["created_at"] or datetime.utcnow()
        last_at = last["created_at"] or created_at
        public_id = uuid.uuid4().hex
        connection.execute(
            conversations.insert().values(
                public_id=public_id,
                type="direct",
                title=None,
                created_by_id=first["sender_id"],
                last_message_at=last_at,
                created_at=created_at,
                updated_at=last_at,
            )
        )
        conversation_id = connection.execute(sa.select(conversations.c.id).where(conversations.c.public_id == public_id)).scalar_one()
        for user_id in pair:
            latest_read = next(
                (message for message in reversed(pair_messages) if message["recipient_id"] == user_id and message["is_read"]),
                None,
            )
            connection.execute(
                conversation_members.insert().values(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="member",
                    is_active=True,
                    joined_at=created_at,
                    last_read_message_id=latest_read["id"] if latest_read else None,
                    last_read_at=latest_read["created_at"] if latest_read else None,
                )
            )
        for message in pair_messages:
            read_at = message["created_at"] if message["is_read"] else None
            connection.execute(
                messages.update()
                .where(messages.c.id == message["id"])
                .values(
                    conversation_id=conversation_id,
                    status="read" if message["is_read"] else "delivered",
                    delivered_at=message["created_at"],
                    read_at=read_at,
                )
            )
            connection.execute(
                receipts.insert().values(
                    message_id=message["id"],
                    user_id=message["sender_id"],
                    status="read",
                    delivered_at=message["created_at"],
                    read_at=message["created_at"],
                )
            )
            connection.execute(
                receipts.insert().values(
                    message_id=message["id"],
                    user_id=message["recipient_id"],
                    status="read" if message["is_read"] else "delivered",
                    delivered_at=message["created_at"],
                    read_at=read_at,
                )
            )


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("type IN ('direct', 'group')", name="ck_conversations_type"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_conversations_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_conversations_created_by_id"), ["created_by_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_conversations_last_message_at"), ["last_message_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_conversations_public_id"), ["public_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_conversations_type"), ["type"], unique=False)
        batch_op.create_index("ix_conversations_type_updated", ["type", "updated_at"], unique=False)

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("client_id", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("status", sa.String(length=20), nullable=False, server_default="sent"))
        batch_op.add_column(sa.Column("delivered_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("read_at", sa.DateTime(), nullable=True))
        batch_op.alter_column("recipient_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_foreign_key("fk_messages_conversation_id_conversations", "conversations", ["conversation_id"], ["id"], ondelete="CASCADE")
        batch_op.create_index(batch_op.f("ix_messages_client_id"), ["client_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_conversation_id"), ["conversation_id"], unique=False)
        batch_op.create_index("ix_messages_conversation_created", ["conversation_id", "created_at"], unique=False)
        batch_op.create_index("ix_messages_conversation_id_id", ["conversation_id", "id"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_delivered_at"), ["delivered_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_read_at"), ["read_at"], unique=False)
        batch_op.create_index("ix_messages_recipient_read_created", ["recipient_id", "is_read", "created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_status"), ["status"], unique=False)
        batch_op.create_index("ix_messages_sender_client", ["sender_id", "client_id"], unique=False)

    op.create_table(
        "conversation_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("left_at", sa.DateTime(), nullable=True),
        sa.Column("last_read_message_id", sa.Integer(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member')", name="ck_conversation_member_role"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_read_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_conversation_member"),
    )
    with op.batch_alter_table("conversation_members", schema=None) as batch_op:
        batch_op.create_index("ix_conversation_members_conversation_role", ["conversation_id", "role"], unique=False)
        batch_op.create_index(batch_op.f("ix_conversation_members_conversation_id"), ["conversation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_conversation_members_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_conversation_members_last_read_message_id"), ["last_read_message_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_conversation_members_role"), ["role"], unique=False)
        batch_op.create_index(batch_op.f("ix_conversation_members_user_id"), ["user_id"], unique=False)
        batch_op.create_index("ix_conversation_members_user_active", ["user_id", "is_active"], unique=False)

    op.create_table(
        "message_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('sent', 'delivered', 'read')", name="ck_message_receipt_status"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_receipt_user"),
    )
    with op.batch_alter_table("message_receipts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_message_receipts_message_id"), ["message_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_message_receipts_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_message_receipts_user_id"), ["user_id"], unique=False)
        batch_op.create_index("ix_message_receipts_user_status", ["user_id", "status"], unique=False)

    _backfill_direct_conversations(op.get_bind())

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.alter_column("status", server_default=None)


def downgrade():
    with op.batch_alter_table("message_receipts", schema=None) as batch_op:
        batch_op.drop_index("ix_message_receipts_user_status")
        batch_op.drop_index(batch_op.f("ix_message_receipts_user_id"))
        batch_op.drop_index(batch_op.f("ix_message_receipts_status"))
        batch_op.drop_index(batch_op.f("ix_message_receipts_message_id"))
    op.drop_table("message_receipts")

    with op.batch_alter_table("conversation_members", schema=None) as batch_op:
        batch_op.drop_index("ix_conversation_members_user_active")
        batch_op.drop_index(batch_op.f("ix_conversation_members_user_id"))
        batch_op.drop_index(batch_op.f("ix_conversation_members_role"))
        batch_op.drop_index(batch_op.f("ix_conversation_members_last_read_message_id"))
        batch_op.drop_index(batch_op.f("ix_conversation_members_is_active"))
        batch_op.drop_index(batch_op.f("ix_conversation_members_conversation_id"))
        batch_op.drop_index("ix_conversation_members_conversation_role")
    op.drop_table("conversation_members")

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index("ix_messages_sender_client")
        batch_op.drop_index(batch_op.f("ix_messages_status"))
        batch_op.drop_index("ix_messages_recipient_read_created")
        batch_op.drop_index(batch_op.f("ix_messages_read_at"))
        batch_op.drop_index(batch_op.f("ix_messages_delivered_at"))
        batch_op.drop_index("ix_messages_conversation_id_id")
        batch_op.drop_index("ix_messages_conversation_created")
        batch_op.drop_index(batch_op.f("ix_messages_conversation_id"))
        batch_op.drop_index(batch_op.f("ix_messages_client_id"))
        batch_op.drop_constraint("fk_messages_conversation_id_conversations", type_="foreignkey")
        batch_op.alter_column("recipient_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("read_at")
        batch_op.drop_column("delivered_at")
        batch_op.drop_column("status")
        batch_op.drop_column("client_id")
        batch_op.drop_column("conversation_id")

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_index("ix_conversations_type_updated")
        batch_op.drop_index(batch_op.f("ix_conversations_type"))
        batch_op.drop_index(batch_op.f("ix_conversations_public_id"))
        batch_op.drop_index(batch_op.f("ix_conversations_last_message_at"))
        batch_op.drop_index(batch_op.f("ix_conversations_created_by_id"))
        batch_op.drop_index(batch_op.f("ix_conversations_created_at"))
    op.drop_table("conversations")
