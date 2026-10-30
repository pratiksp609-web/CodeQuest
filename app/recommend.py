"""Personalized learning recommendations and adaptive question selection."""
import random

from .models import Language, Question, Topic


def recommendations(features, mastery, lang_summary, prediction, user=None, coding=None):
    recs = []
    if user is not None and features is not None and user.wants_job:
        if "Aptitude" not in {r["language"] for r in lang_summary}:
            recs.append({"kind": "job", "title": "Start aptitude practice",
                         "detail": "Most placement tests begin with an aptitude round. Take your first aptitude test.",
                         "link": None, "language": "Aptitude"})
        if coding is not None and coding["solved"] < 5:
            recs.append({"kind": "job", "title": "Solve interview coding problems",
                         "detail": f"You've solved {coding['solved']} so far. Start with the Easy interview-tagged problems.",
                         "link": "/problems?interview=1"})
    if features is None:
        return [{"kind": "start", "title": "Take your first test",
                 "detail": "Pick any language to get a baseline. Recommendations appear after your first test.",
                 "link": None}]

    weak = mastery[(mastery["mastery"] < 0.6) & (mastery["answered"] >= 2)].head(3)
    for _, r in weak.iterrows():
        recs.append({
            "kind": "topic",
            "title": f"Strengthen {r['language']}: {r['topic']}",
            "detail": f"Mastery is {round(r['mastery'] * 100)}% over {int(r['answered'])} questions. Review the guide, then take an adaptive test.",
            "link": r["resource_url"],
            "language": r["language"],
        })

    if prediction and prediction["level"] == "high":
        recs.append({"kind": "alert", "title": "You're at risk of falling below the pass mark",
                     "detail": f"Predicted next score is {prediction['predicted_pct']}%. Short daily practice on your weakest topics helps most.",
                     "link": None})
    if features["attendance_rate"] < 0.3:
        recs.append({"kind": "habit", "title": "Practice more consistently",
                     "detail": f"You were active on {round(features['attendance_rate'] * 30)} of the last 30 days. Aim for 3 to 4 sessions a week.",
                     "link": None})
    if features["trend"] < -0.02:
        recs.append({"kind": "trend", "title": "Your recent scores are slipping",
                     "detail": "Revisit the explanations on your last few results before taking new tests.", "link": None})
    if features["hard_accuracy"] >= 0.75 and features["recent_pct"] >= 0.8:
        recs.append({"kind": "level", "title": "Ready for harder material",
                     "detail": "You're scoring well on hard questions. Try adaptive mode in a new language.", "link": None})

    tried = {r["language"] for r in lang_summary}
    mine = set(user.preferred_languages or []) if user is not None else set()
    untried = [l.name for l in Language.query.filter_by(category="programming").order_by(Language.name)
               if l.name not in tried and (not mine or l.slug in mine)]
    if untried:
        recs.append({"kind": "explore", "title": f"Try {untried[0]}",
                     "detail": f"You haven't tested {', '.join(untried[:3])} yet.", "link": None, "language": untried[0]})

    strong = mastery[mastery["mastery"] >= 0.85]
    if len(strong) and len(recs) < 6:
        names = ", ".join(f"{r.language} {r.topic}" for r in strong.head(3).itertuples())
        recs.append({"kind": "strength", "title": "Strengths", "detail": f"You've mastered {names}.", "link": None})
    return recs


def pick_questions(language, n, mode="standard", mastery=None, seen_ids=None, topic_id=None, prefer_harder=False):
    """Demo: short, mostly easy, one per topic where possible. Standard: random mix (tilted toward
    medium/hard for job seekers). Adaptive: weighted toward weak/unseen topics, at a difficulty
    that matches the student's mastery of each topic."""
    q = Question.query.join(Topic).filter(Topic.language_id == language.id)
    if topic_id:
        q = q.filter(Question.topic_id == topic_id)
    pool = q.all()
    if len(pool) <= n:
        random.shuffle(pool)
        return pool
    if mode == "demo":
        random.shuffle(pool)
        pool.sort(key=lambda q: q.difficulty)
        chosen, topics = [], set()
        for q in pool:  # one easy question per topic first
            if q.topic_id not in topics and len(chosen) < n:
                chosen.append(q)
                topics.add(q.topic_id)
        chosen += [q for q in pool if q not in chosen][: n - len(chosen)]
        random.shuffle(chosen)
        return chosen
    if mode != "adaptive" or mastery is None or mastery.empty:
        if not prefer_harder:
            return random.sample(pool, n)
        weights = [{1: 0.6, 2: 1.2, 3: 1.4}[q.difficulty] for q in pool]
        return _weighted_sample(pool, weights, n)

    m = {int(r.topic_id): float(r.mastery) for r in mastery.itertuples() if r.language == language.name}
    seen_ids = seen_ids or set()
    weights = []
    for question in pool:
        tm = m.get(question.topic_id, 0.4)
        target = 1 if tm < 0.4 else 2 if tm < 0.75 else 3
        w = (1.2 - tm) * (1.5 if question.id not in seen_ids else 1.0)
        w *= 1.6 if question.difficulty == target else 0.7
        weights.append(max(w, 0.05))
    return _weighted_sample(pool, weights, n)


def _weighted_sample(pool, weights, n):
    chosen = []
    pool, weights = list(pool), list(weights)
    for _ in range(n):
        i = random.choices(range(len(pool)), weights=weights, k=1)[0]
        chosen.append(pool.pop(i))
        weights.pop(i)
    return chosen
