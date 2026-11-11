"""Student accounts: first name, last name, e-mail, password (stored only as a hash).

data/students.json -> [{"code", "first", "last", "email", "hash", "created"}]   (never goes to GitHub)
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


def public(s):
    return {k: s[k] for k in ("code", "first", "last", "email", "created")}


def list_students():
    return [public(s) for s in _load()]


def find(email):
    e = norm_email(email)
    return next((s for s in _load() if s["email"] == e), None)


def register(first, last, email, password):
    """Returns (student dict, error key). error key '' = done."""
    first, last, email = (first or "").strip()[:40], (last or "").strip()[:40], norm_email(email)
    if not first or not last:
        return None, "reg_name_missing"
    if not _EMAIL.match(email):
        return None, "reg_email_bad"
    if len(password or "") < MIN_LEN:
        return None, "reg_pw_short"
    with _lock:
        rows = _load()
        if any(s["email"] == email for s in rows):
            return None, "reg_email_taken"
        used = {s["code"] for s in rows}
        n = len(rows) + 1
        while f"S{n:04d}" in used:
            n += 1
        s = {"code": f"S{n:04d}", "first": first, "last": last, "email": email,
             "hash": generate_password_hash(password), "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
        rows.append(s)
        _save(rows)
    return s, ""


def check(email, password):
    s = find(email)
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
