"""End-to-end smoke test: python -m pytest tests (or python tests/test_app.py)."""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "t.db")
os.environ["MODEL_PATH"] = os.path.join(tmp, "m.joblib")

from app import create_app, db  # noqa: E402
import manage  # noqa: E402


def test_full_flow():
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        manage.load_questions()
        manage.ensure_user("Teach", "t@x.io", "secret1", "instructor")
        manage.simulate_students(n=40, days=50)
        from app import ml
        assert ml.train()["ok"]
    c = app.test_client()
    r = c.post("/register", data={"name": "Ann", "email": "ann@x.io", "password": "secret1"}, follow_redirects=True)
    assert b"Choose a language" in r.data
    for mode in ("standard", "adaptive", "adaptive"):
        r = c.post("/tests/python/start", data={"mode": mode})
        assert r.status_code == 302
        page = c.get(r.headers["Location"])
        qids = re.findall(rb'name="q(\d+)"', page.data)
        answers = {f"q{q.decode()}": "0" for q in set(qids)}
        r = c.post(r.headers["Location"], data={**answers, "elapsed": "120"}, follow_redirects=True)
        assert b"correct in Python" in r.data
    r = c.get("/dashboard")
    assert r.status_code == 200 and b"Predicted next score" in r.data
    c.get("/logout")
    c.post("/login", data={"email": "t@x.io", "password": "secret1"})
    r = c.get("/instructor")
    assert r.status_code == 200 and b"Class dashboard" in r.data
    assert c.post("/instructor/train", follow_redirects=True).status_code == 200
    r = c.get("/instructor/report.csv")
    assert r.status_code == 200 and b"risk_level" in r.data and b"Ann" in r.data
    with app.app_context():
        from app.models import User
        sid = User.query.filter_by(email="ann@x.io").first().id
    assert c.get(f"/instructor/student/{sid}").status_code == 200


if __name__ == "__main__":
    test_full_flow()
    print("OK")
