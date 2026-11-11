"""Videos of a course: recorded lectures uploaded by the doctor (files) and YouTube links shown inside the site.
Stored in data/<course>/videos/ (files) and data/<course>/videos.json (the list)."""
import json
import re
import secrets
import threading
from datetime import datetime

import config

ALLOWED = {".mp4", ".webm", ".ogg", ".m4v", ".mov"}
_lock = threading.Lock()
_YT = re.compile(r"(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/|v/))([A-Za-z0-9_-]{11})")


def folder(code):
    return config.course_paths(code).data / "videos"


def _file(code):
    return config.course_paths(code).data / "videos.json"


def _load(code):
    try:
        d = json.loads(_file(code).read_text(encoding="utf-8"))
        return {"recorded": d.get("recorded", []), "links": d.get("links", [])}
    except (OSError, ValueError):
        return {"recorded": [], "links": []}


def _save(code, d):
    f = _file(code)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def items(code):
    return _load(code)


def youtube_id(url):
    m = _YT.search((url or "").strip())
    return m.group(1) if m else ""


def add_link(code, title, url, lecture="", by=""):
    """True when saved; False when the address is not a YouTube video."""
    vid = youtube_id(url)
    if not vid:
        return False
    with _lock:
        d = _load(code)
        d["links"].append({"id": secrets.token_hex(4), "title": (title or "").strip()[:120] or "YouTube", "yt": vid,
                           "lecture": str(lecture or "").strip()[:6], "by": by, "added": datetime.now().strftime("%Y-%m-%d")})
        _save(code, d)
    return True


def add_recorded(code, title, fileobj, filename, lecture="", by=""):
    """Saves an uploaded video. Returns '' when done, else 'bad_type'."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED:
        return "bad_type"
    fid = secrets.token_hex(6)
    folder(code).mkdir(parents=True, exist_ok=True)
    path = folder(code) / (fid + ext)
    fileobj.save(path)
    with _lock:
        d = _load(code)
        d["recorded"].append({"id": fid, "title": (title or "").strip()[:120] or filename[:60], "file": fid + ext,
                              "lecture": str(lecture or "").strip()[:6], "by": by, "size": path.stat().st_size,
                              "added": datetime.now().strftime("%Y-%m-%d")})
        _save(code, d)
    return ""


def delete(code, kind, vid):
    with _lock:
        d = _load(code)
        key = "recorded" if kind == "recorded" else "links"
        gone = [x for x in d[key] if x["id"] == vid]
        d[key] = [x for x in d[key] if x["id"] != vid]
        _save(code, d)
    for x in gone:
        if kind == "recorded":
            try:
                (folder(code) / x["file"]).unlink()
            except OSError:
                pass
    return bool(gone)


def file_of(code, fid):
    for x in _load(code)["recorded"]:
        if x["id"] == fid:
            return folder(code), x["file"]
    return None, None
