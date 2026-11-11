"""The password that opens the hidden "AI models" page (main admin only).

Order: a password saved from that page (hashed, data/models_auth.json) -> STUDYMATE_MODELS_PASSWORD from the server
settings -> the main admin's own password. So it works from day one and can be made separate at any time."""
import hmac
import json
import os
import threading

from werkzeug.security import check_password_hash, generate_password_hash

import config
from core import adminpw

FILE = lambda: config.BASE_DIR / "data" / "models_auth.json"
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
    if h:
        return check_password_hash(h, pw)
    env = os.environ.get("STUDYMATE_MODELS_PASSWORD", "")
    if env:
        return hmac.compare_digest(pw, env)
    return adminpw.verify(pw)


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
