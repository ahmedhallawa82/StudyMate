"""Read the TEXT INSIDE the pictures of a slide (diagram labels, table screenshots, captions) with OCR.

The normal extraction (pypdf) only sees real text, so a slide whose content is a pasted picture was invisible to the
search. This module extracts the pictures embedded in each page, throws away logos / icons / repeated pictures, reads
the rest with Tesseract and keeps only confident words. The result is added to the slide text when the index is built.

Two ways to get the figure text (both end in data/<course>/figures.json, {"L01S05": "text read from the pictures"}):
  1. the server runs Tesseract itself (cached, so it runs once per lecture file), or
  2. the doctor runs notebooks/StudyMate_Image_Recognition.ipynb on Google Colab and imports its figure_text.json on the
     "AI models" page (useful when the hosting has no Tesseract).
Formulas are NOT understood by OCR; only their words (names, labels) are kept.
"""
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

MIN_SIDE = 60            # pixels: smaller pictures are icons / bullets
MIN_AREA = 12000
MIN_CONF = 60            # Tesseract confidence (0-100) a word needs to be kept
MIN_WORDS = 3            # a picture that gives fewer words is noise
_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def available():
    return bool(shutil.which("tesseract"))


def _ocr_words(img):
    """Confident words of one PIL image (empty list when Tesseract is missing)."""
    if not available():
        return []
    from PIL import Image
    img = img.convert("RGB")
    if img.width < 700:                                           # small pictures read much better when enlarged
        k = 2 if img.width >= 350 else 3
        img = img.resize((img.width * k, img.height * k), Image.LANCZOS)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "f.png"
        img.save(p)
        out = subprocess.run(["tesseract", str(p), "stdout", "-l", "eng", "--psm", "11", "tsv"],
                             check=False, capture_output=True, timeout=120)
    words = []
    for line in out.stdout.decode("utf-8", errors="ignore").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        w = parts[11].strip()
        if conf >= MIN_CONF and _WORD.fullmatch(w.strip(".,;:()[]")):
            words.append(w.strip(".,;:()[]"))
    return words


def pdf_figure_text(pdf, cache_dir=None):
    """{page_number: text} for the pictures of one PDF. Cached next to the course data."""
    pdf = Path(pdf)
    cache = Path(cache_dir) / f"{pdf.stem}__figures.json" if cache_dir else None
    key = f"{pdf.stat().st_size}"
    if cache and cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("key") == key:
                return {int(k): v for k, v in d["pages"].items()}
        except (OSError, ValueError):
            pass
    if not available():
        return {}
    from pypdf import PdfReader
    reader = PdfReader(str(pdf))
    found, count = [], Counter()
    for no, page in enumerate(reader.pages, start=1):
        try:
            images = list(page.images)
        except Exception:                                         # noqa: BLE001 - damaged picture objects are skipped
            continue
        for im in images:
            try:
                pil = im.image
            except Exception:                                     # noqa: BLE001
                continue
            if min(pil.size) < MIN_SIDE or pil.size[0] * pil.size[1] < MIN_AREA:
                continue
            h = hashlib.md5(im.data).hexdigest()
            count[h] += 1
            found.append((no, h, pil))
    pages = {}
    for no, h, pil in found:
        if count[h] > 2:                                          # the same picture on many slides = logo / template
            continue
        words = _ocr_words(pil)
        if len(words) >= MIN_WORDS:
            pages[no] = (pages.get(no, "") + " " + " ".join(words)).strip()
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"key": key, "pages": pages}, ensure_ascii=False), encoding="utf-8")
    return pages


def imported_file(course_dir):
    return Path(course_dir) / "figures.json"


def imported(course_dir):
    """Figure text imported from Colab: {passage_id: text}."""
    try:
        d = json.loads(imported_file(course_dir).read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in d.items()}
    except (OSError, ValueError, AttributeError):
        return {}


def save_imported(course_dir, mapping):
    clean = {str(k): re.sub(r"\s+", " ", str(v)).strip() for k, v in mapping.items() if re.fullmatch(r"L\d{2,3}S\d{2,3}", str(k)) and str(v).strip()}
    imported_file(course_dir).write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(clean)
