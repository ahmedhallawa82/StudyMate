"""Doctor accounts: every doctor has a private access code; the courses he creates are registered under his name.

data/doctors.json  ->  [{"id", "name", "hash", "created"}].  A code looks like  K7QD-M4PX2TNB  (id - secret).
Only a hash of the code is stored, so the code is shown once (when the doctor is created or his code is reset).
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
    """Returns (doctor_id, code). The code cannot be read again later."""
    with _lock:
        rows = _load()
        ids = {d["id"] for d in rows}
        did = _rand(4)
        while did in ids:
            did = _rand(4)
        secret = _rand(8)
        rows.append({"id": did, "name": name.strip()[:60] or did, "hash": generate_password_hash(secret),
                     "created": datetime.now().strftime("%Y-%m-%d")})
        _save(rows)
    return did, f"{did}-{secret}"


def reset(doctor_id):
    with _lock:
        rows = _load()
        for d in rows:
            if d["id"] == doctor_id:
                secret = _rand(8)
                d["hash"] = generate_password_hash(secret)
                _save(rows)
                return f"{doctor_id}-{secret}"
    return None


def remove(doctor_id):
    with _lock:
        rows = _load()
        _save([d for d in rows if d["id"] != doctor_id])


def check(code):
    """The doctor id if the code is right, else None."""
    code = (code or "").strip().upper().replace(" ", "")
    if "-" not in code:
        return None
    did, secret = code.split("-", 1)
    d = next((d for d in _load() if d["id"] == did), None)
    return did if d and check_password_hash(d["hash"], secret) else None
