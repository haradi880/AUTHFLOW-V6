"""Conversation and message domain helpers."""

from datetime import datetime

from sqlalchemy import select

from app.extensions import db
from app.models import Conversation, ConversationMember, Message, MessageReceipt, User


def active_member(conversation, user):
    if not conversation or not user or not getattr(user, "is_authenticated", False):
        return None
    return ConversationMember.query.filter_by(
        conversation_id=conversation.id,
        user_id=user.id,
        is_active=True,
    ).first()


def conversation_query_for_user(user):
    return (
        Conversation.query.join(ConversationMember)
        .filter(ConversationMember.user_id == user.id, ConversationMember.is_active.is_(True))
        .order_by(Conversation.last_message_at.desc(), Conversation.updated_at.desc())
    )


def get_or_create_direct_conversation(user_a, user_b):
    if not user_a or not user_b or user_a.id == user_b.id:
        return None

    matching_ids = (
        select(ConversationMember.conversation_id)
        .filter(ConversationMember.user_id == user_b.id, ConversationMember.is_active.is_(True))
    )
    conversation = (
        Conversation.query.join(ConversationMember)
        .filter(
            Conversation.type == "direct",
            ConversationMember.user_id == user_a.id,
            ConversationMember.is_active.is_(True),
            Conversation.id.in_(matching_ids),
        )
        .first()
    )
    if conversation:
        return conversation

    conversation = Conversation(type="direct", created_by_id=user_a.id)
    db.session.add(conversation)
    db.session.flush()
    db.session.add_all(
        [
            ConversationMember(conversation_id=conversation.id, user_id=user_a.id, role="member"),
            ConversationMember(conversation_id=conversation.id, user_id=user_b.id, role="member"),
        ]
    )
    db.session.flush()
    return conversation


def create_group_conversation(owner, title, members):
    title = (title or "").strip()[:160] or "New group"
    unique_members = {member.id: member for member in members if member and member.id != owner.id}
    conversation = Conversation(type="group", title=title, created_by_id=owner.id)
    db.session.add(conversation)
    db.session.flush()
    db.session.add(ConversationMember(conversation_id=conversation.id, user_id=owner.id, role="owner"))
    for member in unique_members.values():
        db.session.add(ConversationMember(conversation_id=conversation.id, user_id=member.id, role="member"))
    db.session.flush()
    return conversation


def add_group_member(conversation, user, role="member"):
    existing = ConversationMember.query.filter_by(conversation_id=conversation.id, user_id=user.id).first()
    if existing:
        existing.is_active = True
        existing.left_at = None
        existing.role = role if role in {"owner", "admin", "member"} else "member"
        return existing
    member = ConversationMember(
        conversation_id=conversation.id,
        user_id=user.id,
        role=role if role in {"owner", "admin", "member"} else "member",
    )
    db.session.add(member)
    return member


def remove_group_member(conversation, user_id):
    member = ConversationMember.query.filter_by(conversation_id=conversation.id, user_id=user_id, is_active=True).first()
    if not member:
        return False
    member.is_active = False
    member.left_at = datetime.utcnow()
    if member.role == "owner":
        replacement = (
            ConversationMember.query.filter(
                ConversationMember.conversation_id == conversation.id,
                ConversationMember.user_id != user_id,
                ConversationMember.is_active.is_(True),
            )
            .order_by(ConversationMember.role == "admin", ConversationMember.joined_at.asc())
            .first()
        )
        if replacement:
            replacement.role = "owner"
    return True


def create_message(conversation, sender, content, attachment_data=None, client_id=None):
    if not active_member(conversation, sender):
        raise PermissionError("User is not a member of this conversation.")

    recipient_id = None
    if conversation.type == "direct":
        other = (
            ConversationMember.query.filter(
                ConversationMember.conversation_id == conversation.id,
                ConversationMember.user_id != sender.id,
                ConversationMember.is_active.is_(True),
            )
            .first()
        )
        recipient_id = other.user_id if other else None

    message = Message(
        conversation_id=conversation.id,
        sender_id=sender.id,
        recipient_id=recipient_id,
        content=content,
        client_id=(client_id or "")[:80] or None,
        status="sent",
        delivered_at=datetime.utcnow(),
    )
    if attachment_data:
        message.attachment_filename = attachment_data["filename"]
        message.attachment_original_name = attachment_data["original_name"]
        message.attachment_mime = attachment_data["mime"]
        message.attachment_size = attachment_data["size"]
    db.session.add(message)
    db.session.flush()
    add_message_receipts(message)
    conversation.last_message_at = message.created_at
    conversation.updated_at = datetime.utcnow()
    return message


def add_message_receipts(message):
    if not message.conversation_id:
        if message.recipient_id:
            db.session.add(MessageReceipt(message_id=message.id, user_id=message.recipient_id, status="delivered"))
        return
    members = ConversationMember.query.filter_by(conversation_id=message.conversation_id, is_active=True).all()
    for member in members:
        if member.user_id == message.sender_id:
            db.session.add(MessageReceipt(message_id=message.id, user_id=member.user_id, status="read", read_at=message.created_at))
        else:
            db.session.add(MessageReceipt(message_id=message.id, user_id=member.user_id, status="delivered", delivered_at=message.created_at))


def mark_conversation_read(conversation, user, through_message_id=None):
    member = active_member(conversation, user)
    if not member:
        return 0

    latest = (
        Message.query.filter(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .first()
    )
    if not latest:
        return 0

    through_id = min(int(through_message_id or latest.id), latest.id)
    now = datetime.utcnow()
    member.last_read_message_id = through_id
    member.last_read_at = now
    receipt_ids = (
        select(MessageReceipt.id)
        .join(Message)
        .filter(
            Message.conversation_id == conversation.id,
            Message.id <= through_id,
            Message.sender_id != user.id,
            MessageReceipt.user_id == user.id,
            MessageReceipt.status != "read",
        )
    )
    updated = MessageReceipt.query.filter(MessageReceipt.id.in_(receipt_ids)).update(
        {"status": "read", "read_at": now},
        synchronize_session=False,
    )
    Message.query.filter(
        Message.conversation_id == conversation.id,
        Message.id <= through_id,
        Message.recipient_id == user.id,
        Message.is_read.is_(False),
    ).update({"is_read": True, "read_at": now}, synchronize_session=False)
    return updated


def unread_count(conversation, user):
    member = active_member(conversation, user)
    if not member:
        return 0
    query = Message.query.filter(Message.conversation_id == conversation.id, Message.sender_id != user.id)
    if member.last_read_message_id:
        query = query.filter(Message.id > member.last_read_message_id)
    return query.count()


def conversation_other_user(conversation, user):
    if conversation.type != "direct":
        return None
    member = (
        ConversationMember.query.filter(
            ConversationMember.conversation_id == conversation.id,
            ConversationMember.user_id != user.id,
            ConversationMember.is_active.is_(True),
        )
        .first()
    )
    return db.session.get(User, member.user_id) if member else None


def search_users_for_group(raw_names):
    usernames = [name.strip().lstrip("@") for name in (raw_names or "").replace(",", "\n").splitlines() if name.strip()]
    if not usernames:
        return []
    return User.query.filter(User.username.in_(usernames), User.active.is_(True)).limit(30).all()
