"""Badges made by the admin or by a doctor, given to students by hand.

data/custom_badges.json -> {"defs": [{"id", "name", "icon", "desc", "owner": "master" | <doctor id>, "created"}],
                            "awards": [{"badge", "student", "by", "time", "note", "seen": bool}]}
A badge made by the admin can reach every student; a badge made by a doctor reaches the students of that doctor's courses.
"""
import json
import threading
import time
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "custom_badges.json"
_lock = threading.Lock()
MASTER = "master"


def _read():
    try:
        d = json.loads(FILE().read_text(encoding="utf-8"))
        return {"defs": d.get("defs", []), "awards": d.get("awards", [])}
    except (OSError, ValueError):
        return {"defs": [], "awards": []}


def _write(d):
    f = FILE()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def defs():
    return _read()["defs"]


def get(bid):
    return next((b for b in defs() if b["id"] == bid), None)


def create(name, icon, desc, owner):
    name, desc = (name or "").strip()[:60], (desc or "").strip()[:300]
    icon = (icon or "").strip()[:8] or "⭐"
    if not name:
        return None
    rec = {"id": f"c{int(time.time() * 1000)}", "name": name, "icon": icon, "desc": desc, "owner": owner,
           "created": datetime.now().strftime("%Y-%m-%d")}
    with _lock:
        d = _read()
        d["defs"].append(rec)
        _write(d)
    return rec


def delete(bid, by, is_master):
    """Remove a badge (and its awards). Only its maker or the admin can."""
    with _lock:
        d = _read()
        b = next((x for x in d["defs"] if x["id"] == bid), None)
        if not b or not (is_master or b["owner"] == by):
            return False
        d["defs"] = [x for x in d["defs"] if x["id"] != bid]
        d["awards"] = [a for a in d["awards"] if a["badge"] != bid]
        _write(d)
    return True


def award(bid, students, by, note=""):
    """Give the badge to these student codes. Returns the codes that did not have it yet."""
    new = []
    with _lock:
        d = _read()
        if not any(b["id"] == bid for b in d["defs"]):
            return []
        have = {a["student"] for a in d["awards"] if a["badge"] == bid}
        for s in students:
            if s and s not in have:
                have.add(s)
                new.append(s)
                d["awards"].append({"badge": bid, "student": s, "by": by, "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "note": (note or "").strip()[:200], "seen": False})
        _write(d)
    return new


def revoke(bid, student):
    with _lock:
        d = _read()
        d["awards"] = [a for a in d["awards"] if not (a["badge"] == bid and a["student"] == student)]
        _write(d)


def awards():
    return _read()["awards"]


def for_student(code, owners):
    """Badges this student can see: those made by the admin, by the doctors of his courses (`owners`), or already given to him.
    -> [{id, name, icon, desc, owner, earned, when, note, new}]"""
    d = _read()
    mine = {a["badge"]: a for a in d["awards"] if a["student"] == code}
    out = []
    for b in d["defs"]:
        if b["owner"] == MASTER or b["owner"] in owners or b["id"] in mine:
            a = mine.get(b["id"])
            out.append({**b, "earned": a is not None, "when": a["time"][:10] if a else "", "note": a["note"] if a else "",
                        "new": bool(a and not a.get("seen"))})
    return out


def unseen_count(code):
    return sum(1 for a in _read()["awards"] if a["student"] == code and not a.get("seen"))


def mark_seen(code):
    with _lock:
        d = _read()
        ch = False
        for a in d["awards"]:
            if a["student"] == code and not a.get("seen"):
                a["seen"] = True
                ch = True
        if ch:
            _write(d)
