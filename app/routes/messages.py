"""Conversation-based direct and group messaging routes."""

from pathlib import Path

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Block, Conversation, ConversationMember, Message, User
from app.realtime import emit_conversation_event
from app.services.messaging import (
    active_member,
    add_group_member,
    conversation_other_user,
    conversation_query_for_user,
    create_group_conversation,
    create_message,
    get_or_create_direct_conversation,
    mark_conversation_read,
    remove_group_member,
    search_users_for_group,
    unread_count,
)
from app.services.notifications import create_notification
from app.utils.rate_limit import rate_limit
from app.utils.uploads import fetch_private_upload, safe_message_mime, save_message_attachment


messages_bp = Blueprint("messages", __name__)


def _wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", "")


def _conversation_or_404(public_id):
    conversation = Conversation.query.filter_by(public_id=public_id).first_or_404()
    if not active_member(conversation, current_user) and not current_user.is_admin:
        abort(404)
    return conversation


def _active_members(conversation):
    return (
        ConversationMember.query.filter_by(conversation_id=conversation.id, is_active=True)
        .join(User)
        .order_by(ConversationMember.role.desc(), User.username.asc())
        .all()
    )


def _conversation_summaries(conversations, user):
    conversation_ids = [conversation.id for conversation in conversations]
    if not conversation_ids:
        return {}

    summaries = {
        conversation.id: {
            "last_message": None,
            "unread_count": 0,
            "member_count": 0,
            "other_user": None,
            "current_member": None,
        }
        for conversation in conversations
    }

    latest_ids = (
        db.session.query(
            Message.conversation_id.label("conversation_id"),
            func.max(Message.id).label("message_id"),
        )
        .filter(Message.conversation_id.in_(conversation_ids))
        .group_by(Message.conversation_id)
        .subquery()
    )
    latest_messages = (
        Message.query.join(latest_ids, Message.id == latest_ids.c.message_id)
        .options(joinedload(Message.sender), joinedload(Message.conversation))
        .all()
    )
    for message in latest_messages:
        summaries[message.conversation_id]["last_message"] = message

    member_counts = (
        db.session.query(ConversationMember.conversation_id, func.count(ConversationMember.id))
        .filter(ConversationMember.conversation_id.in_(conversation_ids), ConversationMember.is_active.is_(True))
        .group_by(ConversationMember.conversation_id)
        .all()
    )
    for conversation_id, count in member_counts:
        summaries[conversation_id]["member_count"] = count

    current_members = ConversationMember.query.filter(
        ConversationMember.conversation_id.in_(conversation_ids),
        ConversationMember.user_id == user.id,
        ConversationMember.is_active.is_(True),
    ).all()
    for member in current_members:
        summaries[member.conversation_id]["current_member"] = member

    direct_ids = [conversation.id for conversation in conversations if conversation.type == "direct"]
    if direct_ids:
        other_members = (
            db.session.query(ConversationMember.conversation_id, User)
            .join(User, ConversationMember.user_id == User.id)
            .filter(
                ConversationMember.conversation_id.in_(direct_ids),
                ConversationMember.user_id != user.id,
                ConversationMember.is_active.is_(True),
            )
            .all()
        )
        for conversation_id, other_user in other_members:
            summaries[conversation_id]["other_user"] = other_user

    membership = (
        select(
            ConversationMember.conversation_id.label("conversation_id"),
            ConversationMember.last_read_message_id.label("last_read_message_id"),
        )
        .filter(
            ConversationMember.conversation_id.in_(conversation_ids),
            ConversationMember.user_id == user.id,
            ConversationMember.is_active.is_(True),
        )
        .subquery()
    )
    unread_counts = (
        db.session.query(Message.conversation_id, func.count(Message.id))
        .join(membership, Message.conversation_id == membership.c.conversation_id)
        .filter(
            Message.sender_id != user.id,
            or_(membership.c.last_read_message_id.is_(None), Message.id > membership.c.last_read_message_id),
        )
        .group_by(Message.conversation_id)
        .all()
    )
    for conversation_id, count in unread_counts:
        summaries[conversation_id]["unread_count"] = count

    return summaries


