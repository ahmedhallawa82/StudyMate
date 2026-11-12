"""Who changed what and when (admin side): data/audit.jsonl, one JSON line per action, newest read first."""
import json
import threading
from datetime import datetime

import config

FILE = lambda: config.BASE_DIR / "data" / "audit.jsonl"
_lock = threading.Lock()
KEEP = 2000


def record(actor, action, target=""):
    """Never raises: a failed audit line must not break the action itself."""
    try:
        line = json.dumps({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "actor": str(actor or "")[:80],
                           "action": str(action)[:60], "target": str(target or "")[:200]}, ensure_ascii=False)
        with _lock:
            f = FILE()
            f.parent.mkdir(parents=True, exist_ok=True)
            with f.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception as e:                                      # noqa: BLE001
        print("audit skipped:", e)


def rows(limit=300, actor="", action=""):
    try:
        lines = FILE().read_text(encoding="utf-8").splitlines()[-KEEP:]
    except OSError:
        return []
    out = []
    for ln in reversed(lines):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if actor and actor.lower() not in r["actor"].lower():
            continue
        if action and action != r["action"]:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def actions():
    return sorted({r["action"] for r in rows(KEEP)})
