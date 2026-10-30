import logging
import secrets
from datetime import date

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# Pages a signed-in user can open before finishing verification / account setup.
OPEN_ENDPOINTS = {"static", "main.logout", "main.verify", "main.resend_otp", "main.onboarding", "main.index", "healthz",
                  "main.forgot", "main.reset_password"}


def create_app(config_object="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_object)
    if app.config["IS_PRODUCTION"] and app.config["SECRET_KEY"] in ("", "dev-change-me"):
        raise RuntimeError("Set the SECRET_KEY environment variable to a long random value in production.")
    if app.config["TRUST_PROXY_HOPS"]:
        n = app.config["TRUST_PROXY_HOPS"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)
    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    from . import judge, models
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

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if app.config["IS_PRODUCTION"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return resp

    @app.route("/healthz")
    def healthz():
        try:
            db.session.execute(text("SELECT 1"))
            database = "ok"
        except Exception as e:  # noqa: BLE001
            database = f"error: {type(e).__name__}"
        status = {"database": database, "judge_languages": sorted(judge.available()), "judge_isolation": judge.isolation()}
        return jsonify(status), 200 if database == "ok" else 503

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(429)
    @app.errorhandler(500)
    def error_page(e):
        code = getattr(e, "code", 500) or 500
        if request.path.startswith("/problems/") and request.method == "POST":
            return jsonify({"error": getattr(e, "description", "Error")}), code
        titles = {400: "Something went wrong with that request", 403: "You don't have access to this page",
                  404: "Page not found", 429: "Slow down a little", 500: "Something broke on our side"}
        detail = getattr(e, "description", "") if code in (400, 429) else ""
        return render_template("error.html", code=code, title=titles.get(code, "Error"), detail=detail), code

    with app.app_context():
        db.create_all()
        app.logger.info("Judge languages: %s | isolation: %s", ", ".join(sorted(judge.available())), judge.isolation())
    return app