def _display_title_from_summary(conversation, user, summary=None):
    if conversation.type == "group":
        return conversation.title or "Group conversation"
    other_user = (summary or {}).get("other_user")
    if other_user:
        return other_user.full_name or f"@{other_user.username}"
    return conversation.display_title_for(user)


def _can_direct_message(recipient):
    if recipient.id == current_user.id:
        return False, "Cannot message yourself."
    if Block.query.filter_by(blocker_id=recipient.id, blocked_id=current_user.id).first():
        return False, "This user is not available for messages."
    if recipient.message_permission == "none":
        return False, "This user is not accepting messages."
    if recipient.message_permission == "followers" and not recipient.is_following(current_user):
        return False, "Only followers can message this user."
    return True, ""


def message_payload(message):
    return {
        "id": message.id,
        "conversation_id": message.conversation.public_id if message.conversation else None,
        "client_id": message.client_id,
        "content": message.content,
        "sender_id": message.sender_id,
        "sender_username": message.sender.username if message.sender else None,
        "is_read": message.is_read,
        "status": message.display_status_for(current_user) if current_user.is_authenticated else message.status,
        "created_at": message.created_at.isoformat() + "Z",
        "attachment_url": url_for("messages.message_attachment", message_id=message.id) if message.attachment_filename else None,
        "attachment_name": message.attachment_original_name,
        "attachment_mime": message.attachment_mime,
        "attachment_size": message.attachment_size,
    }


def conversation_payload(conversation, include_members=False, summary=None):
    summary = summary or {}
    last_message = summary.get("last_message")
    if last_message is None:
        last_message = conversation.messages.options(joinedload(Message.sender), joinedload(Message.conversation)).order_by(Message.id.desc()).first()
    other_user = summary.get("other_user")
    if other_user is None:
        other_user = conversation_other_user(conversation, current_user)
    member_count = summary.get("member_count")
    if member_count is None:
        member_count = conversation.members.filter_by(is_active=True).count()
    unread_total = summary.get("unread_count")
    if unread_total is None:
        unread_total = unread_count(conversation, current_user)
    current_member = summary.get("current_member")
    can_manage = bool(getattr(current_user, "is_admin", False) or (current_member and current_member.role in {"owner", "admin"}))
    if current_member is None and not summary:
        can_manage = conversation.can_manage(current_user)
    payload = {
        "id": conversation.public_id,
        "type": conversation.type,
        "title": _display_title_from_summary(conversation, current_user, summary),
        "subtitle": f"@{other_user.username}" if other_user else f"{member_count} members",
        "avatar_url": other_user.avatar_url if other_user else "",
        "avatar_initial": (other_user.username[0] if other_user else (conversation.title or "G")[0]).upper(),
        "last_message": message_payload(last_message) if last_message else None,
        "unread_count": unread_total,
        "last_message_at": conversation.last_message_at.isoformat() + "Z" if conversation.last_message_at else None,
        "can_manage": can_manage,
    }
    if include_members:
        payload["members"] = [member_payload(member) for member in _active_members(conversation)]
    return payload


def member_payload(member):
    return {
        "user_id": member.user_id,
        "username": member.user.username,
        "full_name": member.user.full_name,
        "avatar_url": member.user.avatar_url,
        "role": member.role,
        "last_read_message_id": member.last_read_message_id,
    }


def _conversation_list():
    q = request.args.get("q", "").strip().lower()
    conversations = conversation_query_for_user(current_user).limit(80).all()
    if q:
        summaries = _conversation_summaries(conversations, current_user)
        conversations = [
            conversation
            for conversation in conversations
            if q in _display_title_from_summary(conversation, current_user, summaries.get(conversation.id)).lower()
            or (
                summaries.get(conversation.id, {}).get("last_message")
                and q in summaries[conversation.id]["last_message"].content.lower()
            )
        ]
    return conversations


