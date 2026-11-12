"""Study plan (from a student's weak topics) and the weekly report for a doctor (from logs.xlsx). No AI service needed."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import config


def _day(t):
    try:
        return datetime.strptime(str(t)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def study_plan(mastery, topics, exam_day=None, today=None, per_day=2, max_days=14):
    """mastery: {topic: level 0..1}; topics: [(topic, name)] in course order.
    Weakest topics first (a topic never practised counts as 30 %), `per_day` topics a day until the exam
    (or the next `max_days` days when there is no exam). Returns {"days": [{"date", "topics": [{topic, name, pct}]}], "exam"}."""
    today = today or date.today()
    ranked = sorted(topics, key=lambda t: mastery.get(t[0], 0.3))
    ranked = [t for t in ranked if mastery.get(t[0], 0.0) < 0.8]              # a topic above 80 % needs no plan
    span = max_days
    if exam_day:
        span = max(1, min(max_days, (exam_day - today).days))
    days = []
    for i in range(span):
        chunk = ranked[i * per_day:(i + 1) * per_day]
        if not chunk:
            break
        days.append({"date": (today + timedelta(days=i)).isoformat(),
                     "topics": [{"topic": t, "name": n, "pct": round(mastery.get(t, 0.0) * 100)} for t, n in chunk]})
    left = ranked[span * per_day:]                                            # more weak topics than days: say so
    return {"days": days, "exam": exam_day.isoformat() if exam_day else "", "left": len(left)}


def weekly(questions, answers, visits, names, days=7, today=None):
    """Numbers for the last `days` days of ONE course (rows already filtered by course)."""
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    inr = lambda r: (d := _day(r.get("time"))) is not None and start <= d <= today
    qs, an, vi = [r for r in questions if inr(r)], [r for r in answers if inr(r)], [r for r in visits if inr(r)]
    score = defaultdict(list)
    for a in an:
        if a.get("topic") in names:
            score[a["topic"]].append(1 if str(a.get("correct")) in ("1", "True") else 0)
    weak = sorted(((t, round(100 * sum(v) / len(v)), len(v)) for t, v in score.items() if len(v) >= 3), key=lambda x: x[1])[:3]
    missing = Counter(" ".join(str(q["question"]).lower().split()) for q in qs if q.get("found") == "no" and str(q.get("question", "")).strip())
    helpful = [q["helpful"] for q in qs if q.get("helpful") in ("yes", "no")]
    return {
        "from": start.isoformat(), "to": today.isoformat(),
        "questions": len(qs), "not_found": sum(q.get("found") == "no" for q in qs), "answers": len(an),
        "students": len({r.get("student_code") for r in qs + an + vi if r.get("student_code")}),
        "helpful_pct": round(100 * helpful.count("yes") / len(helpful)) if helpful else None,
        "weak": [{"name": names[t], "avg": a, "n": n} for t, a, n in weak],
        "missing": [{"question": q, "n": n} for q, n in missing.most_common(5)],
    }
