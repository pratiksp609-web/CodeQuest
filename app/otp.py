import secrets
from datetime import datetime, timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .mailer import send_mail
from .models import EmailOTP


def _latest(user, purpose="verify"):
    return (EmailOTP.query.filter_by(user_id=user.id, used=False, purpose=purpose)
            .order_by(EmailOTP.created_at.desc()).first())


def seconds_until_resend(user, purpose="verify"):
    last = _latest(user, purpose)
    if not last:
        return 0
    wait = current_app.config["OTP_RESEND_SECONDS"] - (datetime.utcnow() - last.created_at).total_seconds()
    return max(0, int(wait))


def issue(user, purpose="verify"):
    """Creates a new 6-digit code (invalidating older ones for the same purpose) and emails it."""
    EmailOTP.query.filter_by(user_id=user.id, used=False, purpose=purpose).update({"used": True})
    code = f"{secrets.randbelow(10**6):06d}"
    ttl = current_app.config["OTP_TTL_MINUTES"]
    db.session.add(EmailOTP(user_id=user.id, code_hash=generate_password_hash(code), purpose=purpose,
                            expires_at=datetime.utcnow() + timedelta(minutes=ttl)))
    db.session.commit()
    if purpose == "reset":
        body = (f"Hi {user.name},\n\nYour CodeQuest password reset code is: {code}\n\n"
                f"It expires in {ttl} minutes. If you didn't ask to reset your password, ignore this email.\n")
        return send_mail(user.email, f"{code} is your CodeQuest password reset code", body)
    body = (f"Hi {user.name},\n\nYour CodeQuest verification code is: {code}\n\n"
            f"It expires in {ttl} minutes. If you didn't sign up, ignore this email.\n")
    return send_mail(user.email, f"{code} is your CodeQuest verification code", body)


def verify(user, code, purpose="verify"):
    """Returns (ok, message). A correct code also marks the email as verified, since it proves inbox access."""
    otp = _latest(user, purpose)
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