def _conversation_payload_fn(conversations):
    summaries = _conversation_summaries(conversations, current_user)

    def payload(conversation, include_members=False):
        return conversation_payload(conversation, include_members=include_members, summary=summaries.get(conversation.id))

    return payload


def _render_chat(conversation, messages=None):
    mark_conversation_read(conversation, current_user)
    db.session.commit()
    messages = messages or (
        Message.query.filter_by(conversation_id=conversation.id)
        .order_by(Message.id.desc())
        .limit(50)
        .all()
    )
    messages = list(reversed(messages))
    conversations = _conversation_list()
    payload_fn = _conversation_payload_fn(conversations + [conversation])
    return render_template(
        "messages/chat.html",
        conversation=conversation,
        conversations=conversations,
        active_conversation=payload_fn(conversation, include_members=True),
        conversation_payload_fn=payload_fn,
        other_user=conversation_other_user(conversation, current_user),
        members=_active_members(conversation),
        messages=messages,
    )


@messages_bp.get("/messages")
@login_required
@rate_limit(max_calls=120, window_seconds=60, scope="messages-inbox", methods={"GET"})
def inbox():
    conversations = _conversation_list()
    return render_template("messages/inbox.html", conversations=conversations, conversation_payload_fn=_conversation_payload_fn(conversations))


@messages_bp.get("/messages/c/<public_id>")
@login_required
def conversation_chat(public_id):
    conversation = _conversation_or_404(public_id)
    return _render_chat(conversation)


@messages_bp.get("/messages/<username>")
@login_required
def chat(username):
    other_user = User.query.filter_by(username=username, active=True).first_or_404()
    allowed, reason = _can_direct_message(other_user)
    if not allowed:
        flash(reason, "error")
        return redirect(url_for("messages.inbox"))
    conversation = get_or_create_direct_conversation(current_user, other_user)
    db.session.commit()
    return _render_chat(conversation)


@messages_bp.get("/messages/attachments/<int:message_id>")
@login_required
def message_attachment(message_id):
    message = db.get_or_404(Message, message_id)
    allowed = current_user.id in {message.sender_id, message.recipient_id}
    if not allowed and message.conversation_id:
        allowed = bool(
            ConversationMember.query.filter_by(
                conversation_id=message.conversation_id,
                user_id=current_user.id,
                is_active=True,
            ).first()
        )
    if not allowed:
        abort(404)
    if not message.attachment_filename or Path(message.attachment_filename).name != message.attachment_filename:
        abort(404)

    download_name = secure_filename(message.attachment_original_name or "") or message.attachment_filename
    response_mime = safe_message_mime(message.attachment_original_name or message.attachment_filename, message.attachment_mime)
    as_attachment = not response_mime.startswith(("image/", "application/pdf", "text/plain"))
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    filepath = (upload_root / "messages" / message.attachment_filename).resolve()
    if upload_root in filepath.parents and filepath.exists() and filepath.is_file():
        response = send_file(
            filepath,
            mimetype=response_mime,
            as_attachment=as_attachment,
            download_name=download_name,
        )
    else:
        private_file = fetch_private_upload("messages", message.attachment_filename)
        if not private_file:
            abort(404)
        content, _content_type = private_file
        response = Response(content, mimetype=response_mime)
        disposition = "attachment" if as_attachment else "inline"
        response.headers.set("Content-Disposition", disposition, filename=download_name)

    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@messages_bp.get("/messages/c/<public_id>/messages")
