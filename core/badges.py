"""Student badges. Everything is computed from the logs (nothing to keep in sync), so a badge can never be lost.

Each badge = a metric + a target. A metric is the sorted list of moments (dates) at which something happened, so
"value" is len(list) and "earned on" is the date of the target-th event.

data/badges.json -> {"<student code>": {"notified": [badge ids], "seen": [badge ids]}}   (only to flag NEW badges)
"""
import json
import threading
from datetime import date, datetime, timedelta

import config

FILE = lambda: config.BASE_DIR / "data" / "badges.json"
_lock = threading.Lock()

# (id, group, icon, metric, target, (name en, name ar), (description en, description ar))
DEFS = [
    ("d10", "days", "🌱", "days", 10, ("Beginner", "مبتدئ"), ("Be active on 10 different days", "اشتغل على الموقع 10 أيام مختلفة")),
    ("d20", "days", "🌿", "days", 20, ("Hardworking", "مجتهد"), ("Be active on 20 different days", "اشتغل على الموقع 20 يوم مختلف")),
    ("d50", "days", "🌳", "days", 50, ("Steady", "ثابت"), ("Be active on 50 different days", "اشتغل على الموقع 50 يوم مختلف")),
    ("d100", "days", "🏆", "days", 100, ("Pro", "محترف"), ("Be active on 100 different days", "اشتغل على الموقع 100 يوم مختلف")),
    ("d200", "days", "👑", "days", 200, ("Legend", "أسطورة"), ("Be active on 200 different days", "اشتغل على الموقع 200 يوم مختلف")),
    ("d365", "days", "💎", "days", 365, ("A full year", "سنة كاملة"), ("Be active on 365 different days", "اشتغل على الموقع 365 يوم مختلف")),
    ("s3", "streak", "🔥", "streak", 3, ("3 days in a row", "3 أيام ورا بعض"), ("Be active 3 days in a row", "اشتغل 3 أيام ورا بعض")),
    ("s7", "streak", "🔥", "streak", 7, ("A full week", "أسبوع كامل"), ("Be active 7 days in a row", "اشتغل 7 أيام ورا بعض")),
    ("s14", "streak", "🔥", "streak", 14, ("Two weeks", "أسبوعين"), ("Be active 14 days in a row", "اشتغل 14 يوم ورا بعض")),
    ("s30", "streak", "🔥", "streak", 30, ("A whole month", "شهر كامل"), ("Be active 30 days in a row", "اشتغل 30 يوم ورا بعض")),
    ("q1", "questions", "💬", "asked", 1, ("First question", "أول سؤال"), ("Ask your first question", "اسأل أول سؤال ليك")),
    ("q10", "questions", "🔎", "asked", 10, ("Curious", "فضولي"), ("Ask 10 questions", "اسأل 10 أسئلة")),
    ("q50", "questions", "🧠", "asked", 50, ("Question machine", "ماكينة أسئلة"), ("Ask 50 questions", "اسأل 50 سؤال")),
    ("q200", "questions", "📚", "asked", 200, ("Walking library", "موسوعة"), ("Ask 200 questions", "اسأل 200 سؤال")),
    ("p1", "practice", "✏️", "answered", 1, ("First practice", "أول تدريب"), ("Answer your first practice question", "جاوب أول سؤال تدريب")),
    ("r10", "practice", "🎯", "run", 10, ("10 in a row", "10 صح ورا بعض"), ("Get 10 practice answers right in a row", "جاوب 10 أسئلة تدريب صح ورا بعض")),
    ("c100", "practice", "🏹", "correct", 100, ("100 correct", "100 إجابة صح"), ("Get 100 practice answers right", "جاوب 100 إجابة صح في التدريب")),
    ("fix", "practice", "🔄", "fixed", 1, ("Fixed a mistake", "صحّحت غلطتك"), ("Answer right a question you got wrong before", "جاوب صح على سؤال كنت غلطت فيه قبل كده")),
    ("t1", "topics", "✅", "green", 1, ("First topic mastered", "أتقنت أول موضوع"), ("Turn one topic green", "خلّي موضوع واحد يبقى أخضر")),
    ("t5", "topics", "🌟", "green", 5, ("5 topics mastered", "أتقنت 5 مواضيع"), ("Turn 5 topics green", "خلّي 5 مواضيع تبقى خضرا")),
    ("tall", "topics", "🎓", "course", 1, ("Course master", "أتقنت المادة كلها"), ("Turn every topic of a course green", "خلّي كل مواضيع مادة كاملة تبقى خضرا")),
    ("e1", "exams", "📝", "exams", 1, ("First exam", "أول امتحان"), ("Finish your first exam", "خلّص أول امتحان")),
    ("e90", "exams", "💯", "exam90", 1, ("Top score", "درجة عالية"), ("Score 90% or more in an exam", "هات 90% أو أكتر في امتحان")),
    ("early", "habits", "🌅", "early", 1, ("Early bird", "صاحي بدري"), ("Study between 4 and 8 in the morning", "ذاكر بين 4 و8 الصبح")),
    ("night", "habits", "🦉", "night", 1, ("Night owl", "سهران"), ("Study between midnight and 4 a.m.", "ذاكر بين 12 بالليل و4 الفجر")),
]
GROUPS = ["days", "streak", "questions", "practice", "topics", "exams", "habits"]
GROUP_NAMES = {"days": ("Days of activity", "أيام النشاط"), "streak": ("Days in a row", "أيام متتالية"),
               "questions": ("Questions", "الأسئلة"), "practice": ("Practice", "التدريب"), "topics": ("Topics", "المواضيع"),
               "exams": ("Exams", "الامتحانات"), "habits": ("Habits", "العادات")}


