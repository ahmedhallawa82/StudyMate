"""Notifications for students, doctors and the admin.

data/notifications.json -> [{"id", "time", "to": ["s:<student code>", "d:<doctor id>" ...], "kind", "title", "body", "link", "read": [user keys]}]
A user key is "s:<code>" for a student and "d:<id>" for a doctor ("d:master" is the main admin).
"""
import json
import threading
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "notifications.json"
_lock = threading.Lock()
KEEP = 600
_cache = {"mt": None, "rows": []}


def _load():
    f = FILE()
    try:
        mt = f.stat().st_mtime_ns
    except OSError:
        return []
    if _cache["mt"] != mt or _cache.get("f") != str(f):
        try:
            _cache.update(rows=json.loads(f.read_text(encoding="utf-8")), mt=mt, f=str(f))
        except Exception:
            _cache.update(rows=[], mt=mt, f=str(f))
    return _cache["rows"]


def _save(rows):
    f = FILE()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows[-KEEP:], ensure_ascii=False), encoding="utf-8")
    _cache["mt"] = None


def push(to, kind, title, body="", link=""):
    """Send one notification to every user key in `to` (duplicates ignored)."""
    to = sorted({k for k in to if k})
    if not to:
        return
    with _lock:
        rows = list(_load())
        nid = (rows[-1]["id"] + 1) if rows else 1
        rows.append({"id": nid, "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "to": to, "kind": kind,
                     "title": title, "body": body, "link": link, "read": []})
        _save(rows)


def for_user(key, limit=30):
    rows = [dict(r, unread=key not in r["read"]) for r in _load() if key in r["to"]]
    return rows[::-1][:limit]


def unread_count(key):
    return sum(1 for r in _load() if key in r["to"] and key not in r["read"])


def mark_read(key, nid=None):
    with _lock:
        rows = list(_load())
        for r in rows:
            if key in r["to"] and key not in r["read"] and (nid is None or r["id"] == nid):
                r["read"].append(key)
        _save(rows)
