# CodeQuest: a mini LeetCode for coding, theory and aptitude

Students sign up with email verification, set up a profile (languages, goal, job or knowledge), and then
practice three things in one place:

1. **Coding problems**: write code in the browser, run it on examples or custom input, and submit it against hidden tests.
2. **Theory tests** in 12 development languages.
3. **Aptitude tests** for placement and job preparation.

Every result feeds an analytics and machine learning pipeline that predicts outcomes, flags at-risk students and
recommends what to study next. Instructors get a class dashboard.

**Stack:** Python · Flask · SQLAlchemy · MySQL (SQLite for quick local runs) · pandas · scikit-learn · Chart.js · CodeMirror

## Features

### Sign-up and account setup
- Sign up with a name, email and password, then **verify with a 6-digit code sent by email**. Codes are hashed, expire
  after 10 minutes, allow 5 tries, and can be resent after 60 seconds.
- **Account setup** after verification: full name, birth date, mobile number (+91, 10 digits starting 6 to 9),
  languages to practice, university or college, goal (placements, developer job, career switch, competitive
  programming, university exams, a new language, or other), an optional note, and purpose (**job** or **knowledge**).
  Students can't use the site until setup is finished, and they can edit it later under their name in the menu.
- All forms are protected with CSRF tokens.

### Tailored to each student
- The tests page lists **your languages** first, then **Aptitude**, then the rest.
- New languages start with a **5-question demo test** (easy questions, one per topic) to set a baseline.
- Job seekers get standard tests that lean toward medium and hard questions, aptitude and interview-problem
  recommendations, and a placement-focused study plan. Knowledge learners get a concept-focused plan.
- The code editor opens in the student's first preferred language.

### Coding problems (mini LeetCode)
- 18 problems (Easy, Medium, Hard) covering strings, arrays, hashing, stacks, two pointers, sliding window, sorting,
  binary search, DP, BFS and math. Interview-style problems are tagged.
- Filter by difficulty, topic, status (to do, attempted, solved) and interview problems. Acceptance rates shown.
- Browser editor (CodeMirror) with syntax highlighting, drafts saved per problem and language, and a reset button.
- **Run** on examples or custom input. **Submit** to judge against all tests, including hidden ones. Verdicts:
  Accepted, Wrong Answer, Time Limit Exceeded, Runtime Error, Compilation Error.
- Languages: **Python, C, C++, Java, JavaScript, Go, PHP, Rust, and C#** (C# needs Mono). A language shows up only
  if its compiler or runtime is installed on the server.
- Problem expected outputs are generated from a reference solution when loaded, so the tests always agree with a
  working solution.

### Theory and aptitude tests
- 206 questions: 20 each for Python, Java, C, C++, C# and JavaScript; 10 each for Go, Kotlin, TypeScript, PHP, Rust
  and SQL; 26 aptitude questions across Quantitative, Logical Reasoning, Verbal Ability and Data Interpretation.
- Demo, standard and adaptive modes; topic filter; timer; explanations on every answer.

### Analytics, ML and dashboards
- pandas pipeline over MySQL: topic mastery, trends, attendance, class distributions.
- `RandomForestClassifier` (at-risk probability) and `GradientBoostingRegressor` (next score), trained on each
  student's earlier tests to predict later ones. Accuracy, ROC AUC and feature importance shown to instructors.
- Student dashboard: study plan, demo-test prompts, coding progress by difficulty, predicted score, risk level,
  recommendations, score timeline, topic mastery, daily activity.
- Instructor dashboard: class KPIs, students needing attention, coding stats, trends, attendance, per-student
  drill-down with profile, CSV export (includes mobile, university, goal, purpose, problems solved), retrain button.

## Run locally (SQLite)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py demo        # tables, questions, problems, 120 simulated students, trained model
python run.py                # open http://localhost:5000
```

Demo logins (password `demo123`): `student@demo.local` and `instructor@demo.local`. New sign-ups go through the
email code step. **Without SMTP settings, the code is printed in the terminal running `python run.py`.**

If you ran an older version, delete `learnopt.db` first: the database schema changed.

For a clean install without simulated students, use `python manage.py init`, then create an instructor with
`python manage.py create-instructor "Name" email@example.com password`.

To judge code in other languages, install their tools on the server: `gcc`/`g++`, a JDK (`javac`), Node.js,
Go, PHP, Rust (`rustc`), and Mono (`mcs`, `mono`) for C#.

## Send real OTP emails

Set these environment variables before `python run.py`. Example for Gmail (create an App Password in your Google
account first):

```bash
export MAIL_SERVER=smtp.gmail.com
export MAIL_PORT=587
export MAIL_USE_TLS=true
export MAIL_USERNAME=you@gmail.com
export MAIL_PASSWORD=your-app-password
export MAIL_FROM="CodeQuest <you@gmail.com>"
```

For port 465 use `MAIL_USE_SSL=true` and `MAIL_USE_TLS=false`.

## Use MySQL

```bash
mysql -u root -p < schema_mysql.sql
export DATABASE_URL="mysql+pymysql://learnopt:learnopt@localhost:3306/learnopt"
python manage.py demo   # or: python manage.py init
python run.py
```

Set `SECRET_KEY` to a long random value in production.

## Security note on the code judge

Submissions run as local processes in a temporary folder with time, CPU, memory and output limits, and at most 4
run at once. That's fine for a class or a private deployment. Before opening the site to the public, run the app
(or just `app/judge.py`) inside a locked-down container with no network access and an unprivileged user, or
replace `judge.execute` with a sandbox service.

## Add content

- Theory or aptitude questions: `app/question_bank.py` and `app/question_bank_more.py`
- Coding problems: `app/problem_bank.py` (statement, formats, a Python reference solution, and test inputs)

Then run `python manage.py init` again. It only adds new items.

## Tests

```bash
python tests/test_app.py
```

Covers sign-up, OTP verification, account setup validation, tailored tests, all test modes, aptitude, running and
judging code (accepted, wrong answer, compile error, custom input), CSRF, and the instructor pages.

## Project layout

```
app/
  __init__.py          app factory, CSRF, verification/setup gate, attendance
  models.py            users + profile, OTPs, languages, questions, attempts, problems, submissions
  routes.py            auth, OTP, account setup, tests, dashboards, CSV, retraining
  coding.py            problem list, editor page, run/submit API
  judge.py             compiles and runs code against test cases
  otp.py, mailer.py    verification codes and email
  profile.py           goals, mobile validation, study plan
  analytics.py, ml.py, recommend.py
  question_bank.py, question_bank_more.py, problem_bank.py
  templates/, static/  (Chart.js and CodeMirror are bundled, no CDN needed)
manage.py              init / demo / train / create-instructor
```
