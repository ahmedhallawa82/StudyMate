"""Data vault: everything the site keeps about every person, in one place, for the MAIN ADMIN only.

Opened with its own password (data/vault_auth.json; until one is saved: STUDYMATE_VAULT_PASSWORD from the server settings,
else the main admin's password). The session forgets the unlock after IDLE seconds without a vault page.

Passwords of students are stored only as one-way hashes, so nobody (not even the admin) can read them; the vault shows
whether a password is set and lets the admin give a new one. A doctor's system password is shown while he still uses it.
"""
import hmac
import json
import os
import threading

from werkzeug.security import check_password_hash, generate_password_hash

import config
from core import adminpw, students, doctors, profiles, chat, bookmarks, audit, announce, notify, support, uploads, custom_badges, schedule, videos, exams

FILE = lambda: config.BASE_DIR / "data" / "vault_auth.json"
_lock = threading.Lock()
MIN_LEN = 8
IDLE = 20 * 60


# ------------------------------------------------------------------ password
def _hash():
    try:
        return json.loads(FILE().read_text(encoding="utf-8")).get("hash", "")
    except (OSError, ValueError):
        return ""


def verify(pw):
    pw = (pw or "").strip()
    if not pw:
        return False
    h = _hash()
    if h:
        return check_password_hash(h, pw)
    env = os.environ.get("STUDYMATE_VAULT_PASSWORD", "")
    if env:
        return hmac.compare_digest(pw, env)
    return adminpw.verify(pw)


def change(old, new):
    new = (new or "").strip()
    with _lock:
        if not verify(old):
            return "pw_old_wrong"
        if len(new) < MIN_LEN:
            return "vlt_pw_short"
        FILE().parent.mkdir(parents=True, exist_ok=True)
        FILE().write_text(json.dumps({"hash": generate_password_hash(new)}), encoding="utf-8")
    return ""


# ------------------------------------------------------------------ people
def _staff_pw(d):
    """The system password the admin may see (the one the doctor still uses), else ''."""
    return d.get("new") or d.get("initial") or ""


def people(sheets, course_titles):
    """Every account: [{key, kind, role, name, username, email, uni_code, dept, created, courses, last, n_q, n_a, n_v}]."""
    qs, an, vi = sheets.get("Questions", []), sheets.get("Answers", []), sheets.get("Visits", [])
    cnt = lambda rows, code: sum(1 for r in rows if r.get("student_code") == code)
    last = {}
    for r in qs + an + vi:
        c, t = r.get("student_code"), str(r.get("time", ""))
        if c and t > last.get(c, ""):
            last[c] = t
    out = [{"key": "d:" + doctors.MASTER, "kind": "staff", "role": "main", "name": (profiles.get("d:" + doctors.MASTER) or {}).get("name") or "Admin",
            "username": "admin", "email": (profiles.get("d:" + doctors.MASTER) or {}).get("email", ""), "uni_code": "", "dept": "", "created": "",
            "codes": [], "courses": [], "last": "", "n_q": 0, "n_a": 0, "n_v": 0}]
    owners = {}
    for c in config.list_courses():
        owners.setdefault(c["meta"].get("owner"), []).append(c["code"])
    for d in doctors.list_doctors():
        out.append({"key": "d:" + d["id"], "kind": "staff", "role": "admin" if d.get("role") == "admin" else "doctor", "name": d.get("name", ""),
                    "username": doctors.username_of(d), "email": d.get("email", ""), "uni_code": "", "dept": d.get("dept", ""),
                    "created": d.get("created", ""), "codes": owners.get(d["id"], []), "courses": [course_titles.get(c, c) for c in owners.get(d["id"], [])], "last": "", "n_q": 0, "n_a": 0, "n_v": 0})
    for s in students.list_students():
        code = s["code"]
        out.append({"key": "s:" + code, "kind": "student", "role": "student", "name": f"{s.get('first', '')} {s.get('last', '')}".strip(),
                    "username": s.get("username", ""), "email": s.get("email", ""), "uni_code": s.get("uni_code", ""), "dept": "",
                    "created": s.get("created", ""), "codes": list(s.get("courses", [])), "courses": [course_titles.get(c, c) for c in s.get("courses", [])],
                    "last": last.get(code, "")[:16], "n_q": cnt(qs, code), "n_a": cnt(an, code), "n_v": cnt(vi, code)})
    return out


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:                                       # noqa: BLE001 - one broken store must not hide the rest
        print("vault section skipped:", type(e).__name__, e)
        return default


def _raw_doctor(did):
    return next((d for d in doctors._load() if d["id"] == did), None)


