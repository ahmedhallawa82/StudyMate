"""Direct messages between people on the site (student <-> student, student <-> doctor, doctor <-> admin ...).

data/chat.json -> {"threads": {"<keyA>|<keyB>": {"msgs": [{"id", "from", "text", "time"}], "read": {"<user key>": last read message id}}}}
A user key is "s:<student code>" or "d:<doctor id>" ("d:master" is the main admin), the same keys the notifications use.
"""
import json
import secrets
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
FILES = lambda: config.BASE_DIR / "data" / "chat_files"
MAX_FILE = 15 * 1024 * 1024
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
BLOCKED_EXT = {"exe", "bat", "cmd", "com", "scr", "msi", "sh", "ps1", "vbs", "js", "jar", "dll", "html", "htm", "svg", "php"}


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


def save_file(storage):
    """Store an uploaded file. Returns ({"fid","fname","size","img"}, error) with error '' | 'file_big' | 'file_type'."""
    name = (getattr(storage, "filename", "") or "").replace("\\", "/").split("/")[-1].strip()[:120]
    if not name:
        return None, "file_type"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in BLOCKED_EXT:
        return None, "file_type"
    data = storage.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        return None, "file_big"
    FILES().mkdir(parents=True, exist_ok=True)
    fid = secrets.token_hex(12) + (("." + ext) if ext.isalnum() and len(ext) <= 8 else "")
    (FILES() / fid).write_bytes(data)
    return {"fid": fid, "fname": name, "size": len(data), "img": ext in IMAGE_EXT}, ""


def send(frm, to, text, file=None):
    """Add a message (text and/or an attached file). Returns (message, error) where error is '' | 'empty' | 'self' | 'rate'."""
    text = (text or "").strip()[:MAX_LEN]
    if not text and not file:
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
        mid = (th["msgs"][-1]["id"] + 1) if th["msgs"] else (max(th.get("gone", {}).values(), default=0) + 1)
        msg = {"id": mid, "from": frm, "text": text, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
        if file:
            msg["file"] = file
        th["msgs"] = (th["msgs"] + [msg])[-KEEP:]
        th["read"][frm] = mid                      # what I wrote I have read
        _write(d)
    return msg, ""


def _visible(th, me):
    gone = th.get("gone", {}).get(me, 0)
    return [m for m in th["msgs"] if m["id"] > gone]


def messages(me, with_key, after=0):
    th = _read()["threads"].get(tid(me, with_key), {"msgs": []})
    return [m for m in _visible(th, me) if m["id"] > after]


def seen_upto(me, with_key):
    """Id of the last message the other person has read in this conversation."""
    return _read()["threads"].get(tid(me, with_key), {}).get("read", {}).get(with_key, 0)


def file_allowed(me, fid):
    """The message that carries this file, if me is in that conversation and has not deleted it."""
    for t, th in _read()["threads"].items():
        if me in t.split("|"):
            for m in _visible(th, me):
                if m.get("file", {}).get("fid") == fid:
                    return m
    return None


def close(me, with_key):
    """Close the conversation for good on my side (the other person keeps his copy). When both sides closed it, it and its files are deleted."""
    with _lock:
        d = _read()
        t = tid(me, with_key)
        th = d["threads"].get(t)
        if not th:
            return
        last = th["msgs"][-1]["id"] if th["msgs"] else 0
        th.setdefault("gone", {})[me] = last
        th["read"][me] = last
        a, b = t.split("|")
        if th["gone"].get(a, 0) >= last and th["gone"].get(b, 0) >= last:
            _drop_files(th["msgs"])
            th["msgs"] = []
            th["read"] = {}
        _write(d)


def _drop_files(msgs):
    for m in msgs:
        fid = (m.get("file") or {}).get("fid")
        if fid:
            try:
                (FILES() / fid).unlink()
            except OSError:
                pass


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
        vis = _visible(th, me) if me in t.split("|") else []
        if not vis:
            continue
        seen = th["read"].get(me, 0)
        out.append({"with": other(t, me), "last": vis[-1],
                    "unread": sum(1 for m in vis if m["id"] > seen and m["from"] != me)})
    return sorted(out, key=lambda x: (x["last"]["time"], x["last"]["id"]), reverse=True)


def unread_total(me):
    return sum(x["unread"] for x in threads_for(me))


def purge(key):
    """Delete every conversation this user is in."""
    with _lock:
        d = _read()
        for t, v in d["threads"].items():
            if key in t.split("|"):
                _drop_files(v["msgs"])
        d["threads"] = {t: v for t, v in d["threads"].items() if key not in t.split("|")}
        _write(d)
