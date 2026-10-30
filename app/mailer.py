import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def send_mail(to, subject, body):
    """Sends through SMTP when configured. Otherwise prints the message to the console and keeps
    it in app.extensions["outbox"] so development and tests work without an email account."""
    cfg = current_app.config
    if not cfg.get("MAIL_SERVER"):
        current_app.extensions.setdefault("outbox", []).append({"to": to, "subject": subject, "body": body})
        current_app.logger.warning("DEV MAIL to %s | %s\n%s", to, subject, body)
        print(f"\n===== DEV MAIL to {to} =====\n{subject}\n{body}\n=============================\n", flush=True)
        return True
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["MAIL_FROM"], to, subject
    msg.set_content(body)
    try:
        if cfg["MAIL_USE_SSL"]:
            server = smtplib.SMTP_SSL(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], context=ssl.create_default_context(), timeout=15)
        else:
            server = smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=15)
            if cfg["MAIL_USE_TLS"]:
                server.starttls(context=ssl.create_default_context())
        with server:
            if cfg["MAIL_USERNAME"]:
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        current_app.logger.error("Mail to %s failed: %s", to, e)
        return False