def profile(key, sheets, course_titles, name_of_key):
    """Everything about one person. None when the key is unknown."""
    kind, _, ident = (key or "").partition(":")
    p = {"key": key, "kind": kind}
    if kind == "s":
        s = students.get(ident)
        if not s:
            return None
        p.update(role="student", name=f"{s.get('first', '')} {s.get('last', '')}".strip(), username=s.get("username", ""), email=s.get("email", ""),
                 uni_code=s.get("uni_code", ""), code=ident, created=s.get("created", ""), courses=[(c, course_titles.get(c, c)) for c in s.get("courses", [])],
                 pw_state="hash", pw_plain="")
        mine = lambda rows: [r for r in rows if r.get("student_code") == ident]
        p["questions"] = mine(sheets.get("Questions", []))[::-1]
        p["answers"] = mine(sheets.get("Answers", []))[::-1]
        p["visits"] = mine(sheets.get("Visits", []))
        p["exams_log"] = mine(sheets.get("Exams", []))[::-1]
        p["attempts"] = _safe(lambda: [dict(a, course=c) for c in course_titles for a in exams.list_attempts(c, ident)], [])
        p["saved"] = _safe(lambda: bookmarks.listing(ident), [])
        p["badges"] = _safe(lambda: [a for a in custom_badges._read().get("awards", []) if a.get("student") == ident], [])
        idents = {ident.lower(), s.get("username", "").lower(), s.get("email", "").lower()} - {""}
    elif kind == "d":
        if ident == doctors.MASTER:
            prof = profiles.get("d:" + doctors.MASTER) or {}
            p.update(role="main", name=prof.get("name") or "Admin", username="admin", email=prof.get("email", ""), created="", courses=[], dept="",
                     pw_state="env", pw_plain="", perms=["all"])
            actor_names = {"Admin"}
        else:
            d = _raw_doctor(ident)
            if not d:
                return None
            p.update(role="admin" if d.get("role") == "admin" else "doctor", name=d.get("name", ""), username=doctors.username_of(d), email=d.get("email", ""),
                     dept=d.get("dept", ""), created=d.get("created", ""), perms=d.get("perms", []), linked_student=d.get("student", ""),
                     courses=[(c["code"], course_titles.get(c["code"], c["code"])) for c in config.list_courses() if c["meta"].get("owner") == ident],
                     pw_state="hash", pw_plain=_staff_pw(d))
            actor_names = {d.get("name", ""), doctors.username_of(d), ident} - {""}
        p["audit"] = _safe(lambda: [r for r in audit.rows(limit=2000) if r.get("actor") in actor_names], [])
        p["announcements"] = _safe(lambda: [a for a in announce._load() if a.get("by") == ident], [])
        p["events"] = _safe(lambda: [e for e in schedule._load() if e.get("by") in actor_names | {ident}], [])
        p["made_badges"] = _safe(lambda: [b for b in custom_badges._read().get("defs", []) if b.get("owner") == ident], [])
        p["videos"] = _safe(lambda: [dict(v, course=c) for c in course_titles for part in videos.items(c).values() for v in part if v.get("by") in actor_names], [])
        p["lectures"] = _safe(lambda: [(c, f.name) for c, _ in p.get("courses", []) for f in sorted(config.course_paths(c).lectures.glob("*.pdf"))], [])
        idents = {ident.lower(), p.get("username", "").lower(), p.get("email", "").lower()} - {""}
    else:
        return None
    # common to everybody
    p["avatar"] = bool(profiles.avatar_path(key))
    p["uploads"] = _safe(lambda: uploads.of(key), [])
    p["notifs"] = _safe(lambda: notify.for_user(key, limit=50), [])
    p["support"] = _safe(lambda: [m for m in support._read() if str(m.get("ident", "")).lower() in idents or str(m.get("contact", "")).lower() in idents], [])
    p["chat"] = _safe(lambda: _chat_of(key, name_of_key), {"threads": [], "files": [], "sent": 0})
    p["last"] = max([str(r.get("time", "")) for r in p.get("questions", []) + p.get("answers", []) + p.get("visits", [])] + [r.get("time", "") for r in p.get("audit", [])] + [""])[:16]
    return p


def _chat_of(key, name_of_key):
    d = chat._read()
    threads, files, sent = [], [], 0
    for tid_, th in d.get("threads", {}).items():
        a, _, b = tid_.partition("|")
        if key not in (a, b):
            continue
        other = b if a == key else a
        msgs = th.get("msgs", [])
        mine = [m for m in msgs if m.get("from") == key]
        sent += len(mine)
        for m in msgs:
            if m.get("file"):
                files.append({**m["file"], "time": m.get("time", ""), "from_me": m.get("from") == key, "with": name_of_key(other)})
        threads.append({"with": name_of_key(other), "with_key": other, "n": len(msgs), "mine": len(mine), "last": msgs[-1]["time"] if msgs else "",
                        "msgs": msgs[-200:]})
    links = d.get("links", {})
    reqs = [{"with": name_of_key(chat.other(k, key)), "state": (v or {}).get("status", ""), "asked_by_me": (v or {}).get("from") == key} for k, v in links.items() if key in k.split("|")] if isinstance(links, dict) else []
    blocks = d.get("blocks", {}).get(key, []) if isinstance(d.get("blocks"), dict) else []
    return {"threads": sorted(threads, key=lambda t: t["last"], reverse=True), "files": files[::-1], "sent": sent,
            "requests": reqs, "blocked": [name_of_key(k) for k in blocks]}
