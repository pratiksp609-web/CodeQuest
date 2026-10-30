import csv
import io
from datetime import date, datetime
from functools import wraps

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, session, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from . import analytics as an
from . import db, limiter, ml, otp
from .models import Attempt, AttemptAnswer, Language, Problem, Question, Submission, Topic, User
from .profile import GOALS, PURPOSES, age_on, parse_mobile, study_plan
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
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if not name or not email or len(pw) < 8:
            flash("Enter a name, an email and a password of at least 8 characters.", "error")
        elif pw != request.form.get("confirm", ""):
            flash("The passwords don't match.", "error")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered. Log in instead.", "error")
        else:
            u = User(name=name, email=email, role="student")
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            _send_code(u)
            return redirect(url_for("main.verify"))
    return render_template("auth.html", mode="register")


def _send_code(user):
    if otp.issue(user):
        flash(f"We sent a 6-digit code to {user.email}.", "success")
    else:
        flash("We couldn't send the email. Check the address or try again in a minute.", "error")


@bp.route("/verify", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@login_required
def verify():
    if current_user.email_verified:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        ok, msg = otp.verify(current_user, request.form.get("code", ""))
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("main.onboarding"))
    dev = not current_app.config.get("MAIL_SERVER")
    return render_template("verify.html", wait=otp.seconds_until_resend(current_user), dev=dev)


@bp.route("/verify/resend", methods=["POST"])
@limiter.limit("3 per minute; 10 per hour")
@login_required
def resend_otp():
    if current_user.email_verified:
        return redirect(url_for("main.index"))
    wait = otp.seconds_until_resend(current_user)
    if wait:
        flash(f"Please wait {wait} seconds before asking for a new code.", "error")
    else:
        _send_code(current_user)
    return redirect(url_for("main.verify"))


