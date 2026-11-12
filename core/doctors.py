"""Doctor accounts.

data/doctors.json -> [{"id", "name", "hash", "created", "initial", "new"}]
- The admin types a doctor name -> a random password such as  K7QD-M4PX2TNB  is made for him.
- The doctor can change it from his own Admin page.
- Sign-in checks a hash of the password. The plain passwords ("initial" = made by the system, "new" = chosen by
  the doctor) are kept only so they can be written to the admin's private Google Sheet (core/sheet_sync.py),
  as the course owner asked. This file never goes to GitHub (.gitignore).
"""
import json
import re
import secrets
import threading
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

import config

FILE = lambda: config.BASE_DIR / "data" / "doctors.json"
_lock = threading.Lock()
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"          # no 0/O/1/I/L: easy to read out loud
MASTER = "master"
MIN_LEN = 8
PERMS = ("content", "exams", "badges", "data", "students", "chat", "support", "doctors", "announce")     # what a sub-admin may be given


def _load():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(rows):
    FILE().parent.mkdir(parents=True, exist_ok=True)
    FILE().write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def _rand(n):
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def username_of(d):
    return d.get("username") or ("dr" + d["id"].lower())


def list_doctors(role=None):
    """All staff accounts; role="doctor" / "admin" keeps one kind."""
    return [{"id": d["id"], "name": d["name"], "email": d.get("email", ""), "username": username_of(d),
             "created": d.get("created", ""), "role": d.get("role", "doctor"), "dept": d.get("dept", ""), "perms": [p for p in d.get("perms", []) if p in PERMS], "student": d.get("student", "")} for d in _load()
            if role is None or d.get("role", "doctor") == role]


def get(doctor_id):
    return next((d for d in list_doctors() if d["id"] == doctor_id), None)


def add(name, email="", username="", password="", role="doctor", perms=None):
    """Returns (doctor_id, password). A sub-admin (role 'admin') gets a chosen username / password and a list of permissions.
    Raises ValueError('adms_user_taken' | 'pw_too_short' | 'adms_user_bad')."""
    username = (username or "").strip()
    password = (password or "").strip()
    if username and not re.fullmatch(r"[A-Za-z0-9._-]{3,30}", username):
        raise ValueError("adms_user_bad")
    if password and len(password) < MIN_LEN:
        raise ValueError("pw_too_short")
    with _lock:
        rows = _load()
        if username and (username.lower() in ("admin", "master") or any(username_of(d).lower() == username.lower() for d in rows)):
            raise ValueError("adms_user_taken")
        ids = {d["id"] for d in rows}
        did = _rand(4)
        while did in ids:
            did = _rand(4)
        pw = password or f"{did}-{_rand(8)}"
        rec = {"id": did, "name": name.strip()[:60] or did, "email": (email or "").strip()[:120], "hash": generate_password_hash(pw),
               "created": datetime.now().strftime("%Y-%m-%d"), "initial": pw, "new": ""}
        if username:
            rec["username"] = username
        if role == "admin":
            rec["role"] = "admin"
            rec["perms"] = [p for p in (perms or []) if p in PERMS]
        rows.append(rec)
        _save(rows)
    return did, pw


def add_hashed(name, email, username, pw_hash, dept=""):
    """A doctor account whose password was chosen by the doctor himself (already hashed). Raises ValueError('adms_user_taken' | 'adms_user_bad')."""
    username = (username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,30}", username):
        raise ValueError("adms_user_bad")
    with _lock:
        rows = _load()
        if username.lower() in ("admin", "master") or any(username_of(d).lower() == username.lower() for d in rows):
            raise ValueError("adms_user_taken")
        ids = {d["id"] for d in rows}
        did = _rand(4)
        while did in ids:
            did = _rand(4)
        rows.append({"id": did, "name": name.strip()[:60] or did, "email": (email or "").strip()[:120], "hash": pw_hash,
                     "created": datetime.now().strftime("%Y-%m-%d"), "initial": "", "new": "", "username": username, "dept": (dept or "").strip()[:120]})
        _save(rows)
    return did


def by_student(code):
    """The admin account made from this student, if any."""
    return next((d["id"] for d in _load() if code and d.get("student") == code), None)


