"""Exams a doctor schedules for a course (they appear in the calendar of the course's students, doctor and admin).

data/schedule.json -> [{"id", "course", "title", "when": "YYYY-MM-DDTHH:MM", "note", "by", "created"}]
"""
import json
import threading
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "schedule.json"
_lock = threading.Lock()


def _load():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(rows):
    FILE().parent.mkdir(parents=True, exist_ok=True)
    FILE().write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def add(course, title, when, note="", by=""):
    """Returns the new item, or None when the date is not valid."""
    try:
        datetime.strptime(when, "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return None
    title = (title or "").strip()[:120] or "Exam"
    with _lock:
        rows = _load()
        item = {"id": (max([r["id"] for r in rows]) + 1) if rows else 1, "course": course, "title": title, "when": when,
                "note": (note or "").strip()[:300], "by": by, "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
        rows.append(item)
        _save(rows)
    return item


def remove(item_id):
    with _lock:
        rows = _load()
        keep = [r for r in rows if r["id"] != item_id]
        _save(keep)
        return len(keep) != len(rows)


def get(item_id):
    return next((r for r in _load() if r["id"] == item_id), None)


def for_courses(codes):
    codes = set(codes)
    return sorted([r for r in _load() if r["course"] in codes], key=lambda r: r["when"])
