"""Profile options and the personalised study plan built from them."""
import re
from datetime import date

GOALS = {
    "placement": "Crack campus placements",
    "sde_job": "Get a software developer job",
    "switch": "Switch to a tech career",
    "competitive": "Get better at competitive programming",
    "exams": "Score well in university exams",
    "new_language": "Learn a new language",
    "other": "Something else",
}
PURPOSES = {"job": "Preparing for a job", "knowledge": "Improving my knowledge"}
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


def parse_mobile(raw):
    """Accepts '9876543210', '+91 98765 43210', '+91-9876543210'. Returns 10 digits or None."""
    digits = re.sub(r"[\s\-()]", "", raw or "")
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits if MOBILE_RE.match(digits) else None


def age_on(birth, today=None):
    today = today or date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def study_plan(user, languages):
    """A short plan for the dashboard, built from the student's purpose, goal and languages.
    `languages` maps slug -> Language."""
    langs = [languages[s] for s in (user.preferred_languages or []) if s in languages]
    names = ", ".join(l.name for l in langs if l.category == "programming") or "your languages"
    job = user.wants_job or user.goal in ("placement", "sde_job", "switch")
    steps = [f"Take a 5-question demo test in each of {names} to set your baseline."]
    if job:
        steps += [
            "Do one aptitude test every other day: quantitative, logical and verbal rounds are in most placement tests.",
            "Solve the interview-tagged coding problems, starting with Easy, and aim for 2 to 3 a day.",
            "Use adaptive tests to fix weak theory topics before interviews.",
        ]
    elif user.goal == "competitive":
        steps += ["Work through Medium and Hard coding problems and keep runtime in mind.",
                  "Review data structures topics with adaptive tests."]
    elif user.goal == "exams":
        steps += ["Take topic-wise tests for each unit of your syllabus.",
                  "Re-read the explanations on every wrong answer."]
    else:
        steps += ["Take adaptive tests a few times a week; they focus on your weak topics.",
                  "Try Easy coding problems to apply what you learned."]
    return {"job": job, "steps": steps}
