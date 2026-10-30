# CodeQuest: Student Learning Optimization Platform

A web platform where students test their knowledge of development languages (Python, Java, C, C++, C#, JavaScript),
and where the results feed an analytics + machine learning pipeline that predicts outcomes, flags at-risk students
and recommends what to study next.

**Stack:** Python · Flask · SQLAlchemy · MySQL (SQLite for quick local runs) · pandas · scikit-learn · Chart.js

## Features

- **Tests**: 72 starter questions across 6 languages and 24 topics, three difficulty levels, code snippets, timer,
  per-question explanations. Standard mode (random mix) or **adaptive** mode (weighted toward weak/unseen topics at
  the right difficulty). Filter by topic.
- **Analytics pipeline** (`app/analytics.py`): pulls from MySQL with SQLAlchemy into pandas and computes
  difficulty-weighted topic mastery, score trends, attendance, weekly class trends and score distributions.
- **Machine learning** (`app/ml.py`):
  - `RandomForestClassifier` predicts the probability a student is at risk (future average below the 60% pass mark)
  - `GradientBoostingRegressor` predicts the next score
  - Trained on history: features from each student's earlier 70% of tests, label from the later 30%.
  - Features: average, recent average, trend slope, tests taken, 30-day attendance, seconds per question,
    hard-question accuracy, share of weak topics. Holdout accuracy, ROC AUC, error and feature importance are shown
    on the instructor dashboard. Before a model is trained, a transparent rule-based fallback is used.
- **Personalized recommendations** (`app/recommend.py`): weakest topics with study links, consistency and trend
  alerts, readiness for harder material, languages not tried yet, strengths.
- **Dashboards**
  - Student: KPIs, predicted score, risk level, recommendations, score timeline vs pass mark, language averages,
    topic mastery, daily activity, recent tests with review.
  - Instructor: class KPIs, students needing attention, weekly score trend, daily attendance, score distribution,
    language averages, hardest topics, model metrics + feature importance, all students, per-student drill-down,
    **CSV report export**, one-click model retraining.
- **Attendance**: every day a student uses the platform is recorded automatically.

## Run locally (SQLite, 2 minutes)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py demo        # creates tables, loads questions, simulates 120 students, trains the model
python run.py                # open http://localhost:5000
```

Demo logins (password `demo123`): `student@demo.local` and `instructor@demo.local`.
For a clean install without simulated students, run `python manage.py init` instead of `demo`, and create an
instructor with `python manage.py create-instructor "Name" email@example.com password`.

## Use MySQL

```bash
mysql -u root -p < schema_mysql.sql                     # creates database + user 'learnopt'
export DATABASE_URL="mysql+pymysql://learnopt:learnopt@localhost:3306/learnopt"   # Windows: set DATABASE_URL=...
python manage.py demo   # or: python manage.py init
python run.py
```

Set `SECRET_KEY` to a random value in production. Other settings are in `config.py`
(`QUESTIONS_PER_QUIZ`, `MODEL_PATH`, `PASS_MARK`).

## Add questions or languages

Edit `app/question_bank.py` (add a language block, topics with study links, and questions) and run
`python manage.py init` again; it only inserts new items.

## Retrain the model

From the instructor dashboard (**Retrain model**) or `python manage.py train`. It needs at least 10 students with 6+
tests. Retrain as real student data accumulates; the simulated students only exist so the demo has history.

## Tests

```bash
python tests/test_app.py
```

## Project layout

```
app/
  __init__.py      app factory, login, attendance tracking
  models.py        users, languages, topics, questions, attempts, answers, attendance
  question_bank.py starter questions
  routes.py        pages: auth, tests, results, dashboards, CSV report, retraining
  analytics.py     pandas pipeline
  ml.py            training + prediction
  recommend.py     recommendations + adaptive question selection
  templates/, static/
manage.py          init / demo / train / create-instructor
config.py, run.py, schema_mysql.sql, requirements.txt
```
