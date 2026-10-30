from datetime import datetime, date

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")  # student | instructor
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attempts = db.relationship("Attempt", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_instructor(self):
        return self.role == "instructor"


class Language(db.Model):
    __tablename__ = "languages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    docs_url = db.Column(db.String(255))

    topics = db.relationship("Topic", back_populates="language", cascade="all, delete-orphan")


class Topic(db.Model):
    __tablename__ = "topics"
    id = db.Column(db.Integer, primary_key=True)
    language_id = db.Column(db.Integer, db.ForeignKey("languages.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    resource_url = db.Column(db.String(255))

    language = db.relationship("Language", back_populates="topics")
    questions = db.relationship("Question", back_populates="topic", cascade="all, delete-orphan")


class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    difficulty = db.Column(db.Integer, nullable=False, default=1)  # 1 easy, 2 medium, 3 hard
    text = db.Column(db.Text, nullable=False)
    code = db.Column(db.Text)
    options = db.Column(db.JSON, nullable=False)
    answer_index = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.Text)

    topic = db.relationship("Topic", back_populates="questions")


class Attempt(db.Model):
    __tablename__ = "attempts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    language_id = db.Column(db.Integer, db.ForeignKey("languages.id"), nullable=False)
    mode = db.Column(db.String(20), default="standard")  # standard | adaptive
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    score = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    duration_s = db.Column(db.Integer, default=0)
    question_ids = db.Column(db.JSON)

    user = db.relationship("User", back_populates="attempts")
    language = db.relationship("Language")
    answers = db.relationship("AttemptAnswer", back_populates="attempt", cascade="all, delete-orphan")

    @property
    def percent(self):
        return round(100 * self.score / self.total, 1) if self.total else 0.0


class AttemptAnswer(db.Model):
    __tablename__ = "attempt_answers"
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempts.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    chosen_index = db.Column(db.Integer)  # None = skipped
    is_correct = db.Column(db.Boolean, default=False)

    attempt = db.relationship("Attempt", back_populates="answers")
    question = db.relationship("Question")


class Attendance(db.Model):
    """One row per student per day they were active on the platform."""
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, default=date.today)
    __table_args__ = (db.UniqueConstraint("user_id", "day", name="uq_attendance_user_day"),)
