"""End-to-end test: python tests/test_app.py (or pytest tests)."""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "t.db")
os.environ["MODEL_PATH"] = os.path.join(tmp, "m.joblib")
os.environ.pop("MAIL_SERVER", None)

from app import create_app, db  # noqa: E402
import manage  # noqa: E402


def token(client, path="/"):
    html = client.get(path, follow_redirects=True).data.decode()
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def post(client, path, data=None, **kw):
    data = dict(data or {})
    data["_csrf"] = token(client)
    return client.post(path, data=data, **kw)


def take_test(c, slug, mode):
    r = post(c, f"/tests/{slug}/start", {"mode": mode})
    assert r.status_code == 302, r.status_code
    loc = r.headers["Location"]
    page = c.get(loc).data
    qids = sorted(set(re.findall(rb'name="q(\d+)"', page)))
    r = post(c, loc, {**{f"q{q.decode()}": "0" for q in qids}, "elapsed": "60"}, follow_redirects=True)
    assert b"correct in" in r.data
    return len(qids)


def test_full_flow():
    app = create_app()
    with app.app_context():
        manage.load_questions()
        manage.load_problems()
        manage.ensure_user("Teach", "t@x.io", "secret12", "instructor")
        manage.simulate_students(n=40, days=50)
        from app import ml
        assert ml.train()["ok"]
    c = app.test_client()

    # CSRF is enforced
    assert c.post("/login", data={"email": "x", "password": "y"}).status_code == 400

    # Sign up -> OTP -> verify
    r = post(c, "/register", {"name": "Ann", "email": "ann@x.io", "password": "secret12", "confirm": "secret12"})
    assert r.headers["Location"].endswith("/verify")
    assert c.get("/dashboard").headers["Location"].endswith("/verify")  # gated
    mail = app.extensions["outbox"][-1]
    code = re.search(r"code is: (\d{6})", mail["body"]).group(1)
    wrong = "000000" if code != "000000" else "111111"
    assert b"Incorrect code" in post(c, "/verify", {"code": wrong}, follow_redirects=True).data
    r = post(c, "/verify", {"code": code})
    assert r.headers["Location"].endswith("/onboarding")

    # Account setup is required and validated
    assert c.get("/tests").headers["Location"].endswith("/onboarding")
    profile = {"name": "Ann Rao", "birth_date": "2003-04-05", "mobile": "12345", "university": "Pune University",
               "goal": "placement", "purpose": "job", "languages": ["python", "java", "aptitude"]}
    assert b"valid 10-digit" in post(c, "/onboarding", profile, follow_redirects=True).data
    profile["mobile"] = "+91 98765 43210"
    r = post(c, "/onboarding", profile)
    assert r.headers["Location"].endswith("/tests")
    with app.app_context():
        from app.models import User
        u = User.query.filter_by(email="ann@x.io").first()
        assert u.mobile == "9876543210" and u.preferred_languages == ["python", "java", "aptitude"]
        sid = u.id

    # Tailored tests page, demo + standard + adaptive + aptitude
    page = c.get("/tests").data.decode()
    heads = re.findall(r"<h2 id=[^>]*>([^<]+)</h2>", page)
    assert heads == ["Your languages", "Aptitude", "More languages"], heads
    assert take_test(c, "python", "demo") == 5
    assert take_test(c, "python", "standard") == 10
    take_test(c, "python", "adaptive")
    take_test(c, "aptitude", "standard")
    r = c.get("/dashboard")
    assert r.status_code == 200 and b"study plan" in r.data and b"Predicted next score" in r.data

    # Coding problems: run, wrong answer, accepted, compile error
    assert b"Sum of Two Numbers" in c.get("/problems").data
    assert c.get("/problems/sum-of-two").status_code == 200
    hdr = {"X-CSRF-Token": token(c)}
    r = c.post("/problems/sum-of-two/run", json={"language": "python", "code": "a,b=map(int,input().split())\nprint(a+b)"}, headers=hdr)
    assert r.json["verdict"] == "Accepted"
    r = c.post("/problems/sum-of-two/submit", json={"language": "python", "code": "print(8)"}, headers=hdr)
    assert r.json["verdict"] == "Wrong Answer" and any(t["hidden"] and t["input"] is None for t in r.json["results"])
    r = c.post("/problems/sum-of-two/submit", json={"language": "cpp",
               "code": "#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b;}"}, headers=hdr)
    assert r.json["verdict"] == "Accepted", r.json
    r = c.post("/problems/sum-of-two/submit", json={"language": "java", "code": "class {"}, headers=hdr)
    assert r.json["verdict"] == "Compilation Error"
    r = c.post("/problems/sum-of-two/run", json={"language": "python", "code": "print(input()[::-1])", "input": "abc"}, headers=hdr)
    assert r.json["results"][0]["output"].strip() == "cba"
    assert c.post("/problems/sum-of-two/run", json={"language": "python", "code": "print(1)"}).status_code == 400
    assert c.get(f"/submissions/{r.json.get('submission_id', 1)}").status_code in (200, 403)
    assert "✓" in c.get("/problems").data.decode()

    # Forgot password -> code -> new password
    c.get("/logout")
    r = post(c, "/forgot", {"email": "ann@x.io"})
    assert r.headers["Location"].endswith("/reset")
    code = re.search(r"reset code is: (\d{6})", app.extensions["outbox"][-1]["body"]).group(1)
    r = post(c, "/reset", {"code": code, "password": "newpass99", "confirm": "newpass99"})
    assert r.headers["Location"].endswith("/login")
    assert b"Invalid email" in post(c, "/login", {"email": "ann@x.io", "password": "secret12"}, follow_redirects=True).data
    assert post(c, "/login", {"email": "ann@x.io", "password": "newpass99"}).status_code == 302
    assert post(c, "/forgot", {"email": "nobody@x.io"}).status_code == 302  # no account enumeration

    # Health check, error page, security headers
    r = c.get("/healthz")
    assert r.status_code == 200 and r.json["database"] == "ok"
    r = c.get("/no-such-page")
    assert r.status_code == 404 and b"Page not found" in r.data and r.headers["X-Frame-Options"] == "DENY"

    # Instructor views
    c.get("/logout")
    post(c, "/login", {"email": "t@x.io", "password": "secret12"})
    r = c.get("/instructor")
    assert r.status_code == 200 and b"Problems solved" in r.data
    assert post(c, "/instructor/train", follow_redirects=True).status_code == 200
    r = c.get("/instructor/report.csv")
    assert b"+919876543210" in r.data and b"Ann Rao" in r.data
    assert c.get(f"/instructor/student/{sid}").status_code == 200


if __name__ == "__main__":
    test_full_flow()
    print("OK")