@login_required
@rate_limit(max_calls=180, window_seconds=60, scope="message-pagination", methods={"GET"})
def conversation_messages(public_id):
    conversation = _conversation_or_404(public_id)
    before_id = request.args.get("before_id", type=int)
    after_id = request.args.get("after_id", type=int)
    query = Message.query.filter_by(conversation_id=conversation.id)
    if before_id:
        query = query.filter(Message.id < before_id).order_by(Message.id.desc()).limit(30)
        messages = list(reversed(query.all()))
    elif after_id:
        messages = query.filter(Message.id > after_id).order_by(Message.id.asc()).limit(50).all()
    else:
        messages = list(reversed(query.order_by(Message.id.desc()).limit(50).all()))
    return jsonify({"messages": [message_payload(message) for message in messages]})


@messages_bp.post("/messages/c/<public_id>/send")
@login_required
@rate_limit(max_calls=30, window_seconds=60, scope="messages")
def send_conversation_message(public_id):
    conversation = _conversation_or_404(public_id)
    content = request.form.get("content", "").strip()
    attachment = request.files.get("attachment")
    client_id = (request.form.get("client_id") or "").strip()[:80] or None
    if not content and not (attachment and attachment.filename):
        return jsonify({"error": "Add a message or attachment."}), 400
    if len(content) > 4000:
        return jsonify({"error": "Message is too long."}), 400

    if client_id:
        existing_message = Message.query.filter_by(
            conversation_id=conversation.id,
            sender_id=current_user.id,
            client_id=client_id,
        ).first()
        if existing_message:
            return jsonify(
                {
                    "status": "sent",
                    "message": message_payload(existing_message),
                    "conversation": conversation_payload(conversation),
                    "deduplicated": True,
                }
            )

    attachment_data = None
    if attachment and attachment.filename:
        attachment_data, error = save_message_attachment(attachment)
        if error:
            return jsonify({"error": error}), 400

    try:
        message = create_message(
            conversation,
            current_user,
            content or (attachment_data["original_name"] if attachment_data else ""),
            attachment_data=attachment_data,
            client_id=client_id,
        )
    except PermissionError:
        abort(403)

    for member in _active_members(conversation):
        if member.user_id == current_user.id:
            continue
        create_notification(
            member.user,
            "message",
            f"{current_user.username} sent a message in {conversation.display_title_for(member.user)}",
            link=url_for("messages.conversation_chat", public_id=conversation.public_id),
            from_user=current_user,
            commit=False,
            send_mail=False,
            entity_type="conversation",
            entity_id=conversation.id,
        )
    db.session.commit()
    payload = message_payload(message)
    emit_conversation_event(conversation.public_id, "message:new", {"message": payload})
    return jsonify({"status": "sent", "message": payload, "conversation": conversation_payload(conversation)})


@messages_bp.post("/messages/send")
@login_required
@rate_limit(max_calls=30, window_seconds=60, scope="messages")
def send_message():
    recipient_id = request.form.get("recipient_id", type=int)
    recipient = db.session.get(User, recipient_id) if recipient_id else None
    if not recipient:
        return jsonify({"error": "Recipient not found."}), 404
    allowed, reason = _can_direct_message(recipient)
    if not allowed:
        return jsonify({"error": reason}), 403
    conversation = get_or_create_direct_conversation(current_user, recipient)
    db.session.flush()
    response = send_conversation_message(conversation.public_id)
    return response


@messages_bp.post("/messages/c/<public_id>/read")
@login_required
@rate_limit(max_calls=120, window_seconds=60, scope="message-read")
def read_conversation(public_id):
    conversation = _conversation_or_404(public_id)
    count = mark_conversation_read(conversation, current_user, request.form.get("through_id", type=int))
    db.session.commit()
    emit_conversation_event(conversation.public_id, "message:read", {"conversation": conversation.public_id, "user_id": current_user.id})
    return jsonify({"status": "read", "updated": count})


@messages_bp.post("/messages/c/<public_id>/typing")
@login_required
@rate_limit(max_calls=60, window_seconds=60, scope="message-typing")
def typing(public_id):
    conversation = _conversation_or_404(public_id)
    emit_conversation_event(
        conversation.public_id,
        "conversation:typing",
        {"conversation": conversation.public_id, "user_id": current_user.id, "username": current_user.username},
    )
    return jsonify({"status": "ok"})


