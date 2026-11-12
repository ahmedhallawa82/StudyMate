"""Ask with a photo: read the question written in a picture (OCR) so the normal search and topic classifier can use it.

The trained models work on TEXT, so the picture is first turned into text with Tesseract (the same program used for the
picture-only slides in core/figures.py). Works well for screenshots, typed or printed questions and slide photos;
handwriting, formulas and drawings without words are not understood. When Tesseract is not installed on the server,
available() is False and the photo button is hidden.
"""
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_CHARS = 400
_LANGS = None


def available():
    return bool(shutil.which("tesseract"))


def _langs():
    global _LANGS
    if _LANGS is None:
        try:
            out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=15).stdout.split()
        except Exception:                                            # noqa: BLE001
            out = []
        _LANGS = "+".join([l for l in ("eng", "ara") if l in out]) or "eng"
    return _LANGS


def _prepare(data):
    """Grey, upright, large enough, high contrast: what Tesseract reads best."""
    from PIL import Image, ImageOps
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im).convert("L")                    # phone photos carry their rotation in EXIF
    w, h = im.size
    if max(w, h) < 1400:                                              # small screenshots: enlarge
        f = 1400 / max(w, h)
        im = im.resize((int(w * f), int(h * f)), Image.LANCZOS)
    elif max(w, h) > 3000:                                            # huge photos: shrink (speed)
        im.thumbnail((3000, 3000))
    im = ImageOps.autocontrast(im, cutoff=1)
    return im


_HEADER = re.compile(r"\b(sheet|exam|revision|assignment|page|chapter|section|quiz|lecture\s*\d+|lec\s*\d+|week\s*\d+)\b", re.I)
_NUMBER = re.compile(r"^\(?\s*(?:q(?:uestion)?|s)?\s*\d{1,2}\s*[\).:\-]\s*", re.I)
_AR = re.compile(r"[\u0600-\u06FF]")
_LAT = re.compile(r"[A-Za-z]")


def clean(text):
    """Keep the question: drop noise lines, sheet headers ("Exam revision sheet - Lecture 3") and numbering ("Q3)", "2.")."""
    text = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", text)          # direction marks added by OCR
    lines = []
    for ln in text.splitlines():
        ln = re.sub(r"[|_~=<>{}\[\]\\]+", " ", ln)
        ln = re.sub(r"\s+", " ", ln).strip(" -\u2022*\u00b7")
        if len(_LAT.findall(ln)) + len(_AR.findall(ln)) >= 2:          # drop lines that are only symbols / noise
            lines.append(_NUMBER.sub("", ln))
    if len(lines) > 1:
        body = [l for l in lines if not (_HEADER.search(l) and "?" not in l and len(l.split()) <= 7)]
        lines = body or lines
    out = " ".join(lines)
    lat, ar = len(_LAT.findall(out)), len(_AR.findall(out))
    if lat > 3 * ar:                                                     # an English picture: Arabic bits are OCR noise
        out = " ".join(w for w in out.split() if not _AR.search(w))
    return re.sub(r"\s+", " ", out).strip()[:MAX_CHARS]


def read(data):
    """Text read from the picture ('' when nothing readable). Raises ValueError for a file that is not a picture."""
    if not data or len(data) > MAX_BYTES:
        raise ValueError("size")
    try:
        im = _prepare(data)
    except Exception as e:                                           # noqa: BLE001 - not an image
        raise ValueError("image") from e
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "q.png"
        im.save(p)
        out = subprocess.run(["tesseract", str(p), "stdout", "-l", _langs(), "--psm", "6"],
                             capture_output=True, text=True, timeout=60)
        if out.returncode != 0:                                       # older Tesseract (3.x) spells the option differently
            out = subprocess.run(["tesseract", str(p), "stdout", "-l", _langs()], capture_output=True, text=True, timeout=60)
    return clean(out.stdout)
