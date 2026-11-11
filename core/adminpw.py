"""The main admin's password. It starts as LECTURER_PASSWORD from the server settings; once the admin changes it from the
profile page, the new password is kept (hashed) in data/admin_auth.json and wins over the server setting."""
import hmac
import json
import threading

from werkzeug.security import check_password_hash, generate_password_hash

import config

FILE = lambda: config.BASE_DIR / "data" / "admin_auth.json"
_lock = threading.Lock()
MIN_LEN = 6


def _hash():
    try:
        return json.loads(FILE().read_text(encoding="utf-8")).get("hash", "")
    except (OSError, ValueError):
        return ""


def verify(pw):
    pw = (pw or "").strip()
    h = _hash()
    return check_password_hash(h, pw) if h else hmac.compare_digest(pw, config.LECTURER_PASSWORD)


def change(old, new):
    """'' when done, else an error key."""
    new = (new or "").strip()
    with _lock:
        if not verify(old):
            return "pw_old_wrong"
        if len(new) < MIN_LEN:
            return "pw_too_short"
        f = FILE()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"hash": generate_password_hash(new)}), encoding="utf-8")
    return ""
