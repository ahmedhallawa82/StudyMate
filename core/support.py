"""Support messages: anyone (even before signing in) can write to the support team.

data/support.json -> [{"id", "time", "name", "contact", "message", "ident", "status": "open"|"done"}]
"""
import json
import threading
import time
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "support.json"
_LOCK = threading.Lock()
_SENT = {}                                  # ip -> [timestamps]: at most 5 messages per hour per visitor
MAX_PER_HOUR = 5


def _read():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write(items):
    f = FILE()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def add(name, contact, message, ident="", ip="?"):
    """Save a message. Returns the record, or None if empty / the visitor sent too many."""
    message = (message or "").strip()[:2000]
    if not message:
        return None
    now = time.time()
    recent = [t for t in _SENT.get(ip, []) if now - t < 3600]
    if len(recent) >= MAX_PER_HOUR:
        _SENT[ip] = recent
        return None
    _SENT[ip] = recent + [now]
    rec = {"id": f"M{int(now * 1000)}", "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "name": (name or "").strip()[:80], "contact": (contact or "").strip()[:120],
           "message": message, "ident": (ident or "").strip()[:80], "status": "open"}
    with _LOCK:
        items = _read()
        items.append(rec)
        _write(items[-1000:])
    return rec


def all_messages():
    return list(reversed(_read()))


def open_count():
    return sum(1 for m in _read() if m.get("status") == "open")


def set_status(mid, status):
    with _LOCK:
        items = _read()
        for m in items:
            if m["id"] == mid:
                m["status"] = "done" if status == "done" else "open"
        _write(items)