def add_linked(student, perms):
    """Turn a registered student into an admin (he keeps signing in with his own username and password). Returns the admin id."""
    if by_student(student["code"]):
        return by_student(student["code"])
    with _lock:
        rows = _load()
        ids = {d["id"] for d in rows}
        did = _rand(4)
        while did in ids:
            did = _rand(4)
        rows.append({"id": did, "name": (f"{student['first']} {student['last']}").strip()[:60] or did, "email": student.get("email", ""),
                     "username": "adm." + student["username"][:25], "hash": generate_password_hash(secrets.token_hex(16)), "created": datetime.now().strftime("%Y-%m-%d"),
                     "initial": "", "new": "", "role": "admin", "perms": [p for p in (perms or []) if p in PERMS], "student": student["code"]})
        _save(rows)
    return did


def set_perms(doctor_id, perms):
    with _lock:
        rows = _load()
        for d in rows:
            if d["id"] == doctor_id and d.get("role") == "admin":
                d["perms"] = [p for p in (perms or []) if p in PERMS]
                _save(rows)
                return True
    return False


def reset(doctor_id):
    """A new random password; the doctor's own password stops working."""
    with _lock:
        rows = _load()
        for d in rows:
            if d["id"] == doctor_id:
                pw = f"{doctor_id}-{_rand(8)}"
                d.update(hash=generate_password_hash(pw), initial=pw, new="")
                _save(rows)
                return pw
    return None


def remove(doctor_id):
    with _lock:
        _save([d for d in _load() if d["id"] != doctor_id])


def check(password, username=None):
    """The doctor id whose password this is, else None. With a username only that doctor is tried."""
    pw = (password or "").strip()
    if not pw:
        return None
    rows = _load()
    if username:
        rows = [d for d in rows if username_of(d).lower() == username.strip().lower()]
    head = pw.upper().split("-", 1)[0]                     # system passwords start with the doctor id: try him first
    rows.sort(key=lambda d: d["id"] != head)
    for d in rows:
        if check_password_hash(d["hash"], pw) or check_password_hash(d["hash"], pw.upper()):
            return d["id"]
    return None


def change_password(doctor_id, old, new, master_password=""):
    """Returns an error key ('' = done)."""
    new = (new or "").strip()
    with _lock:
        rows = _load()
        me = next((d for d in rows if d["id"] == doctor_id), None)
        if not me or not (check_password_hash(me["hash"], (old or "").strip()) or
                          check_password_hash(me["hash"], (old or "").strip().upper())):
            return "pw_old_wrong"
        if len(new) < MIN_LEN:
            return "pw_too_short"
        if new == master_password or any(check_password_hash(d["hash"], new) for d in rows if d is not me):
            return "pw_taken"
        me.update(hash=generate_password_hash(new), new=new)
        _save(rows)
    return ""


def sheet_rows(courses_of):
    """[[name, e-mail, username, courses, system password, doctor's own password]] – courses_of(doctor_id) -> 'AI, MAM336'."""
    return [[d["name"], d.get("email", ""), username_of(d), courses_of(d["id"]), d.get("initial", ""), d.get("new", "")]
            for d in _load()]


def update_profile(doctor_id, name, email):
    """Change the doctor's display name / e-mail."""
    with _lock:
        rows = _load()
        me = next((d for d in rows if d["id"] == doctor_id), None)
        if not me:
            return False
        me["name"] = (name or me["name"]).strip()[:60] or me["name"]
        me["email"] = (email or "").strip()[:120]
        _save(rows)
    return True


def reset_by_email(email):
    """A new strong random password for the doctor with this e-mail. Returns (doctor dict, password) or (None, None)."""
    from core import passgen
    email = (email or "").strip().lower()
    if not email:
        return None, None
    with _lock:
        rows = _load()
        for d in rows:
            if d.get("email", "").strip().lower() == email:
                pw = passgen.generate()
                d.update(hash=generate_password_hash(pw), initial=pw, new="")
                _save(rows)
                return dict(d), pw
    return None, None


def find_by_email(email):
    email = (email or "").strip().lower()
    return next((dict(d) for d in _load() if email and d.get("email", "").strip().lower() == email), None)


def set_password(doctor_id, pw):
    """Save a new password for this doctor (also shown to the admin as the system password); it works at once."""
    with _lock:
        rows = _load()
        for d in rows:
            if d["id"] == doctor_id:
                d.update(hash=generate_password_hash(pw), initial=pw, new="")
                _save(rows)
                return True
    return False
