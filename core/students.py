"""Student accounts: first name, last name, e-mail, password (stored only as a hash).

data/students.json -> [{"code", "first", "last", "username", "email", "hash", "created", "courses": [course codes]}]   (never goes to GitHub)
Every new student is also written (without the password) to the "Students" sheet of logs.xlsx so the admin can
download the list as Excel / CSV.
"""
import json
import re
import secrets
import threading
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

import config

FILE = lambda: config.BASE_DIR / "data" / "students.json"
_lock = threading.Lock()
MIN_LEN = 6
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _load():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(rows):
    FILE().parent.mkdir(parents=True, exist_ok=True)
    FILE().write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def norm_email(e):
    return (e or "").strip().lower()


_USER = re.compile(r"^[a-z0-9_.]{3,20}$")


def username_of(s):
    return s.get("username") or s["code"].lower()


def public(s):
    return {"code": s["code"], "first": s["first"], "last": s["last"], "email": s["email"], "created": s["created"],
            "username": username_of(s), "courses": list(s.get("courses", []))}


def get(code):
    s = next((x for x in _load() if x["code"] == code), None)
    return public(s) if s else None


def list_students():
    return [public(s) for s in _load()]


def find(ident):
    """A student by e-mail or by username."""
    e = norm_email(ident)
    return next((s for s in _load() if s["email"] == e or username_of(s).lower() == e), None)


def register(first, last, email, password, username="", reserved=()):
    """Returns (student dict, error key). error key '' = done. `reserved` = usernames nobody may take (admin, doctors)."""
    first, last, email = (first or "").strip()[:40], (last or "").strip()[:40], norm_email(email)
    username = (username or "").strip().lower()
    if not first or not last:
        return None, "reg_name_missing"
    if not _EMAIL.match(email):
        return None, "reg_email_bad"
    if len(password or "") < MIN_LEN:
        return None, "reg_pw_short"
    if username and not _USER.match(username):
        return None, "reg_user_bad"
    with _lock:
        rows = _load()
        if any(s["email"] == email for s in rows):
            return None, "reg_email_taken"
        if not username:                                          # not given: made from the e-mail
            base = re.sub(r"[^a-z0-9_.]", "", email.split("@")[0])[:16] or "student"
            username = base if len(base) >= 3 else base + "123"
            n = 1
            while username in reserved or any(username_of(s).lower() == username for s in rows):
                n += 1
                username = f"{base[:16]}{n}"
        elif username in reserved or any(username_of(s).lower() == username for s in rows):
            return None, "reg_user_taken"
        used = {s["code"] for s in rows}
        n = len(rows) + 1
        while f"S{n:04d}" in used:
            n += 1
        s = {"code": f"S{n:04d}", "first": first, "last": last, "email": email, "username": username, "courses": [],
             "hash": generate_password_hash(password), "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
        rows.append(s)
        _save(rows)
    return s, ""


def check(ident, password):
    s = find(ident)
    if s and check_password_hash(s["hash"], password or ""):
        return s
    return None


def change_password(code, old, new):
    """Returns an error key ('' = done)."""
    with _lock:
        rows = _load()
        me = next((s for s in rows if s["code"] == code), None)
        if not me or not check_password_hash(me["hash"], old or ""):
            return "pw_old_wrong"
        if len(new or "") < MIN_LEN:
            return "reg_pw_short"
        me["hash"] = generate_password_hash(new)
        _save(rows)
    return ""


def reset_password(email):
    """A new random password for this e-mail (None if there is no such student)."""
    with _lock:
        rows = _load()
        me = next((s for s in rows if s["email"] == norm_email(email)), None)
        if not me:
            return None, None
        pw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        me["hash"] = generate_password_hash(pw)
        _save(rows)
    return me, pw


def set_courses(code, courses):
    """The courses this student registered in (list of course codes)."""
    with _lock:
        rows = _load()
        me = next((s for s in rows if s["code"] == code), None)
        if not me:
            return False
        me["courses"] = list(dict.fromkeys(courses))
        _save(rows)
    return True