@bp.route("/onboarding", methods=["GET", "POST"])
@bp.route("/profile", methods=["GET", "POST"], endpoint="profile")
@login_required
def onboarding():
    if not current_user.email_verified:
        return redirect(url_for("main.verify"))
    if current_user.is_instructor:
        return redirect(url_for("main.instructor"))
    languages = Language.query.order_by(Language.category.desc(), Language.name).all()
    form = request.form if request.method == "POST" else None
    if form:
        errors = []
        name = form.get("name", "").strip()
        if not name:
            errors.append("Enter your name.")
        try:
            birth = date.fromisoformat(form.get("birth_date", ""))
            if not 10 <= age_on(birth) <= 100:
                errors.append("Enter a valid birth date.")
        except ValueError:
            birth = None
            errors.append("Enter your birth date.")
        mobile = parse_mobile(form.get("mobile"))
        if not mobile:
            errors.append("Enter a valid 10-digit Indian mobile number (it should start with 6, 7, 8 or 9).")
        slugs = {l.slug for l in languages}
        chosen = [s for s in form.getlist("languages") if s in slugs]
        if not chosen:
            errors.append("Pick at least one language.")
        university = form.get("university", "").strip()
        if not university:
            errors.append("Enter your university or college.")
        goal = form.get("goal")
        if goal not in GOALS:
            errors.append("Choose a goal.")
        purpose = form.get("purpose")
        if purpose not in PURPOSES:
            errors.append("Tell us why you're taking tests.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            first_time = not current_user.profile_complete
            current_user.name = name
            current_user.birth_date = birth
            current_user.mobile = mobile
            current_user.preferred_languages = chosen
            current_user.university = university
            current_user.goal = goal
            current_user.goal_detail = form.get("goal_detail", "").strip()[:255] or None
            current_user.purpose = purpose
            current_user.profile_complete = True
            db.session.commit()
            flash("You're all set. Start with a demo test below." if first_time else "Profile saved.", "success")
            return redirect(url_for("main.tests") if first_time else url_for("main.dashboard"))
    return render_template("onboarding.html", languages=languages, goals=GOALS, purposes=PURPOSES, form=form,
                           editing=current_user.profile_complete)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 60 per hour", methods=["POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if u and u.check_password(request.form.get("password", "")):
            login_user(u, remember=True)
            return redirect(request.args.get("next") or url_for("main.index"))
        flash("Invalid email or password.", "error")
    return render_template("auth.html", mode="login")


@bp.route("/forgot", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        u = User.query.filter_by(email=email).first()
        if u and not otp.seconds_until_resend(u, "reset"):
            otp.issue(u, "reset")
        session["reset_email"] = email
        # Same message whether or not the account exists, so the form can't be used to find accounts.
        flash("If that email has an account, we've sent it a 6-digit reset code.", "success")
        return redirect(url_for("main.reset_password"))
    return render_template("forgot.html", step="email")


@bp.route("/reset", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def reset_password():
    email = session.get("reset_email")
    if not email:
        return redirect(url_for("main.forgot"))
    if request.method == "POST":
        pw = request.form.get("password", "")
        u = User.query.filter_by(email=email).first()
        if len(pw) < 8 or pw != request.form.get("confirm", ""):
            flash("Use a password of at least 8 characters, typed the same twice.", "error")
        elif not u:
            flash("Incorrect code.", "error")
        else:
            ok, msg = otp.verify(u, request.form.get("code", ""), "reset")
            if ok:
                u.set_password(pw)
                db.session.commit()
                session.pop("reset_email", None)
                flash("Password changed. Log in with your new password.", "success")
                return redirect(url_for("main.login"))
            flash(msg, "error")
    return render_template("forgot.html", step="code", email=email,
                           dev=not current_app.config.get("MAIL_SERVER"))


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
    mine = current_user.preferred_languages or []
    groups = [
        ("Your languages", sorted([l for l in langs if l.slug in mine and l.category == "programming"], key=lambda l: mine.index(l.slug))),
        ("Aptitude", [l for l in langs if l.category == "aptitude"]),
        ("More languages", [l for l in langs if l.slug not in mine and l.category == "programming"]),
    ]
    return render_template("tests.html", groups=[g for g in groups if g[1]], summary=summary, counts=counts,
                           preselect=request.args.get("lang"))


@bp.route("/tests/<slug>/start", methods=["POST"])
@login_required
def start_test(slug):
    lang = Language.query.filter_by(slug=slug).first_or_404()
    mode = request.form.get("mode", "standard")
    if mode not in ("standard", "adaptive", "demo"):
        mode = "standard"
    topic_id = request.form.get("topic_id", type=int) or None
    n = 5 if mode == "demo" else current_app.config["QUESTIONS_PER_QUIZ"]
    answers = an.answers_df([current_user.id])
    mastery = an.topic_mastery(answers)
    seen = set(answers["question_id"]) if not answers.empty else set()
    questions = pick_questions(lang, n, mode=mode, mastery=mastery, seen_ids=seen, topic_id=topic_id,
                               prefer_harder=current_user.wants_job)
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
                           seconds=len(questions) * (90 if attempt.language.category == "aptitude" else 60))


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
    all_langs = {l.slug: l for l in Language.query.all()}
    tested = {r["language"] for r in langs}
    subs = Submission.query.filter_by(user_id=user.id).all()
    solved = {s.problem_id for s in subs if s.verdict == "Accepted"}
    by_diff = {d: 0 for d in ("Easy", "Medium", "Hard")}
    for p in Problem.query.filter(Problem.id.in_(solved)) if solved else []:
        by_diff[p.difficulty] += 1
    coding = {"solved": len(solved), "attempted": len({s.problem_id for s in subs}), "submissions": len(subs),
              "by_diff": by_diff, "total": Problem.query.count()}
    return {
        "plan": study_plan(user, all_langs) if user.profile_complete else None,
        "demo_langs": [all_langs[s] for s in (user.preferred_languages or []) if s in all_langs and all_langs[s].name not in tested],
        "coding": coding,
        "goal_label": GOALS.get(user.goal), "purpose_label": PURPOSES.get(user.purpose),
        "student": user,
        "features": feats,
        "prediction": pred,
        "timeline": an.score_timeline(att),
        "languages": langs,
        "mastery": mastery.to_dict("records"),
        "attendance": an.attendance_series(days),
        "recs": recommendations(feats, mastery, langs, pred, user=user, coding=coding),
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
    solved = dict(db.session.query(Submission.user_id, db.func.count(db.distinct(Submission.problem_id)))
                  .filter(Submission.verdict == "Accepted").group_by(Submission.user_id).all())
    rows = []
    for s in studs:
        a = att[att["user_id"] == s.id] if not att.empty else att
        f = None
        if not a.empty:
            d = days.loc[days["user_id"] == s.id, "day"] if not days.empty else None
            f = an.compute_features(a, ans[ans["user_id"] == s.id], d, window_end=datetime.utcnow())
        p = ml.predict(f)
        rows.append({"student": s, "features": f, "prediction": p, "last_active": last.get(s.id),
                     "solved": solved.get(s.id, 0)})
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
        "solved": sum(r["solved"] for r in rows),
        "job_share": round(100 * sum(1 for r in rows if r["student"].purpose == "job") / len(rows)) if rows else 0,
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
    w.writerow(["student", "email", "mobile", "university", "goal", "purpose", "problems_solved", "tests", "avg_pct", "recent_pct", "trend", "attendance_rate",
                "predicted_next_pct", "risk_probability", "risk_level", "last_active"])
    for r in rows:
        f, p = r["features"], r["prediction"]
        st = r["student"]
        w.writerow([st.name, st.email, f"+91{st.mobile}" if st.mobile else "", st.university or "",
                    GOALS.get(st.goal, ""), st.purpose or "", r["solved"],
                    f["n_attempts"] if f else 0,
                    round(f["avg_pct"] * 100, 1) if f else "", round(f["recent_pct"] * 100, 1) if f else "",
                    round(f["trend"] * 100, 2) if f else "", round(f["attendance_rate"] * 100, 1) if f else "",
                    p["predicted_pct"] if p else "", p["risk"] if p else "", p["level"] if p else "",
                    r["last_active"].strftime("%Y-%m-%d") if r["last_active"] is not None else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=class_report.csv"})


from . import coding  # noqa: E402,F401  (registers the coding problem routes)