@messages_bp.post("/messages/groups")
@login_required
@rate_limit(max_calls=10, window_seconds=600, scope="message-groups")
def create_group():
    title = request.form.get("title", "").strip()
    members = search_users_for_group(request.form.get("members", ""))
    if len(members) < 1:
        flash("Add at least one member by username.", "error")
        return redirect(url_for("messages.inbox"))
    conversation = create_group_conversation(current_user, title, members)
    for member in _active_members(conversation):
        if member.user_id != current_user.id:
            create_notification(
                member.user,
                "message",
                f"{current_user.username} added you to {conversation.title}.",
                link=url_for("messages.conversation_chat", public_id=conversation.public_id),
                from_user=current_user,
                commit=False,
                send_mail=False,
                entity_type="conversation",
                entity_id=conversation.id,
            )
    db.session.commit()
    flash("Group conversation created.", "success")
    return redirect(url_for("messages.conversation_chat", public_id=conversation.public_id))


@messages_bp.post("/messages/c/<public_id>/rename")
@login_required
def rename_group(public_id):
    conversation = _conversation_or_404(public_id)
    if conversation.type != "group" or not conversation.can_manage(current_user):
        abort(403)
    title = request.form.get("title", "").strip()[:160]
    if title:
        conversation.title = title
        db.session.commit()
        emit_conversation_event(conversation.public_id, "conversation:updated", {"conversation": conversation_payload(conversation)})
    return redirect(url_for("messages.conversation_chat", public_id=conversation.public_id))


@messages_bp.post("/messages/c/<public_id>/members")
@login_required
@rate_limit(max_calls=20, window_seconds=600, scope="message-group-members")
def add_member(public_id):
    conversation = _conversation_or_404(public_id)
    if conversation.type != "group" or not conversation.can_manage(current_user):
        abort(403)
    users = search_users_for_group(request.form.get("members", ""))
    for user in users:
        add_group_member(conversation, user)
    db.session.commit()
    flash("Members updated.", "success")
    return redirect(url_for("messages.conversation_chat", public_id=conversation.public_id))


@messages_bp.post("/messages/c/<public_id>/members/<int:user_id>/remove")
@login_required
def remove_member(public_id, user_id):
    conversation = _conversation_or_404(public_id)
    if conversation.type != "group" or not conversation.can_manage(current_user):
        abort(403)
    if user_id == current_user.id:
        flash("Use Leave Group to remove yourself.", "warning")
        return redirect(url_for("messages.conversation_chat", public_id=conversation.public_id))
    remove_group_member(conversation, user_id)
    db.session.commit()
    flash("Member removed.", "success")
    return redirect(url_for("messages.conversation_chat", public_id=conversation.public_id))


@messages_bp.post("/messages/c/<public_id>/leave")
@login_required
def leave_group(public_id):
    conversation = _conversation_or_404(public_id)
    if conversation.type != "group":
        abort(403)
    remove_group_member(conversation, current_user.id)
    db.session.commit()
    flash("You left the group.", "info")
    return redirect(url_for("messages.inbox"))


@messages_bp.get("/messages/search")
@login_required
@rate_limit(max_calls=60, window_seconds=60, scope="message-search", methods={"GET"})
def search_messages():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"conversations": [], "messages": []})
    conversations = [
        conversation_payload(conversation)
        for conversation in _conversation_list()
        if q.lower() in conversation.display_title_for(current_user).lower()
    ]
    member_ids = [member.conversation_id for member in ConversationMember.query.filter_by(user_id=current_user.id, is_active=True).all()]
    messages = (
        Message.query.filter(Message.conversation_id.in_(member_ids), Message.content.ilike(f"%{q}%"))
        .options(joinedload(Message.sender), joinedload(Message.conversation))
        .order_by(Message.created_at.desc())
        .limit(25)
        .all()
    )
    return jsonify({"conversations": conversations, "messages": [message_payload(message) for message in messages]})
