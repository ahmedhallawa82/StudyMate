"""Profile photos (and the admin's display name / e-mail, which no other file stores).

data/avatars/<key>.jpg      key = "s_<student code>" or "d_<doctor id>"  (never goes to GitHub)
data/profiles.json          {"d_master": {"name", "email"}}
"""
import json
import re
import threading

import config

DIR = lambda: config.BASE_DIR / "data" / "avatars"
FILE = lambda: config.BASE_DIR / "data" / "profiles.json"
_lock = threading.Lock()
MAX_BYTES = 4 * 1024 * 1024


def safe(key):
    return re.sub(r"[^A-Za-z0-9_-]", "", (key or "").replace(":", "_"))[:60]


def avatar_path(key):
    p = DIR() / f"{safe(key)}.jpg"
    return p if p.exists() else None


def save_avatar(key, fileobj):
    """Square 256x256 JPEG. Returns '' when done, else an error key."""
    from PIL import Image, UnidentifiedImageError
    data = fileobj.read(MAX_BYTES + 1)
    if not data:
        return "photo_missing"
    if len(data) > MAX_BYTES:
        return "photo_big"
    try:
        import io
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return "photo_bad"
    im = im.convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((256, 256))
    DIR().mkdir(parents=True, exist_ok=True)
    im.save(DIR() / f"{safe(key)}.jpg", "JPEG", quality=88)
    return ""


def remove_avatar(key):
    p = avatar_path(key)
    if p:
        p.unlink()


def _load():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(key):
    return _load().get(safe(key), {})


def update(key, **fields):
    with _lock:
        d = _load()
        d.setdefault(safe(key), {}).update({k: v for k, v in fields.items() if v is not None})
        FILE().parent.mkdir(parents=True, exist_ok=True)
        FILE().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
