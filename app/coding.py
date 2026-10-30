"""Coding problems: list, solve in the browser, run against samples, submit against all tests."""
import threading

from flask import abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from . import db, judge
from .models import Problem, Submission
from .routes import bp

MAX_CODE = 64 * 1024
_slots = threading.BoundedSemaphore(4)  # concurrent judge runs per server process


def _status_map(user_id):
    status = {}
    for pid, verdict in db.session.query(Submission.problem_id, Submission.verdict).filter_by(user_id=user_id):
        if verdict == "Accepted":
            status[pid] = "solved"
        else:
            status.setdefault(pid, "attempted")
    return status


@bp.route("/problems")
@login_required
def problems():
    q = Problem.query
    diff = request.args.get("difficulty")
    tag = request.args.get("tag")
    interview = request.args.get("interview") == "1"
    if diff in ("Easy", "Medium", "Hard"):
        q = q.filter_by(difficulty=diff)
    if interview:
        q = q.filter_by(interview=True)
    items = q.all()
    if tag:
        items = [p for p in items if tag in (p.tags or [])]
    order = {"Easy": 0, "Medium": 1, "Hard": 2}
    items.sort(key=lambda p: (order[p.difficulty], p.title))
    stats = {pid: (acc, tot) for pid, acc, tot in db.session.query(
        Submission.problem_id,
        db.func.sum(db.case((Submission.verdict == "Accepted", 1), else_=0)),
        db.func.count(Submission.id)).group_by(Submission.problem_id)}
    status = _status_map(current_user.id)
    if request.args.get("status") in ("solved", "attempted", "todo"):
        want = request.args["status"]
        items = [p for p in items if status.get(p.id, "todo") == want]
    tags = sorted({t for p in Problem.query.all() for t in (p.tags or [])})
    solved = sum(1 for v in status.values() if v == "solved")
    return render_template("problems.html", problems=items, stats=stats, status=status, tags=tags, solved=solved,
                           total=Problem.query.count(), args=request.args)


def _default_lang(available):
    for slug in current_user.preferred_languages or []:
        if slug in available:
            return slug
    return "python" if "python" in available else next(iter(available), None)


@bp.route("/problems/<slug>")
@login_required
def problem(slug):
    p = Problem.query.filter_by(slug=slug).first_or_404()
    available = judge.available()
    subs = (Submission.query.filter_by(user_id=current_user.id, problem_id=p.id)
            .order_by(Submission.created_at.desc()).limit(20).all())
    last_code = {}
    for s in reversed(subs):
        last_code[s.language] = s.code
    langs = {k: {"label": v["label"], "mode": v["mode"], "template": judge.TEMPLATES[k]} for k, v in available.items()}
    return render_template("problem.html", p=p, langs=langs, default_lang=_default_lang(available),
                           last_code=last_code, submissions=subs,
                           solved=any(s.verdict == "Accepted" for s in subs))


def _read_payload(p):
    data = request.get_json(silent=True) or {}
    lang, code = data.get("language"), data.get("code") or ""
    if lang not in judge.available():
        abort(400, "Unsupported language")
    if not code.strip() or len(code) > MAX_CODE:
        abort(400, "Code is empty or too long")
    return data, lang, code


def _execute(lang, code, tests):
    if not _slots.acquire(timeout=20):
        abort(503, "The judge is busy. Try again in a moment.")
    try:
        return judge.execute(lang, code, tests, time_limit=current_app.config["JUDGE_TIME_LIMIT"],
                             mem_mb=current_app.config["JUDGE_MEMORY_MB"])
    finally:
        _slots.release()


@bp.route("/problems/<slug>/run", methods=["POST"])
@login_required
def run_code(slug):
    p = Problem.query.filter_by(slug=slug).first_or_404()
    data, lang, code = _read_payload(p)
    custom = data.get("input")
    tests = [{"input": custom if custom.endswith("\n") else custom + "\n", "output": None}] if custom else \
        [{"input": t["input"], "output": t["output"]} for t in p.samples]
    return jsonify(_execute(lang, code, tests))


@bp.route("/problems/<slug>/submit", methods=["POST"])
@login_required
def submit_code(slug):
    p = Problem.query.filter_by(slug=slug).first_or_404()
    _, lang, code = _read_payload(p)
    res = _execute(lang, code, [{"input": t["input"], "output": t["output"]} for t in p.tests])
    sub = Submission(user_id=current_user.id, problem_id=p.id, language=lang, code=code, verdict=res["verdict"],
                     passed=res["passed"], total=res["total"], runtime_ms=res["runtime_ms"])
    db.session.add(sub)
    db.session.commit()
    # Hide hidden test data; show details only for samples and the first failing test's verdict.
    for t, r in zip(p.tests, res["results"]):
        r["hidden"] = not t.get("sample")
        if r["hidden"]:
            r.update(input=None, expected=None, output=None, stderr=r["stderr"][:300] if r["verdict"] == "Runtime Error" else "")
    res["submission_id"] = sub.id
    return jsonify(res)


@bp.route("/submissions/<int:sid>")
@login_required
def submission(sid):
    s = db.session.get(Submission, sid) or abort(404)
    if s.user_id != current_user.id and not current_user.is_instructor:
        abort(403)
    return render_template("submission.html", s=s, label=judge.LANGS.get(s.language, {}).get("label", s.language))
