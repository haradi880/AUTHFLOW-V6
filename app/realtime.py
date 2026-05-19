"""Optional Socket.IO realtime notifications.

When Flask-SocketIO is installed, production can run with Redis message queues
and emit events to room `user:<id>`. Without the dependency, the app falls back
to the existing polling APIs.
"""

try:
    from flask_socketio import SocketIO, emit, join_room
except Exception:  # pragma: no cover - optional dependency fallback
    SocketIO = None


socketio = SocketIO(cors_allowed_origins=[], async_mode="threading") if SocketIO else None


def init_realtime(app):
    if not socketio:
        app.logger.info("Flask-SocketIO unavailable; realtime notifications use polling fallback.")
        return
    socketio.init_app(app, message_queue=app.config.get("REDIS_URL") if app.config.get("TASK_QUEUE_ASYNC") else None)

    @socketio.on("join_notifications")
    def join_notifications(data):
        user_id = (data or {}).get("user_id")
        if user_id:
            join_room(f"user:{user_id}")
            emit("joined", {"room": f"user:{user_id}"})


def emit_notification(user_id, payload):
    if socketio:
        socketio.emit("notification", payload, room=f"user:{user_id}")
