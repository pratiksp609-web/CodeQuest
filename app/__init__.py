import secrets
from datetime import date

from flask import Flask, abort, redirect, request, session, url_for
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"

# Pages a signed-in user can open before finishing verification / account setup.
OPEN_ENDPOINTS = {"static", "main.logout", "main.verify", "main.resend_otp", "main.onboarding", "main.index"}


def create_app(config_object="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_object)
    db.init_app(app)
    login_manager.init_app(app)

    from . import models
    from .routes import bp
    app.register_blueprint(bp)

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(models.User, int(uid))

    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def check_csrf():
        if request.method == "POST" and not app.config.get("TESTING_SKIP_CSRF"):
            sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
            if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
                abort(400, "Your session expired. Go back, refresh the page and try again.")

    @app.before_request
    def gate_and_mark_attendance():
        if not current_user.is_authenticated:
            return None
        if request.endpoint not in OPEN_ENDPOINTS:
            if not current_user.email_verified:
                return redirect(url_for("main.verify"))
            if not current_user.is_instructor and not current_user.profile_complete:
                return redirect(url_for("main.onboarding"))
        # Any day a student uses the platform counts as attendance.
        if not current_user.is_instructor and current_user.profile_complete:
            today = date.today()
            if not models.Attendance.query.filter_by(user_id=current_user.id, day=today).first():
                db.session.add(models.Attendance(user_id=current_user.id, day=today))
                db.session.commit()
        return None

    with app.app_context():
        db.create_all()
    return app
