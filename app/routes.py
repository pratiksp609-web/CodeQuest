import csv
import io
from datetime import datetime
from functools import wraps

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from . import analytics as an
from . import db, ml
from .models import Attempt, AttemptAnswer, Language, Question, Topic, User
from .recommend import pick_questions, recommendations

bp = Blueprint("main", __name__)


def instructor_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if not current_user.is_instructor:
            abort(403)
        return f(*a, **kw)
    return wrapper


# ---------- auth ----------

@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.instructor" if current_user.is_instructor else "main.dashboard"))
    langs = Language.query.order_by(Language.name).all()
    return render_template("index.html", languages=langs)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if not name or not email or len(pw) < 6:
            flash("Enter a name, an email and a password of at least 6 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
        else:
            u = User(name=name, email=email, role="student")
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            return redirect(url_for("main.tests"))
    return render_template("auth.html", mode="register")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if u and u.check_password(request.form.get("password", "")):
            login_user(u, remember=True)
            return redirect(request.args.get("next") or url_for("main.index"))
        flash("Invalid email or password.", "error")
    return render_template("auth.html", mode="login")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.index"))


# ---------- tests ----------

@bp.route("/tests")
@login_required
def tests():
    langs = Language.query.order_by(Language.name).all()
    att = an.attempts_df([current_user.id])
    summary = {r["language"]: r for r in an.language_summary(att)}
    counts = dict(db.session.query(Topic.language_id, db.func.count(Question.id)).join(Question).group_by(Topic.language_id).all())
    return render_template("tests.html", languages=langs, summary=summary, counts=counts,
                           preselect=request.args.get("lang"))


@bp.route("/tests/<slug>/start", methods=["POST"])
@login_required
def start_test(slug):
    lang = Language.query.filter_by(slug=slug).first_or_404()
    mode = request.form.get("mode", "standard")
    topic_id = request.form.get("topic_id", type=int) or None
    n = current_app.config["QUESTIONS_PER_QUIZ"]
    answers = an.answers_df([current_user.id])
    mastery = an.topic_mastery(answers)
    seen = set(answers["question_id"]) if not answers.empty else set()
    questions = pick_questions(lang, n, mode=mode, mastery=mastery, seen_ids=seen, topic_id=topic_id)
    if not questions:
        flash("No questions available for that selection yet.", "error")
        return redirect(url_for("main.tests"))
    attempt = Attempt(user_id=current_user.id, language_id=lang.id, mode=mode,
                      total=len(questions), question_ids=[q.id for q in questions])
    db.session.add(attempt)
    db.session.commit()
    return redirect(url_for("main.take_test", attempt_id=attempt.id))


def _own_attempt(attempt_id):
    a = db.session.get(Attempt, attempt_id) or abort(404)
    if a.user_id != current_user.id and not current_user.is_instructor:
        abort(403)
    return a


@bp.route("/attempt/<int:attempt_id>", methods=["GET", "POST"])
@login_required
def take_test(attempt_id):
    attempt = _own_attempt(attempt_id)
    if attempt.finished_at:
        return redirect(url_for("main.result", attempt_id=attempt.id))
    qs = {q.id: q for q in Question.query.filter(Question.id.in_(attempt.question_ids))}
    questions = [qs[i] for i in attempt.question_ids if i in qs]

    if request.method == "POST":
        score = 0
        for q in questions:
            raw = request.form.get(f"q{q.id}")
            chosen = int(raw) if raw is not None and raw.isdigit() else None
            ok = chosen == q.answer_index
            score += ok
            db.session.add(AttemptAnswer(attempt_id=attempt.id, question_id=q.id, chosen_index=chosen, is_correct=ok))
        attempt.score = score
        attempt.finished_at = datetime.utcnow()
        attempt.duration_s = max(1, request.form.get("elapsed", type=int) or
                                 int((attempt.finished_at - attempt.started_at).total_seconds()))
        db.session.commit()
        return redirect(url_for("main.result", attempt_id=attempt.id))
    return render_template("take_test.html", attempt=attempt, questions=questions,
                           seconds=len(questions) * 60)


@bp.route("/attempt/<int:attempt_id>/result")
@login_required
def result(attempt_id):
    attempt = _own_attempt(attempt_id)
    if not attempt.finished_at:
        return redirect(url_for("main.take_test", attempt_id=attempt.id))
    by_topic = {}
    for a in attempt.answers:
        t = by_topic.setdefault(a.question.topic.name, [0, 0])
        t[0] += a.is_correct
        t[1] += 1
    passed = attempt.score / attempt.total >= current_app.config["PASS_MARK"]
    return render_template("result.html", attempt=attempt, by_topic=by_topic, passed=passed)


# ---------- dashboards ----------

def _student_context(user):
    att = an.attempts_df([user.id])
    ans = an.answers_df([user.id])
    days = an.attendance_df([user.id])
    feats = an.student_features(user.id)
    pred = ml.predict(feats)
    mastery = an.topic_mastery(ans)
    langs = an.language_summary(att)
    return {
        "student": user,
        "features": feats,
        "prediction": pred,
        "timeline": an.score_timeline(att),
        "languages": langs,
        "mastery": mastery.to_dict("records"),
        "attendance": an.attendance_series(days),
        "recs": recommendations(feats, mastery, langs, pred),
        "recent": Attempt.query.filter(Attempt.user_id == user.id, Attempt.finished_at.isnot(None))
                               .order_by(Attempt.started_at.desc()).limit(8).all(),
        "pass_mark": current_app.config["PASS_MARK"] * 100,
    }


@bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_instructor:
        return redirect(url_for("main.instructor"))
    return render_template("dashboard.html", **_student_context(current_user))


@bp.route("/instructor/student/<int:user_id>")
@instructor_required
def student_detail(user_id):
    user = db.session.get(User, user_id) or abort(404)
    return render_template("dashboard.html", viewing_as_instructor=True, **_student_context(user))


def _class_rows():
    studs = an.students()
    ids = [s.id for s in studs]
    att, ans, days = an.attempts_df(ids), an.answers_df(ids), an.attendance_df(ids)
    last = an.last_active(days, att)
    rows = []
    for s in studs:
        a = att[att["user_id"] == s.id] if not att.empty else att
        f = None
        if not a.empty:
            d = days.loc[days["user_id"] == s.id, "day"] if not days.empty else None
            f = an.compute_features(a, ans[ans["user_id"] == s.id], d, window_end=datetime.utcnow())
        p = ml.predict(f)
        rows.append({"student": s, "features": f, "prediction": p, "last_active": last.get(s.id)})
    return rows, att, ans, days


@bp.route("/instructor")
@instructor_required
def instructor():
    rows, att, ans, days = _class_rows()
    active = [r for r in rows if r["features"]]
    at_risk = sorted([r for r in active if r["prediction"]["level"] == "high"], key=lambda r: -r["prediction"]["risk"])
    mastery = an.topic_mastery(ans)
    lang_avg = an.language_summary(att)
    hardest = mastery.sort_values("mastery").head(6).to_dict("records") if not mastery.empty else []
    kpis = {
        "students": len(rows),
        "active": len(active),
        "tests": int(len(att)),
        "avg": round(float(att["pct"].mean() * 100), 1) if not att.empty else 0,
        "at_risk": len(at_risk),
        "attendance": round(100 * sum(r["features"]["attendance_rate"] for r in active) / len(active), 1) if active else 0,
    }
    bundle = ml.load()
    return render_template(
        "instructor.html", rows=sorted(active, key=lambda r: -r["prediction"]["risk"]), inactive=[r for r in rows if not r["features"]],
        at_risk=at_risk, kpis=kpis, languages=lang_avg, hardest=hardest,
        trend=an.weekly_trend(att), attendance=an.attendance_series(days, n_students=len(rows) or None),
        distribution=an.score_distribution([r["features"]["avg_pct"] for r in active]),
        risk_counts={lvl: sum(1 for r in active if r["prediction"]["level"] == lvl) for lvl in ("low", "medium", "high")},
        model=bundle,
    )


@bp.route("/instructor/train", methods=["POST"])
@instructor_required
def train_model():
    res = ml.train()
    if res["ok"]:
        m = res["metrics"]
        flash(f"Model retrained on {m['train_size'] + m['test_size']} students. Holdout accuracy {m['accuracy']:.0%}, "
              f"ROC AUC {m['roc_auc']}, score error ±{m['score_mae_pct']} pts.", "success")
    else:
        flash(res["message"], "error")
    return redirect(url_for("main.instructor"))


@bp.route("/instructor/report.csv")
@instructor_required
def report_csv():
    rows, *_ = _class_rows()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["student", "email", "tests", "avg_pct", "recent_pct", "trend", "attendance_rate",
                "predicted_next_pct", "risk_probability", "risk_level", "last_active"])
    for r in rows:
        f, p = r["features"], r["prediction"]
        w.writerow([r["student"].name, r["student"].email,
                    f["n_attempts"] if f else 0,
                    round(f["avg_pct"] * 100, 1) if f else "", round(f["recent_pct"] * 100, 1) if f else "",
                    round(f["trend"] * 100, 2) if f else "", round(f["attendance_rate"] * 100, 1) if f else "",
                    p["predicted_pct"] if p else "", p["risk"] if p else "", p["level"] if p else "",
                    r["last_active"].strftime("%Y-%m-%d") if r["last_active"] is not None else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=class_report.csv"})
