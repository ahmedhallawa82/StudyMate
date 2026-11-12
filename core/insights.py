"""Insights that need no AI service: built only from logs.xlsx.

1. unanswered()  - the questions the slides could not answer, grouped and counted (what is missing from the lectures).
2. reviews()     - spaced repetition: a weak topic comes back for review 1, 3 and 7 days after it was practised.
3. at_risk()     - students who need attention: low level, or no activity for some days.
   notify_at_risk() tells the course owner about new ones, at most once a day per course.
"""
import json
import re
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta

import config

INTERVALS = (1, 3, 7)            # days before the 1st, 2nd and 3rd(+) review of a weak topic
LOW_LEVEL = config.RED_BELOW     # below 40 % = needs attention
INACTIVE_DAYS = 7
MIN_ANSWERS = 5                  # judge a student's level only after a few practice answers
_lock = threading.Lock()


def _day(t):
    try:
        return datetime.strptime(str(t)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def norm(q):
    q = re.sub(r"[^\w\s]", " ", str(q).lower())
    return " ".join(q.split())


# ------------------------------------------------------------------ 1. unanswered questions
def unanswered(questions, top=10):
    """questions: rows of the Questions sheet of one course. Returns the most repeated 'Not found' questions."""
    groups = defaultdict(list)
    for q in questions:
        if q.get("found") == "no" and str(q.get("question", "")).strip():
            groups[norm(q["question"])].append(q)
    out = []
    for rows in groups.values():
        last = rows[-1]
        out.append({"question": last["question"], "n": len(rows), "students": len({r.get("student_code") for r in rows}),
                    "last": str(last.get("time", ""))[:16], "id": last.get("id")})
    out.sort(key=lambda r: r["last"], reverse=True)
    out.sort(key=lambda r: -r["n"])                    # most repeated first, newest first among equals
    return out[:top]


# ------------------------------------------------------------------ 2. spaced repetition
def reviews(answers, mastery, qid_topic, today=None):
    """answers: the student's Answers rows in this course. Returns weak, already practised topics with their next review:
    [{topic, last, days_ago, due (date), overdue (bool)}], due ones first."""
    today = today or date.today()
    days = defaultdict(set)
    for a in answers:
        t = qid_topic.get(a.get("question_id")) or a.get("topic")
        d = _day(a.get("time"))
        if t and d:
            days[t].add(d)
    out = []
    for t, ds in days.items():
        if mastery.get(t, 0.0) >= config.GREEN_FROM:
            continue                                    # green topics need no review
        last = max(ds)
        gap = INTERVALS[min(len(ds), len(INTERVALS)) - 1]
        due = last + timedelta(days=gap)
        out.append({"topic": t, "last": last.isoformat(), "days_ago": (today - last).days, "due": due.isoformat(),
                    "overdue": due <= today, "gap": gap})
    out.sort(key=lambda r: (not r["overdue"], r["due"]))
    return out


# ------------------------------------------------------------------ 3. students who need attention
def at_risk(code, students, questions, answers, visits, replay, qid_topic, n_topics, today=None, inactive_days=INACTIVE_DAYS):
    """students: registered students of the course ({code, first, last, created}). Returns [{code, name, level, last, reasons}]."""
    today = today or date.today()
    last_seen = {}
    for r in list(questions) + list(answers) + list(visits):
        d = _day(r.get("time"))
        c = r.get("student_code")
        if d and c and (c not in last_seen or d > last_seen[c]):
            last_seen[c] = d
    by_student = defaultdict(list)
    for a in answers:
        by_student[a.get("student_code")].append(a)
    out = []
    for s in students:
        c = s["code"]
        rows = by_student.get(c, [])
        m = replay(rows, qid_topic)
        level = sum(m.values()) / len(m) if (m and len(rows) >= MIN_ANSWERS) else None   # mean over practised topics
        last = last_seen.get(c) or _day(s.get("created"))
        reasons = []
        if level is not None and level < LOW_LEVEL:
            reasons.append("low")
        if last and (today - last).days >= inactive_days:
            reasons.append("inactive")
        if reasons:
            out.append({"code": c, "name": f"{s.get('first', '')} {s.get('last', '')}".strip() or c,
                        "level": None if level is None else round(level * 100), "last": last.isoformat() if last else "",
                        "days": (today - last).days if last else None, "reasons": reasons})
    out.sort(key=lambda r: (-(r["days"] or 0), r["level"] if r["level"] is not None else 101))
    return out


def _file():
    return config.BASE_DIR / "data" / "atrisk_notified.json"


def notified_today(code):
    try:
        return json.loads(_file().read_text(encoding="utf-8")).get(code, {}).get("day") == date.today().isoformat()
    except (OSError, ValueError):
        return False


def notify_at_risk(code, rows, owner_keys, push, title, body_fn, link=""):
    """Tell the course owner(s) about students who became at risk since the last notice (max once a day per course)."""
    today = date.today().isoformat()
    with _lock:
        try:
            state = json.loads(_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        cur = state.get(code, {})
        if cur.get("day") == today:
            return False
        known = set(cur.get("codes", []))
        new = [r for r in rows if r["code"] not in known]
        state[code] = {"day": today, "codes": sorted({r["code"] for r in rows})}
        _file().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    if new:
        push(owner_keys, "student", title, body_fn(new), link)
        return True
    return False
