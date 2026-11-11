"""Doctors' follow-up of the students' questions: which question was answered (data/followups.json).
Key = the question id in logs.xlsx (sheet Questions). Value = who, when and an optional note."""
import json
import threading
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "followups.json"
_lock = threading.Lock()


def load():
    try:
        d = json.loads(FILE().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    f = FILE()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def mark(qid, by, note=""):
    with _lock:
        d = load()
        d[str(qid)] = {"by": by, "when": datetime.now().strftime("%Y-%m-%d %H:%M"), "note": (note or "").strip()[:300]}
        _save(d)


def reopen(qid):
    with _lock:
        d = load()
        d.pop(str(qid), None)
        _save(d)
