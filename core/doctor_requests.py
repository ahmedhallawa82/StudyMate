"""Doctors who ask for an account on the register page. The main admin approves or rejects them (data/doctor_requests.json).
The password is stored hashed only; on approval the doctor account is created with that hash."""
import json
import re
import threading
from datetime import datetime

from werkzeug.security import generate_password_hash

import config

FILE = lambda: config.BASE_DIR / "data" / "doctor_requests.json"
_lock = threading.Lock()
MIN_LEN = 8


def _load():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(rows):
    FILE().parent.mkdir(parents=True, exist_ok=True)
    FILE().write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def pending():
    return [{k: v for k, v in r.items() if k != "hash"} for r in _load()]


def get(rid):
    return next((r for r in _load() if r["id"] == rid), None)


def add(name, email, username, password, dept="", taken=()):
    """Returns (request, error) with error '' | 'need_all' | 'adms_user_bad' | 'adms_user_taken' | 'pw_too_short'."""
    name, email, username, dept = (name or "").strip()[:60], (email or "").strip()[:120], (username or "").strip(), (dept or "").strip()[:120]
    if not (name and email and username and password and dept):
        return None, "need_all"
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,30}", username):
        return None, "adms_user_bad"
    if len(password) < MIN_LEN:
        return None, "pw_too_short"
    with _lock:
        rows = _load()
        if username.lower() in {x.lower() for x in taken} | {"admin", "master"} or any(r["username"].lower() == username.lower() for r in rows):
            return None, "adms_user_taken"
        rid = (max([r["id"] for r in rows]) + 1) if rows else 1
        rec = {"id": rid, "name": name, "email": email, "username": username, "dept": dept, "hash": generate_password_hash(password),
               "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
        rows.append(rec)
        _save(rows)
    return {k: v for k, v in rec.items() if k != "hash"}, ""


def remove(rid):
    with _lock:
        rows = _load()
        keep = [r for r in rows if r["id"] != rid]
        _save(keep)
        return len(keep) != len(rows)
