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
    email_verified = db.Column(db.Boolean, nullable=False, default=False)

    # Profile, filled in during account setup after the email is verified.
    birth_date = db.Column(db.Date)
    mobile = db.Column(db.String(10))  # 10 digits, stored without the +91 prefix
    university = db.Column(db.String(190))
    goal = db.Column(db.String(60))
    goal_detail = db.Column(db.String(255))
    purpose = db.Column(db.String(20))  # knowledge | job
    preferred_languages = db.Column(db.JSON, default=list)  # language slugs
    profile_complete = db.Column(db.Boolean, nullable=False, default=False)

    attempts = db.relationship("Attempt", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_instructor(self):
        return self.role == "instructor"

    @property
    def wants_job(self):
        return self.purpose == "job"


class EmailOTP(db.Model):
    __tablename__ = "email_otps"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(20), nullable=False, default="verify")  # verify | reset
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0)
    used = db.Column(db.Boolean, default=False)


class Language(db.Model):
    __tablename__ = "languages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    docs_url = db.Column(db.String(255))
    category = db.Column(db.String(20), nullable=False, default="programming")  # programming | aptitude

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


class Problem(db.Model):
    """A coding problem judged on stdin/stdout test cases."""
    __tablename__ = "problems"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    title = db.Column(db.String(150), nullable=False)
    difficulty = db.Column(db.String(10), nullable=False)  # Easy | Medium | Hard
    tags = db.Column(db.JSON, default=list)
    statement = db.Column(db.Text, nullable=False)
    input_format = db.Column(db.Text)
    output_format = db.Column(db.Text)
    constraints = db.Column(db.Text)
    tests = db.Column(db.JSON, nullable=False)  # [{"input": str, "output": str, "sample": bool}]
    interview = db.Column(db.Boolean, default=False)

    submissions = db.relationship("Submission", back_populates="problem", cascade="all, delete-orphan")

    @property
    def samples(self):
        return [t for t in self.tests if t.get("sample")]


class Submission(db.Model):
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=False, index=True)
    language = db.Column(db.String(20), nullable=False)
    code = db.Column(db.Text, nullable=False)
    verdict = db.Column(db.String(40), nullable=False)
    passed = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    runtime_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    problem = db.relationship("Problem", back_populates="submissions")
    user = db.relationship("User")
