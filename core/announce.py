"""Announcements a doctor sends to the students of one course: data/announcements.json."""
import json
import threading
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "announcements.json"
_lock = threading.Lock()
KEEP = 300


def _load():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except Exception:
        return []


def add(course, title, body, by, by_name=""):
    title, body = (title or "").strip()[:120], (body or "").strip()[:1500]
    if not title:
        return None
    with _lock:
        rows = _load()
        item = {"id": (max([r["id"] for r in rows]) + 1) if rows else 1, "course": course, "title": title, "body": body,
                "by": by, "by_name": by_name, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
        rows.append(item)
        FILE().parent.mkdir(parents=True, exist_ok=True)
        FILE().write_text(json.dumps(rows[-KEEP:], ensure_ascii=False), encoding="utf-8")
    return item


def remove(aid):
    with _lock:
        rows = _load()
        keep = [r for r in rows if r["id"] != aid]
        FILE().write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
        return len(keep) != len(rows)


def for_courses(codes, limit=20):
    codes = set(codes)
    return [r for r in _load() if r["course"] in codes][::-1][:limit]


def latest(codes, days=7):
    """Announcements of the last `days` days for these courses (shown as a banner on the student's home)."""
    from datetime import timedelta
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    return [r for r in for_courses(codes, 5) if r["time"] >= cut]
