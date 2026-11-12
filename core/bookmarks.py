"""Saved answers (bookmarks): data/bookmarks.json -> {student code: [{"id", "course", "question", "slide", "topic", "time"}]}."""
import json
import threading
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "bookmarks.json"
_lock = threading.Lock()
MAX_PER_STUDENT = 200


def _load():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    FILE().parent.mkdir(parents=True, exist_ok=True)
    FILE().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def listing(code, course=None):
    rows = _load().get(code, [])
    return [r for r in rows if not course or r["course"] == course][::-1]


def is_saved(code, course, question):
    q = question.strip().lower()
    return any(r["course"] == course and r["question"].strip().lower() == q for r in _load().get(code, []))


def toggle(code, course, question, slide="", topic=""):
    """Save the question, or remove it when it is already saved. Returns True when it is saved afterwards."""
    question = (question or "").strip()[:300]
    if not question or not code:
        return False
    with _lock:
        d = _load()
        rows = d.get(code, [])
        keep = [r for r in rows if not (r["course"] == course and r["question"].strip().lower() == question.lower())]
        if len(keep) != len(rows):
            d[code] = keep
            _save(d)
            return False
        rid = (max([r["id"] for r in rows]) + 1) if rows else 1
        rows.append({"id": rid, "course": course, "question": question, "slide": slide, "topic": topic,
                     "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
        d[code] = rows[-MAX_PER_STUDENT:]
        _save(d)
        return True


def remove(code, rid):
    with _lock:
        d = _load()
        rows = d.get(code, [])
        d[code] = [r for r in rows if r["id"] != rid]
        _save(d)


def drop_student(code):
    with _lock:
        d = _load()
        if d.pop(code, None) is not None:
            _save(d)
