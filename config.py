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