def _day(t):
    return str(t)[:10]


def _hour(t):
    try:
        return int(str(t)[11:13])
    except ValueError:
        return -1


def _ok(v):
    return str(v).strip().lower() in ("1", "true", "yes")


def metrics(questions, answers, exams, topics_of, green_from=0.7):
    """{metric: sorted list of event times}. questions/answers/exams are one student's rows (time, course, ...)."""
    qs = sorted(questions, key=lambda r: str(r["time"]))
    an = sorted(answers, key=lambda r: str(r["time"]))
    ex = sorted(exams, key=lambda r: str(r["time"]))
    days = sorted({_day(r["time"]) for r in qs + an + ex if r.get("time")})
    # a run of consecutive days: the date on which a run first reached length k is event k
    streak, run, prev = [], 0, None
    for d in days:
        run = run + 1 if prev and date.fromisoformat(d) - date.fromisoformat(prev) == timedelta(days=1) else 1
        prev = d
        if run > len(streak):
            streak.append(d)
    # right answers in a row
    runs, n = [], 0
    for a in an:
        n = n + 1 if _ok(a["correct"]) else 0
        if n > len(runs):
            runs.append(str(a["time"]))
    # a question answered right right after it was answered wrong
    fixed, last = [], {}
    for a in an:
        k = (a.get("course"), a["question_id"])
        if last.get(k) is False and _ok(a["correct"]):
            fixed.append(str(a["time"]))
        last[k] = _ok(a["correct"])
    # topics that reached green (ever), and courses whose every topic did
    first_green = {}
    for a in an:
        try:
            lvl = float(a.get("mastery_after") or 0)
        except ValueError:
            continue
        if lvl >= green_from:
            first_green.setdefault((a.get("course"), a.get("topic")), str(a["time"]))
    courses = []
    for code, names in topics_of.items():
        got = [first_green.get((code, t)) for t in names]
        if names and all(got):
            courses.append(max(got))
    times = [str(r["time"]) for r in qs + an + ex]
    return {
        "days": days, "streak": streak, "asked": [str(r["time"]) for r in qs], "answered": [str(r["time"]) for r in an],
        "run": runs, "correct": [str(a["time"]) for a in an if _ok(a["correct"])], "fixed": fixed,
        "green": sorted(first_green.values()), "course": sorted(courses),
        "exams": [str(r["time"]) for r in ex],
        "exam90": [str(r["time"]) for r in ex if float(r.get("score_pct") or 0) >= 90],
        "early": [t for t in times if 4 <= _hour(t) < 8], "night": [t for t in times if 0 <= _hour(t) < 4],
    }


def compute(questions, answers, exams, topics_of, green_from=0.7, lang="en"):
    """All badges with their state: [{id, group, icon, name, desc, target, value, earned, when, pct}]."""
    m = metrics(questions, answers, exams, topics_of, green_from)
    i = 1 if lang == "ar" else 0
    out = []
    for bid, group, icon, metric, target, name, desc in DEFS:
        ev = m[metric]
        value = min(len(ev), target)
        earned = len(ev) >= target
        out.append({"id": bid, "group": group, "icon": icon, "name": name[i], "desc": desc[i], "target": target, "value": value,
                    "earned": earned, "when": _day(ev[target - 1]) if earned else "", "pct": round(100 * value / target)})
    return out


# ---- which badges the student has already been told about ---------------------------------------------------
def _read():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(d):
    f = FILE()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def new_ids(code, earned):
    """Badges earned (id -> date) but never announced to this student.
    The first call for a student quietly records the badges older than yesterday (history), so nobody gets a flood."""
    with _lock:
        d = _read()
        st = d.get(code)
        if st is None:
            cut = (date.today() - timedelta(days=1)).isoformat()
            old = sorted(b for b, w in earned.items() if w < cut)
            st = d[code] = {"notified": old, "seen": list(old)}
        fresh = sorted(b for b in earned if b not in st["notified"])
        if fresh:
            st["notified"] = sorted(set(st["notified"]) | set(fresh))
        _write(d)
        return fresh


def unseen_count(code):
    st = _read().get(code)
    return len(set(st["notified"]) - set(st["seen"])) if st else 0


def unseen_ids(code):
    st = _read().get(code)
    return set(st["notified"]) - set(st["seen"]) if st else set()


def mark_seen(code):
    with _lock:
        d = _read()
        if code in d:
            d[code]["seen"] = list(d[code]["notified"])
            _write(d)
