import hashlib
import secrets
from datetime import datetime, timedelta

from flask import request, session

from app.extensions import db
from app.models import LoginEvent, LoginSession
from app.utils.audit import AuditEventType, audit_log, get_client_ip


def _user_agent():
    return (request.headers.get("User-Agent") or "")[:500]


def device_fingerprint(ip_address=None, user_agent=None):
    raw = f"{ip_address or get_client_ip()}|{user_agent or _user_agent()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_device_label(user_agent):
    ua = user_agent or ""
    browser = "Browser"
    platform = "Device"
    for candidate in ("Edg", "Chrome", "Firefox", "Safari", "Opera"):
        if candidate in ua:
            browser = "Edge" if candidate == "Edg" else candidate
            break
    for candidate in ("Windows", "Android", "iPhone", "iPad", "Mac OS", "Linux"):
        if candidate in ua:
            platform = "macOS" if candidate == "Mac OS" else candidate
            break
    return f"{browser} on {platform}", browser, platform


def log_login_attempt(email, user=None, success=False, reason=None):
    ip_address = get_client_ip()
    user_agent = _user_agent()
    fingerprint = device_fingerprint(ip_address, user_agent)
    suspicious = False
    if success and user:
        recent_known = LoginSession.query.filter(
            LoginSession.user_id == user.id,
            LoginSession.fingerprint == fingerprint,
            LoginSession.created_at >= datetime.utcnow() - timedelta(days=90),
        ).first()
        suspicious = recent_known is None and LoginSession.query.filter_by(user_id=user.id).count() > 0

    event = LoginEvent(
        user_id=user.id if user else None,
        email=(email or "")[:255],
        event_type="login_success" if success else "login_failed",
        success=success,
        reason=(reason or "")[:160] if reason else None,
        ip_address=ip_address,
        user_agent=user_agent,
        fingerprint=fingerprint,
        suspicious=suspicious,
    )
    db.session.add(event)
    db.session.flush()
    audit_log(
        AuditEventType.LOGIN_SUCCESS if success else AuditEventType.LOGIN_FAILED,
        description="Successful login" if success else f"Failed login: {reason or 'invalid credentials'}",
        actor_id=user.id if user else None,
        actor_username=user.username if user else None,
        metadata={"email": email, "suspicious": suspicious},
        status_code=200 if success else 401,
    )
    return event


def create_login_session(user):
    ip_address = get_client_ip()
    user_agent = _user_agent()
    label, browser, platform = parse_device_label(user_agent)
    fingerprint = device_fingerprint(ip_address, user_agent)
    LoginSession.query.filter_by(user_id=user.id, is_current=True).update({"is_current": False})
    login_session = LoginSession(
        public_id=secrets.token_urlsafe(32),
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        device_label=label,
        browser=browser,
        platform=platform,
        fingerprint=fingerprint,
        is_current=True,
    )
    db.session.add(login_session)
    db.session.flush()
    session["login_session_id"] = login_session.public_id
    return login_session


def touch_current_session(user):
    public_id = session.get("login_session_id")
    if not public_id:
        return None
    login_session = LoginSession.query.filter_by(public_id=public_id, user_id=user.id).first()
    if not login_session or login_session.revoked_at:
        return None
    login_session.last_seen_at = datetime.utcnow()
    return login_session


def revoke_session(user, public_id):
    login_session = LoginSession.query.filter_by(public_id=public_id, user_id=user.id).first()
    if not login_session:
        return False
    login_session.revoked_at = datetime.utcnow()
    login_session.is_current = False
    db.session.commit()
    return True


def revoke_other_sessions(user):
    current_id = session.get("login_session_id")
    query = LoginSession.query.filter_by(user_id=user.id, revoked_at=None)
    if current_id:
        query = query.filter(LoginSession.public_id != current_id)
    count = 0
    for login_session in query.all():
        login_session.revoked_at = datetime.utcnow()
        login_session.is_current = False
        count += 1
    db.session.commit()
    return count


def revoke_all_sessions(user):
    count = 0
    for login_session in LoginSession.query.filter_by(user_id=user.id, revoked_at=None).all():
        login_session.revoked_at = datetime.utcnow()
        login_session.is_current = False
        count += 1
    db.session.commit()
    session.clear()
    return count
