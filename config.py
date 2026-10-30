import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _database_url():
    """Accepts the URL formats hosting providers hand out (mysql://, mysql2://) and points them at PyMySQL."""
    url = os.environ.get("DATABASE_URL") or os.environ.get("MYSQL_URL")
    if not url:
        return "sqlite:///" + os.path.join(BASE_DIR, "learnopt.db")
    for prefix in ("mysql://", "mysql2://"):
        if url.startswith(prefix):
            url = "mysql+pymysql://" + url[len(prefix):]
    if url.startswith("mysql+pymysql://") and "charset=" not in url:
        url += ("&" if "?" in url else "?") + "charset=utf8mb4"
    return url


IS_PRODUCTION = os.environ.get("APP_ENV", "development").lower() == "production"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    # MySQL example: mysql+pymysql://user:password@localhost:3306/learnopt
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Production hardening (APP_ENV=production): HTTPS-only cookies, trusted proxy headers.
    IS_PRODUCTION = IS_PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    REMEMBER_COOKIE_SECURE = IS_PRODUCTION
    REMEMBER_COOKIE_HTTPONLY = True
    PREFERRED_URL_SCHEME = "https" if IS_PRODUCTION else "http"
    MAX_CONTENT_LENGTH = 1024 * 1024
    TRUST_PROXY_HOPS = int(os.environ.get("TRUST_PROXY_HOPS", 1 if IS_PRODUCTION else 0))
    # Rate limits. memory:// is per process; set redis://... when running several app servers.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
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
