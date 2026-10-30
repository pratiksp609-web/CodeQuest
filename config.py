import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    # MySQL example: mysql+pymysql://user:password@localhost:3306/learnopt
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "learnopt.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    MODEL_PATH = os.environ.get("MODEL_PATH", os.path.join(BASE_DIR, "risk_model.joblib"))
    QUESTIONS_PER_QUIZ = int(os.environ.get("QUESTIONS_PER_QUIZ", 10))
    PASS_MARK = 0.6

    # Email (OTP). If MAIL_SERVER is empty, codes are printed to the server console instead (dev mode).
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "CodeQuest <no-reply@codequest.local>")
    OTP_TTL_MINUTES = 10
    OTP_MAX_ATTEMPTS = 5
    OTP_RESEND_SECONDS = 60

    # Code judge. Runs submissions as local subprocesses with time and memory limits.
    # For a public deployment, run the judge inside a container or use a sandbox service.
    JUDGE_TIME_LIMIT = float(os.environ.get("JUDGE_TIME_LIMIT", 3))
    JUDGE_MEMORY_MB = int(os.environ.get("JUDGE_MEMORY_MB", 512))
