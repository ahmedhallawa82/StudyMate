"""Direct messages between people on the site (student <-> student, student <-> doctor, doctor <-> admin ...).

data/chat.json -> {"threads": {"<keyA>|<keyB>": {"msgs": [{"id", "from", "text", "time"}], "read": {"<user key>": last read message id}}}}
A user key is "s:<student code>" or "d:<doctor id>" ("d:master" is the main admin), the same keys the notifications use.
"""
import json
import threading
import time
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "chat.json"
_lock = threading.Lock()
MAX_LEN = 1000
KEEP = 400                  # messages kept per conversation
RATE = (20, 60)             # at most 20 messages per 60 seconds per person
_sent = {}


def _read():
    try:
        d = json.loads(FILE().read_text(encoding="utf-8"))
        return {"threads": d.get("threads", {})}
    except (OSError, ValueError):
        return {"threads": {}}


def _write(d):
    f = FILE()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def tid(a, b):
    return "|".join(sorted((a, b)))


def other(thread_id, me):
    a, b = thread_id.split("|")
    return b if a == me else a


def send(frm, to, text):
    """Add a message. Returns (message, error) where error is '' | 'empty' | 'self' | 'rate'."""
    text = (text or "").strip()[:MAX_LEN]
    if not text:
        return None, "empty"
    if frm == to:
        return None, "self"
    now = time.time()
    with _lock:
        recent = [t for t in _sent.get(frm, []) if now - t < RATE[1]]
        if len(recent) >= RATE[0]:
            _sent[frm] = recent
            return None, "rate"
        _sent[frm] = recent + [now]
        d = _read()
        th = d["threads"].setdefault(tid(frm, to), {"msgs": [], "read": {}})
        mid = (th["msgs"][-1]["id"] + 1) if th["msgs"] else 1
        msg = {"id": mid, "from": frm, "text": text, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
        th["msgs"] = (th["msgs"] + [msg])[-KEEP:]
        th["read"][frm] = mid                      # what I wrote I have read
        _write(d)
    return msg, ""


def messages(me, with_key, after=0):
    th = _read()["threads"].get(tid(me, with_key), {"msgs": []})
    return [m for m in th["msgs"] if m["id"] > after]


def mark_read(me, with_key):
    with _lock:
        d = _read()
        th = d["threads"].get(tid(me, with_key))
        if th and th["msgs"] and th["read"].get(me, 0) < th["msgs"][-1]["id"]:
            th["read"][me] = th["msgs"][-1]["id"]
            _write(d)


def threads_for(me):
    """[{with, last, unread}] newest first."""
    out = []
    for t, th in _read()["threads"].items():
        if me not in t.split("|") or not th["msgs"]:
            continue
        seen = th["read"].get(me, 0)
        out.append({"with": other(t, me), "last": th["msgs"][-1],
                    "unread": sum(1 for m in th["msgs"] if m["id"] > seen and m["from"] != me)})
    return sorted(out, key=lambda x: (x["last"]["time"], x["last"]["id"]), reverse=True)


def unread_total(me):
    return sum(x["unread"] for x in threads_for(me))
