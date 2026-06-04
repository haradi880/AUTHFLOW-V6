"""Optional Socket.IO realtime notifications.

When Flask-SocketIO is installed, production can run with Redis message queues
and emit events to room `user:<id>`. Without the dependency, the app falls back
to the existing polling APIs.
"""

try:
    from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room
except Exception:  # pragma: no cover - optional dependency fallback
    SocketIO = None

from flask_login import current_user


socketio = SocketIO(cors_allowed_origins=[], async_mode="threading", manage_session=False) if SocketIO else None


def notification_room_for_current_user():
    if not current_user.is_authenticated:
        return None
    return f"user:{current_user.id}"


def init_realtime(app):
    if not socketio:
        app.logger.info("Flask-SocketIO unavailable; realtime notifications use polling fallback.")
        return
    socketio.init_app(app, message_queue=app.config.get("REDIS_URL") if app.config.get("TASK_QUEUE_ASYNC") else None)

    @socketio.on("join_notifications")
    def join_notifications(data):
        room = notification_room_for_current_user()
        if not room:
            emit("error", {"message": "Authentication required."})
            disconnect()
            return
        join_room(room)
        payload = {"room": room}
        emit("joined", payload)
        return payload

    @socketio.on("join_conversation")
    def join_conversation(data):
        if not current_user.is_authenticated:
            emit("error", {"message": "Authentication required."})
            disconnect()
            return
        public_id = (data or {}).get("conversation")
        from app.models import Conversation, ConversationMember

        conversation = Conversation.query.filter_by(public_id=public_id).first()
        member = None
        if conversation:
            member = ConversationMember.query.filter_by(
                conversation_id=conversation.id,
                user_id=current_user.id,
                is_active=True,
            ).first()
        if not conversation or not member:
            emit("error", {"message": "Conversation not found."})
            return
        room = f"conversation:{conversation.public_id}"
        join_room(room)
        emit("conversation_joined", {"conversation": conversation.public_id})

    @socketio.on("leave_conversation")
    def leave_conversation(data):
        public_id = (data or {}).get("conversation")
        if public_id:
            leave_room(f"conversation:{public_id}")

    @socketio.on("conversation_typing")
    def conversation_typing(data):
        if not current_user.is_authenticated:
            return
        public_id = (data or {}).get("conversation")
        from app.models import Conversation, ConversationMember

        conversation = Conversation.query.filter_by(public_id=public_id).first()
        if not conversation:
            return
        member = ConversationMember.query.filter_by(
            conversation_id=conversation.id,
            user_id=current_user.id,
            is_active=True,
        ).first()
        if not member:
            return
        emit(
            "conversation_typing",
            {"conversation": conversation.public_id, "user_id": current_user.id, "username": current_user.username},
            room=f"conversation:{conversation.public_id}",
            include_self=False,
        )


def emit_notification(user_id, payload):
    if socketio:
        socketio.emit("notification", payload, room=f"user:{user_id}")


def emit_conversation_event(public_id, event, payload):
    if socketio and public_id:
        socketio.emit(event, payload, room=f"conversation:{public_id}")
