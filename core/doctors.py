"""Doctor accounts.

data/doctors.json -> [{"id", "name", "hash", "created", "initial", "new"}]
- The admin types a doctor name -> a random password such as  K7QD-M4PX2TNB  is made for him.
- The doctor can change it from his own Admin page.
- Sign-in checks a hash of the password. The plain passwords ("initial" = made by the system, "new" = chosen by
  the doctor) are kept only so they can be written to the admin's private Google Sheet (core/sheet_sync.py),
  as the course owner asked. This file never goes to GitHub (.gitignore).
"""
import json
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


def list_doctors():
    return [{"id": d["id"], "name": d["name"], "created": d.get("created", "")} for d in _load()]


def get(doctor_id):
    return next((d for d in list_doctors() if d["id"] == doctor_id), None)


def add(name):
    """Returns (doctor_id, password)."""
    with _lock:
        rows = _load()
        ids = {d["id"] for d in rows}
        did = _rand(4)
        while did in ids:
            did = _rand(4)
        pw = f"{did}-{_rand(8)}"
        rows.append({"id": did, "name": name.strip()[:60] or did, "hash": generate_password_hash(pw),
                     "created": datetime.now().strftime("%Y-%m-%d"), "initial": pw, "new": ""})
        _save(rows)
    return did, pw


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


def check(password):
    """The doctor id whose password this is, else None."""
    pw = (password or "").strip()
    if not pw:
        return None
    rows = _load()
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
    """[[name, courses, system password, doctor's own password]] – courses_of(doctor_id) -> 'AI, MAM336'."""
    return [[d["name"], courses_of(d["id"]), d.get("initial", ""), d.get("new", "")] for d in _load()]
