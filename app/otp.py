import secrets
from datetime import datetime, timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .mailer import send_mail
from .models import EmailOTP


def _latest(user):
    return EmailOTP.query.filter_by(user_id=user.id, used=False).order_by(EmailOTP.created_at.desc()).first()


def seconds_until_resend(user):
    last = _latest(user)
    if not last:
        return 0
    wait = current_app.config["OTP_RESEND_SECONDS"] - (datetime.utcnow() - last.created_at).total_seconds()
    return max(0, int(wait))


def issue(user):
    """Creates a new 6-digit code (invalidating older ones) and emails it."""
    EmailOTP.query.filter_by(user_id=user.id, used=False).update({"used": True})
    code = f"{secrets.randbelow(10**6):06d}"
    ttl = current_app.config["OTP_TTL_MINUTES"]
    db.session.add(EmailOTP(user_id=user.id, code_hash=generate_password_hash(code),
                            expires_at=datetime.utcnow() + timedelta(minutes=ttl)))
    db.session.commit()
    body = (f"Hi {user.name},\n\nYour CodeQuest verification code is: {code}\n\n"
            f"It expires in {ttl} minutes. If you didn't sign up, ignore this email.\n")
    return send_mail(user.email, f"{code} is your CodeQuest verification code", body)


def verify(user, code):
    """Returns (ok, message)."""
    otp = _latest(user)
    if not otp:
        return False, "No active code. Send a new one."
    if otp.expires_at < datetime.utcnow():
        otp.used = True
        db.session.commit()
        return False, "That code has expired. Send a new one."
    if otp.attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
        otp.used = True
        db.session.commit()
        return False, "Too many wrong tries. Send a new code."
    otp.attempts += 1
    if not check_password_hash(otp.code_hash, (code or "").strip()):
        db.session.commit()
        left = current_app.config["OTP_MAX_ATTEMPTS"] - otp.attempts
        return False, f"Incorrect code. {left} tries left."
    otp.used = True
    user.email_verified = True
    db.session.commit()
    return True, "Email verified."
