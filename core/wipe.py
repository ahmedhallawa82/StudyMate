"""Danger zone: delete parts of the site (or everything) after a waiting period that the main admin can cancel.

Flow (enforced on the server, see app.py /vault/danger):
  1. type the delete sentence           2. choose what to delete
  3. read the warning: the "I agree" button unlocks after a 10-second countdown
  4. type the security code (set in advance, stored as a hash)
  5. the deletion is SCHEDULED (3 or 24 hours). The site keeps working; the main admin sees a red banner and can cancel.
  6. when the time has passed, the first request to the site (or scripts/run_wipe.py from a scheduled task) runs it.

State: data/wipe_pending.json  {"cats": [...], "due": epoch, "created": epoch, "by": name, "delay_h": 3|24}
Code:  data/wipe_auth.json     {"hash": ...}
After an "interface" wipe the site shows a closed page to everybody except the main admin: data/site_closed.json.
"""
import json
import shutil
import threading
import time
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

import config

PHRASES = ("delete the server", "delete the website", "delete all data", "delete the all data", "delete everything",
           "احذف كل البيانات", "امسح كل البيانات", "احذف الموقع", "امسح الموقع")
DELAYS = (3, 24)
COUNTDOWN = 10
MIN_CODE = 8
_lock = threading.Lock()

# what each choice deletes (paths relative to the project folder; globs allowed)
CATS = {
    "students":  ["data/students.json", "data/bookmarks.json", "data/avatars/s_*", "data/uploads/s_*", "data/*/exams/attempts",
                  "data/atrisk_notified.json", "data/followups.json"],
    "doctors":   ["data/doctors.json", "data/doctor_requests.json", "data/avatars/d_*", "data/uploads/d_*"],
    "content":   ["data/*/lectures", "data/*/passages.csv", "data/*/slides", "data/*/ocr_cache", "data/*/figures.json",
                  "data/*/videos", "data/*/videos.json", "models", "static/reports"],
    "exams":     ["data/*/exams"],
    "chat":      ["data/chat.json", "data/chat_files"],
    "logs":      ["logs.xlsx", "logs.db", "logs.db-wal", "logs.db-shm", "data/audit.jsonl", "data/weekly_sent.json"],
    "notices":   ["data/notifications.json", "data/announcements.json", "data/schedule.json", "data/badges.json",
                  "data/custom_badges.json", "data/support.json", "data/faq.json"],
    "uploads":   ["data/uploads", "data/avatars", "data/chat_files", "data/profiles.json"],
    "interface": [],                                              # closes the site (pages, icons, menus) for everybody
}
ORDER = list(CATS)

PENDING = lambda: config.BASE_DIR / "data" / "wipe_pending.json"
AUTH = lambda: config.BASE_DIR / "data" / "wipe_auth.json"
CLOSED = lambda: config.BASE_DIR / "data" / "site_closed.json"


# ------------------------------------------------------------------ security code
def code_set():
    try:
        return bool(json.loads(AUTH().read_text(encoding="utf-8")).get("hash"))
    except (OSError, ValueError):
        return False


def set_code(code):
    code = (code or "").strip()
    if len(code) < MIN_CODE:
        return "wp_code_short"
    AUTH().parent.mkdir(parents=True, exist_ok=True)
    AUTH().write_text(json.dumps({"hash": generate_password_hash(code)}), encoding="utf-8")
    return ""


def check_code(code):
    try:
        return check_password_hash(json.loads(AUTH().read_text(encoding="utf-8"))["hash"], (code or "").strip())
    except (OSError, ValueError, KeyError):
        return False


def phrase_ok(text):
    return " ".join((text or "").lower().split()) in PHRASES


# ------------------------------------------------------------------ schedule / cancel
def pending():
    try:
        p = json.loads(PENDING().read_text(encoding="utf-8"))
        p["left"] = max(0, int(p["due"] - time.time()))
        p["due_text"] = datetime.fromtimestamp(p["due"]).strftime("%Y-%m-%d %H:%M")
        return p
    except (OSError, ValueError, KeyError):
        return None


def schedule(cats, delay_h, by):
    cats = ["everything"] if "everything" in cats else [c for c in ORDER if c in cats]
    if not cats or delay_h not in DELAYS:
        return None
    rec = {"cats": cats, "created": time.time(), "due": time.time() + delay_h * 3600, "delay_h": delay_h, "by": by}
    with _lock:
        PENDING().parent.mkdir(parents=True, exist_ok=True)
        PENDING().write_text(json.dumps(rec), encoding="utf-8")
    return rec


def cancel():
    with _lock:
        try:
            PENDING().unlink()
            return True
        except OSError:
            return False


# ------------------------------------------------------------------ run
def _targets(cats, base):
    names = ORDER if "everything" in cats else cats
    out = []
    for c in names:
        for pat in CATS.get(c, []):
            out += [p for p in base.glob(pat)]
    return out


def due():
    p = pending()
    return p if p and p["left"] <= 0 else None


def execute(base=None):
    """Delete what was chosen. Only paths inside the project folder are touched. Returns the number of deleted items."""
    base = (base or config.BASE_DIR).resolve()
    with _lock:
        try:
            rec = json.loads(PENDING().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        n = 0
        for p in _targets(rec["cats"], base):
            rp = p.resolve()
            if not str(rp).startswith(str(base)) or rp == base:
                continue
            try:
                if rp.is_dir():
                    shutil.rmtree(rp)
                else:
                    rp.unlink()
                n += 1
            except OSError as e:
                print("wipe: could not delete", rp, e)
        if "everything" in rec["cats"] or "interface" in rec["cats"]:
            CLOSED().parent.mkdir(parents=True, exist_ok=True)
            CLOSED().write_text(json.dumps({"since": datetime.now().strftime("%Y-%m-%d %H:%M")}), encoding="utf-8")
        for f in (PENDING(),) + ((AUTH(),) if "everything" in rec["cats"] else ()):
            try:
                f.unlink()
            except OSError:
                pass
        try:                                                     # the only trace left: when and what
            (base / "data").mkdir(parents=True, exist_ok=True)
            with (base / "data" / "wipe_log.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "cats": rec["cats"], "by": rec.get("by"), "items": n}) + "\n")
        except OSError:
            pass
    return n


def closed():
    return CLOSED().exists()


def reopen():
    try:
        CLOSED().unlink()
    except OSError:
        pass
