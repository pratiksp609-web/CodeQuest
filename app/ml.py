"""Machine learning: predicts each student's upcoming test outcome and flags at-risk students.

Training data is built from history in the database: for every student with enough tests,
features are computed from their earlier tests (first 70%) and the label is how they did on
their later tests (last 30%). Two models are trained on the same features:
  * a RandomForestClassifier -> probability the student is at risk (future average < pass mark)
  * a GradientBoostingRegressor -> predicted future average score
"""
import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from flask import current_app
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import train_test_split

from . import analytics as an

MIN_ATTEMPTS = 6
_cache = {"bundle": None, "mtime": None}


def build_training_set(pass_mark):
    attempts = an.attempts_df()
    answers = an.answers_df()
    attendance = an.attendance_df()
    rows = []
    if attempts.empty:
        return pd.DataFrame()
    for uid, att in attempts.groupby("user_id"):
        att = att.sort_values("started_at")
        if len(att) < MIN_ATTEMPTS:
            continue
        cut = int(len(att) * 0.7)
        past, future = att.iloc[:cut], att.iloc[cut:]
        cutoff = past["started_at"].max()
        past_ans = answers[answers["attempt_id"].isin(past["attempt_id"])]
        days = attendance.loc[(attendance["user_id"] == uid) & (attendance["day"] <= cutoff), "day"] if not attendance.empty else None
        feats = an.compute_features(past, past_ans, days, window_end=cutoff)
        future_pct = float(future["pct"].mean())
        feats.update(user_id=uid, future_pct=future_pct, at_risk=int(future_pct < pass_mark))
        rows.append(feats)
    return pd.DataFrame(rows)


def train():
    pass_mark = current_app.config["PASS_MARK"]
    data = build_training_set(pass_mark)
    if len(data) < 10 or data["at_risk"].nunique() < 2:
        return {"ok": False, "message": f"Need at least 10 students with {MIN_ATTEMPTS}+ tests and both outcomes; have {len(data)}."}

    X, y_cls, y_reg = data[an.FEATURES].to_numpy(), data["at_risk"].to_numpy(), data["future_pct"].to_numpy()
    strat = y_cls if np.bincount(y_cls).min() >= 2 else None
    Xtr, Xte, ctr, cte, rtr, rte = train_test_split(X, y_cls, y_reg, test_size=0.25, random_state=42, stratify=strat)

    clf = RandomForestClassifier(n_estimators=300, max_depth=6, class_weight="balanced", random_state=42).fit(Xtr, ctr)
    reg = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42).fit(Xtr, rtr)

    proba = clf.predict_proba(Xte)[:, 1]
    metrics = {
        "train_size": int(len(Xtr)),
        "test_size": int(len(Xte)),
        "accuracy": round(float((clf.predict(Xte) == cte).mean()), 3),
        "roc_auc": round(float(roc_auc_score(cte, proba)), 3) if len(set(cte)) > 1 else None,
        "score_mae_pct": round(float(mean_absolute_error(rte, reg.predict(Xte)) * 100), 1),
        "at_risk_share": round(float(y_cls.mean()), 3),
    }
    # Refit on all data for serving.
    clf.fit(X, y_cls)
    reg.fit(X, y_reg)
    importances = sorted(zip(an.FEATURES, clf.feature_importances_.round(3).tolist()), key=lambda t: -t[1])
    bundle = {"clf": clf, "reg": reg, "features": an.FEATURES, "metrics": metrics,
              "importances": importances, "trained_at": datetime.utcnow().isoformat(timespec="seconds")}
    joblib.dump(bundle, current_app.config["MODEL_PATH"])
    _cache["bundle"] = None
    return {"ok": True, "metrics": metrics, "importances": importances}


def load():
    path = current_app.config["MODEL_PATH"]
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    if _cache["bundle"] is None or _cache["mtime"] != mtime:
        _cache["bundle"], _cache["mtime"] = joblib.load(path), mtime
    return _cache["bundle"]


def risk_level(p):
    return "high" if p >= 0.6 else "medium" if p >= 0.35 else "low"


def predict(features):
    """Returns {risk, level, predicted_pct, source}. Falls back to a transparent rule if no model."""
    if not features:
        return None
    bundle = load()
    if bundle is not None:
        x = np.array([[features[f] for f in bundle["features"]]])
        p = float(bundle["clf"].predict_proba(x)[0, 1])
        pred = float(np.clip(bundle["reg"].predict(x)[0], 0, 1))
        source = "model"
    else:
        pass_mark = current_app.config["PASS_MARK"]
        pred = float(np.clip(0.6 * features["recent_pct"] + 0.4 * features["avg_pct"] + 2 * features["trend"], 0, 1))
        p = float(np.clip((pass_mark - pred) * 3 + 0.5 - 0.4 * features["attendance_rate"], 0, 1))
        source = "rule"
    return {"risk": round(p, 3), "level": risk_level(p), "predicted_pct": round(pred * 100, 1), "source": source}
