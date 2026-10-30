"""Pandas analytics pipeline: pulls data from MySQL/SQLite through SQLAlchemy and
turns it into features, mastery scores, trends and reports."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

from . import db
from .models import Attempt, AttemptAnswer, Attendance, Language, Question, Topic, User

FEATURES = [
    "avg_pct", "recent_pct", "trend", "n_attempts", "attendance_rate",
    "sec_per_question", "hard_accuracy", "weak_topic_ratio",
]


def _read(stmt):
    with db.engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def attempts_df(user_ids=None):
    stmt = (
        select(
            Attempt.id.label("attempt_id"), Attempt.user_id, Language.name.label("language"),
            Attempt.started_at, Attempt.score, Attempt.total, Attempt.duration_s,
        )
        .join(Language, Language.id == Attempt.language_id)
        .where(Attempt.finished_at.isnot(None), Attempt.total > 0)
        .order_by(Attempt.started_at)
    )
    if user_ids is not None:
        stmt = stmt.where(Attempt.user_id.in_(list(user_ids)))
    df = _read(stmt)
    if not df.empty:
        df["started_at"] = pd.to_datetime(df["started_at"])
        df["pct"] = df["score"] / df["total"]
    return df


def answers_df(user_ids=None):
    stmt = (
        select(
            AttemptAnswer.attempt_id, Attempt.user_id, Attempt.started_at,
            Language.name.label("language"), Topic.name.label("topic"), Topic.id.label("topic_id"),
            Topic.resource_url, Question.id.label("question_id"), Question.difficulty,
            AttemptAnswer.is_correct,
        )
        .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
        .join(Question, Question.id == AttemptAnswer.question_id)
        .join(Topic, Topic.id == Question.topic_id)
        .join(Language, Language.id == Topic.language_id)
        .where(Attempt.finished_at.isnot(None))
    )
    if user_ids is not None:
        stmt = stmt.where(Attempt.user_id.in_(list(user_ids)))
    df = _read(stmt)
    if not df.empty:
        df["started_at"] = pd.to_datetime(df["started_at"])
        df["is_correct"] = df["is_correct"].astype(bool)
    return df


def attendance_df(user_ids=None):
    stmt = select(Attendance.user_id, Attendance.day)
    if user_ids is not None:
        stmt = stmt.where(Attendance.user_id.in_(list(user_ids)))
    df = _read(stmt)
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df


def topic_mastery(answers):
    """Difficulty-weighted accuracy per language/topic (0..1)."""
    if answers.empty:
        return pd.DataFrame(columns=["language", "topic", "topic_id", "resource_url", "mastery", "answered"])
    a = answers.assign(w=answers["difficulty"], wc=answers["difficulty"] * answers["is_correct"])
    g = a.groupby(["language", "topic", "topic_id", "resource_url"], dropna=False).agg(
        wc=("wc", "sum"), w=("w", "sum"), answered=("is_correct", "size")
    ).reset_index()
    g["mastery"] = (g["wc"] / g["w"]).round(3)
    return g.drop(columns=["wc", "w"]).sort_values("mastery")


def compute_features(attempts, answers, attendance_days, window_end=None, window_days=30):
    """Feature vector for one student, from their attempts/answers up to `window_end`."""
    if attempts.empty:
        return None
    window_end = pd.Timestamp(window_end or attempts["started_at"].max())
    pct = attempts["pct"].to_numpy()
    recent = pct[-3:]
    trend = float(np.polyfit(np.arange(len(pct)), pct, 1)[0]) if len(pct) >= 2 else 0.0
    start = window_end - pd.Timedelta(days=window_days)
    if attendance_days is not None and len(attendance_days):
        days = pd.to_datetime(pd.Series(attendance_days))
        active = days[(days > start) & (days <= window_end)].nunique()
    else:
        active = attempts["started_at"].dt.normalize().nunique()
    total_q = attempts["total"].sum()
    hard = answers[answers["difficulty"] == 3] if not answers.empty else answers
    mastery = topic_mastery(answers)
    return {
        "avg_pct": float(pct.mean()),
        "recent_pct": float(recent.mean()),
        "trend": trend,
        "n_attempts": int(len(pct)),
        "attendance_rate": min(1.0, active / window_days),
        "sec_per_question": float(attempts["duration_s"].sum() / total_q) if total_q else 0.0,
        "hard_accuracy": float(hard["is_correct"].mean()) if len(hard) else float(pct.mean()),
        "weak_topic_ratio": float((mastery["mastery"] < 0.5).mean()) if len(mastery) else 0.0,
    }


def student_features(user_id):
    att = attempts_df([user_id])
    ans = answers_df([user_id])
    days = attendance_df([user_id])
    return compute_features(att, ans, days["day"] if not days.empty else None, window_end=pd.Timestamp.utcnow().tz_localize(None))


def score_timeline(attempts):
    if attempts.empty:
        return {"labels": [], "values": [], "languages": []}
    return {
        "labels": attempts["started_at"].dt.strftime("%b %d %H:%M").tolist(),
        "values": (attempts["pct"] * 100).round(1).tolist(),
        "languages": attempts["language"].tolist(),
    }


def language_summary(attempts):
    if attempts.empty:
        return []
    g = attempts.groupby("language").agg(avg=("pct", "mean"), best=("pct", "max"), tests=("pct", "size")).reset_index()
    g["avg"] = (g["avg"] * 100).round(1)
    g["best"] = (g["best"] * 100).round(1)
    return g.sort_values("avg", ascending=False).to_dict("records")


def attendance_series(attendance, days=30, n_students=None):
    """Daily active-student counts (or 0/1 for a single student) for the last `days` days."""
    end = pd.Timestamp(date.today())
    idx = pd.date_range(end - pd.Timedelta(days=days - 1), end, freq="D")
    if attendance.empty:
        counts = pd.Series(0, index=idx)
    else:
        counts = attendance.groupby("day")["user_id"].nunique().reindex(idx, fill_value=0)
    values = counts.tolist()
    if n_students:
        values = [round(100 * v / n_students, 1) for v in values]
    return {"labels": [d.strftime("%b %d") for d in idx], "values": values}


def weekly_trend(attempts, weeks=8):
    if attempts.empty:
        return {"labels": [], "values": [], "counts": []}
    df = attempts.set_index("started_at").sort_index()
    w = df["pct"].resample("W").agg(["mean", "size"]).tail(weeks)
    return {
        "labels": [d.strftime("%b %d") for d in w.index],
        "values": (w["mean"].fillna(0) * 100).round(1).tolist(),
        "counts": w["size"].astype(int).tolist(),
    }


def score_distribution(per_student_avg):
    bins = [0, 20, 40, 60, 80, 101]
    labels = ["0-20", "20-40", "40-60", "60-80", "80-100"]
    if len(per_student_avg) == 0:
        return {"labels": labels, "values": [0] * 5}
    cut = pd.cut(pd.Series(per_student_avg) * 100, bins=bins, labels=labels, right=False)
    return {"labels": labels, "values": cut.value_counts().reindex(labels, fill_value=0).astype(int).tolist()}


def last_active(attendance, attempts):
    out = {}
    if not attendance.empty:
        out.update(attendance.groupby("user_id")["day"].max().to_dict())
    if not attempts.empty:
        for uid, ts in attempts.groupby("user_id")["started_at"].max().items():
            if uid not in out or ts > out[uid]:
                out[uid] = ts
    return out


def students():
    return User.query.filter_by(role="student").order_by(User.name).all()


def recent_days(n):
    return date.today() - timedelta(days=n)
