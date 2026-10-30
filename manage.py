"""Command line helpers.

  python manage.py init          create tables and load the question bank
  python manage.py demo          add an instructor, a demo student and 120 simulated students
  python manage.py train         train the at-risk / score prediction models
  python manage.py create-instructor NAME EMAIL PASSWORD
"""
import math
import random
import sys
from datetime import date, datetime, timedelta

from app import create_app, db, ml
from app.models import Attempt, AttemptAnswer, Attendance, Language, Question, Topic, User
from app.question_bank import LANGUAGES


def load_questions():
    added = 0
    for name, spec in LANGUAGES.items():
        lang = Language.query.filter_by(slug=spec["slug"]).first()
        if not lang:
            lang = Language(name=name, slug=spec["slug"], description=spec["description"], docs_url=spec["docs_url"])
            db.session.add(lang)
            db.session.flush()
        topics = {t.name: t for t in lang.topics}
        for tname, url in spec["topics"].items():
            if tname not in topics:
                topics[tname] = Topic(language_id=lang.id, name=tname, resource_url=url)
                db.session.add(topics[tname])
        db.session.flush()
        existing = {q.text + (q.code or "") for t in topics.values() for q in t.questions}
        for tname, diff, text, code, options, ans, expl in spec["questions"]:
            if text + (code or "") in existing:
                continue
            db.session.add(Question(topic_id=topics[tname].id, difficulty=diff, text=text, code=code,
                                    options=options, answer_index=ans, explanation=expl))
            added += 1
    db.session.commit()
    print(f"Question bank ready ({added} new questions, {Question.query.count()} total).")


FIRST = ["Aarav", "Diya", "Rohan", "Ananya", "Kabir", "Isha", "Vihaan", "Meera", "Arjun", "Sara", "Neel", "Priya",
         "Omar", "Lena", "Yash", "Tara", "Dev", "Nisha", "Kiran", "Zoya", "Sam", "Ria", "Aditya", "Maya"]
LAST = ["Sharma", "Patel", "Iyer", "Khan", "Reddy", "Singh", "Joshi", "Das", "Mehta", "Nair", "Gupta", "Rao"]


def simulate_students(n=120, days=70, seed=7):
    """Simulated cohort so the dashboards and ML have history to work with. Each student has a hidden
    ability, an engagement level and a learning rate; engaged students improve, disengaged ones drift."""
    rng = random.Random(seed)
    langs = Language.query.all()
    by_lang = {l.id: Question.query.join(Topic).filter(Topic.language_id == l.id).all() for l in langs}
    start = date.today() - timedelta(days=days)
    for i in range(n):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"student{i + 1}@demo.local"
        if User.query.filter_by(email=email).first():
            continue
        u = User(name=name, email=email, role="student", created_at=datetime.combine(start, datetime.min.time()))
        u.set_password("demo123")
        db.session.add(u)
        db.session.flush()
        ability = rng.gauss(0.2, 0.9)
        engagement = min(0.85, max(0.05, rng.betavariate(2, 3)))
        learn = rng.gauss(0.03, 0.02) * (engagement / 0.4) - (0.025 if engagement < 0.2 else 0)
        fav = rng.sample(langs, k=rng.randint(1, 3))
        topic_skill = {}
        for d in range(days):
            day = start + timedelta(days=d)
            if rng.random() > engagement:
                continue
            db.session.add(Attendance(user_id=u.id, day=day))
            if rng.random() > 0.7:
                continue
            lang = rng.choice(fav)
            qs = rng.sample(by_lang[lang.id], k=min(10, len(by_lang[lang.id])))
            level = ability + learn * d
            ts = datetime.combine(day, datetime.min.time()) + timedelta(hours=rng.randint(8, 22), minutes=rng.randint(0, 59))
            a = Attempt(user_id=u.id, language_id=lang.id, mode=rng.choice(["standard", "adaptive"]),
                        started_at=ts, total=len(qs), question_ids=[q.id for q in qs])
            db.session.add(a)
            db.session.flush()
            score = 0
            for q in qs:
                ts_skill = topic_skill.setdefault(q.topic_id, rng.gauss(0, 0.5))
                p = 1 / (1 + math.exp(-(level + ts_skill - (q.difficulty - 2) * 0.9)))
                ok = rng.random() < p
                score += ok
                chosen = q.answer_index if ok else rng.choice([k for k in range(len(q.options)) if k != q.answer_index])
                db.session.add(AttemptAnswer(attempt_id=a.id, question_id=q.id, chosen_index=chosen, is_correct=ok))
            a.score = score
            a.duration_s = int(len(qs) * rng.uniform(15, 55) * (1.3 if level < 0 else 1.0))
            a.finished_at = ts + timedelta(seconds=a.duration_s)
        db.session.commit()
    print(f"Simulated {n} students.")


def ensure_user(name, email, pw, role):
    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(name=name, email=email, role=role)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
    return u


def main(argv):
    app = create_app()
    cmd = argv[1] if len(argv) > 1 else "help"
    with app.app_context():
        if cmd == "init":
            db.create_all()
            load_questions()
        elif cmd == "demo":
            db.create_all()
            load_questions()
            ensure_user("Demo Instructor", "instructor@demo.local", "demo123", "instructor")
            ensure_user("Demo Student", "student@demo.local", "demo123", "student")
            simulate_students()
            res = ml.train()
            print("Model:", res.get("metrics") or res.get("message"))
            print("Log in as instructor@demo.local / demo123 or student@demo.local / demo123")
        elif cmd == "train":
            res = ml.train()
            print(res)
        elif cmd == "create-instructor" and len(argv) == 5:
            ensure_user(argv[2], argv[3].lower(), argv[4], "instructor")
            print("Instructor created.")
        else:
            print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
