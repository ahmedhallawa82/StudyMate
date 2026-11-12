"""Files people upload that no other store keeps (for now: the pictures sent with "Ask with a photo").

data/uploads/<user key>/<time>_<name>      the file itself (never goes to GitHub)
data/uploads/index.jsonl                   one line per file: {"time", "key", "kind", "file", "name", "size", "note"}
Only the main admin can open them, from the Data vault.
"""
import json
import re
import threading
from datetime import datetime

import config

DIR = lambda: config.BASE_DIR / "data" / "uploads"
_lock = threading.Lock()


def _safe(s, n=60):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s or ""))[:n]


def save(key, kind, data, name="file", note=""):
    """Keep a copy. Never raises: a failed copy must not break the student's action."""
    try:
        ts = datetime.now()
        folder = DIR() / _safe(key.replace(":", "_"))
        folder.mkdir(parents=True, exist_ok=True)
        fname = f"{ts:%Y%m%d-%H%M%S-%f}_{_safe(name, 40)}"
        (folder / fname).write_bytes(data)
        rec = {"time": f"{ts:%Y-%m-%d %H:%M}", "key": key, "kind": kind, "file": f"{folder.name}/{fname}",
               "name": str(name)[:80], "size": len(data), "note": str(note or "")[:400]}
        with _lock:
            with (DIR() / "index.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec
    except Exception as e:                                       # noqa: BLE001
        print("upload copy skipped:", e)
        return None


def of(key):
    try:
        lines = (DIR() / "index.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("key") == key and (DIR() / r["file"]).exists():
            out.append(r)
    return out[::-1]


def path(rel):
    """Absolute path of a stored upload, or None when the name is not inside data/uploads."""
    p = (DIR() / rel).resolve()
    return p if str(p).startswith(str(DIR().resolve())) and p.is_file() else None


def purge(key):
    import shutil
    shutil.rmtree(DIR() / _safe(key.replace(":", "_")), ignore_errors=True)
