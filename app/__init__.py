from datetime import date

from flask import Flask
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"


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

    @app.before_request
    def mark_attendance():
        # Any day a student uses the platform counts as attendance.
        if current_user.is_authenticated and not current_user.is_instructor:
            today = date.today()
            exists = models.Attendance.query.filter_by(user_id=current_user.id, day=today).first()
            if not exists:
                db.session.add(models.Attendance(user_id=current_user.id, day=today))
                db.session.commit()

    with app.app_context():
        db.create_all()
    return app
