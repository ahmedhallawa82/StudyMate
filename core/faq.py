"""Help / Questions page: extra questions and answers the admin or a doctor adds (data/faq.json).
The first question (what the search methods do) is built into the page itself."""
import json
import secrets
import threading

import config

FILE = lambda: config.BASE_DIR / "data" / "faq.json"
_lock = threading.Lock()


def _load():
    try:
        rows = json.loads(FILE().read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _save(rows):
    f = FILE()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def items(lang="en"):
    """[{id, q, a}] in the page language, falling back to the other language when one is empty."""
    out = []
    for r in _load():
        q = (r.get("q_ar") if lang == "ar" else r.get("q_en")) or r.get("q_en") or r.get("q_ar") or ""
        a = (r.get("a_ar") if lang == "ar" else r.get("a_en")) or r.get("a_en") or r.get("a_ar") or ""
        if q and a:
            out.append({"id": r["id"], "q": q, "a": a})
    return out


def add(q_en="", a_en="", q_ar="", a_ar=""):
    """True when saved (needs a question and an answer in at least one language)."""
    q_en, a_en, q_ar, a_ar = (x.strip()[:1500] for x in (q_en, a_en, q_ar, a_ar))
    if not ((q_en and a_en) or (q_ar and a_ar)):
        return False
    with _lock:
        rows = _load()
        rows.append({"id": secrets.token_hex(4), "q_en": q_en, "a_en": a_en, "q_ar": q_ar, "a_ar": a_ar})
        _save(rows)
    return True


def delete(fid):
    with _lock:
        rows = _load()
        keep = [r for r in rows if r.get("id") != fid]
        _save(keep)
        return len(keep) != len(rows)
