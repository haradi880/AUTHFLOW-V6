import secrets
import string
from datetime import datetime, timedelta

from flask import current_app
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import OTPToken, User
from app.utils.emailer import send_otp_email, send_welcome_email


def normalize_email(email):
    return (email or "").strip().lower()


def generate_otp():
    return "".join(secrets.choice(string.digits) for _ in range(6))


def validate_password_strength(password):
    password = password or ""
    checks = [
        (len(password) >= 10, "Password must be at least 10 characters."),
        (any(char.islower() for char in password), "Password needs a lowercase letter."),
        (any(char.isupper() for char in password), "Password needs an uppercase letter."),
        (any(char.isdigit() for char in password), "Password needs a number."),
        (any(not char.isalnum() for char in password), "Password needs a symbol."),
    ]
    for passed, message in checks:
        if not passed:
            return message
    return None


def register_user(username, email, password):
    user = User(username=username.strip(), email=normalize_email(email), is_verified=False)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    code = issue_otp(user, "email_verification", commit=False)
    db.session.commit()
    send_otp_email(user.email, code)
    return user


def issue_otp(user, purpose, minutes=10, commit=True):
    OTPToken.query.filter_by(user_id=user.id, purpose=purpose, consumed_at=None).update(
        {"consumed_at": datetime.utcnow()}, synchronize_session=False
    )
    code = generate_otp()
    token = OTPToken(user_id=user.id, purpose=purpose, expires_at=datetime.utcnow() + timedelta(minutes=minutes))
    token.set_code(code)
    db.session.add(token)
    if commit:
        db.session.commit()
    return code


def verify_otp(user, purpose, code):
    token = (
        OTPToken.query.filter_by(user_id=user.id, purpose=purpose, consumed_at=None)
        .order_by(OTPToken.created_at.desc())
        .first()
    )
    if not token or not token.verify(code):
        return False
    token.consumed_at = datetime.utcnow()
    if purpose == "email_verification":
        user.is_verified = True
    db.session.commit()
    if purpose == "email_verification":
        send_welcome_email(user.email, user.username)
    return True


def authenticate_user(email, password):
    user = User.query.filter_by(email=normalize_email(email)).first()
    if not user:
        return None, "Invalid email or password."
    if user.is_locked():
        return user, "Account is temporarily locked. Please try again later."
    if not user.check_password(password):
        user.register_failed_login(
            current_app.config["MAX_LOGIN_ATTEMPTS"],
            current_app.config["LOGIN_LOCK_MINUTES"],
        )
        db.session.commit()
        return user, "Invalid email or password."
    if not user.is_verified:
        return user, "Please verify your email before logging in."
    user.clear_failed_logins()
    db.session.commit()
    return user, None


def start_password_reset(email):
    user = User.query.filter_by(email=normalize_email(email)).first()
    if not user:
        return None
    code = issue_otp(user, "password_reset")
    send_otp_email(user.email, code)
    return user


def reset_password(user, password):
    user.password_hash = generate_password_hash(password)
    user.clear_failed_logins()
    db.session.commit()
