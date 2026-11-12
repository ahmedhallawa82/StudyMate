"""Turn lecture PDFs into passages (about one passage per slide) with pypdf."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

import config
from core import figures
from core.text import clean_slide_text, is_useful


FIGURE_IF_SHORTER = 150          # characters: figure text only completes slides whose own text is short
LECTURE_RE = r"(?:lecture|week)\s*[_-]?\s*(\d+)"        # "lecture 3 ..." or "... week 3.pdf"


def ocr_page(pdf: Path, page_no: int, cache_dir: Path) -> str:
    """Text of a picture-only slide, read with Tesseract OCR (needs the tesseract and pdftoppm programs).

    The result is cached in data/<course>/ocr_cache, so the OCR runs once (the online server can then skip it).
    """
    cache = cache_dir / f"{pdf.stem}__p{page_no:03d}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    if not (shutil.which("tesseract") and shutil.which("pdftoppm")):
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "pg"
        subprocess.run(["pdftoppm", "-r", "170", "-f", str(page_no), "-l", str(page_no), "-png", str(pdf), str(base)],
                       check=False, capture_output=True, timeout=120)
        imgs = sorted(Path(tmp).glob("pg*.png"))
        if not imgs:
            return ""
        out = subprocess.run(["tesseract", str(imgs[0]), "stdout", "-l", "eng", "--psm", "6"],
                             check=False, capture_output=True, timeout=120)
    text = out.stdout.decode("utf-8", errors="ignore")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def lecture_number(filename: str):
    m = re.search(LECTURE_RE, filename, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def lecture_title(filename: str) -> str:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    stem = re.sub(LECTURE_RE, "", stem, flags=re.IGNORECASE)
    return stem.strip(" _-").title() or "Lecture"


def load_topic_map(course=None):
    path = config.course_paths(course).topic_map
    if not path.exists():
        return pd.DataFrame(columns=["lecture", "slide_from", "slide_to", "topic"])
    return pd.read_csv(path)


def topic_for(topic_map, lecture, slide):
    rows = topic_map[(topic_map.lecture == lecture) & (topic_map.slide_from <= slide) & (topic_map.slide_to >= slide)]
    return rows.iloc[0]["topic"] if len(rows) else None


def build_passages(predict_topic=None, verbose=True, course=None) -> pd.DataFrame:
    """Read every PDF in data/AI/lectures and write passages.csv.

    predict_topic: optional function(text) -> topic, used for slides of a NEW lecture
    that is not listed in topic_map.csv (e.g. a PDF uploaded from the Admin page).
    """
    P = config.course_paths(course)
    topic_map = load_topic_map(course)
    rows, dropped = [], 0
    from_colab = figures.imported(P.data)                   # figure text made on Google Colab (id -> text)
    pdfs = sorted(P.lectures.glob("*.pdf"), key=lambda p: (lecture_number(p.name) or 999, p.name))
    for pdf in pdfs:
        lec = lecture_number(pdf.name)
        if lec is None:
            if verbose:
                print(f"  skipped {pdf.name}: file name must contain 'lecture <number>' or 'week <number>'")
            continue
        reader = PdfReader(str(pdf))
        try:
            pics = figures.pdf_figure_text(pdf, P.data / "ocr_cache")     # text inside pictures (cached, {} without Tesseract)
        except Exception:                                    # noqa: BLE001 - never break an upload because of a picture
            pics = {}
        for i, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            if len(raw.strip()) < 40:                       # picture-only slide -> read it with OCR
                raw = ocr_page(pdf, i, P.data / "ocr_cache") or raw
            extra = from_colab.get(f"L{lec:02d}S{i:02d}") or pics.get(i, "")
            if extra and len(raw.strip()) < FIGURE_IF_SHORTER:      # only slides that say (almost) nothing in real text
                raw = raw + "\n" + extra
            text = clean_slide_text(raw)
            if not is_useful(text):
                dropped += 1
                continue
            topic = topic_for(topic_map, lec, i)
            source = "topic_map"
            if topic is None:
                topic = predict_topic(text) if predict_topic else "unassigned"
                source = "predicted" if predict_topic else "none"
            rows.append({
                "passage_id": f"L{lec:02d}S{i:02d}",
                "course": P.code,
                "lecture": lec,
                "lecture_title": lecture_title(pdf.name),
                "slide": i,
                "text": text,
                "topic": topic,
                "topic_source": source,
            })
    df = pd.DataFrame(rows)
    df.to_csv(P.passages, index=False, encoding="utf-8-sig")
    if verbose:
        print(f"  {len(df)} passages from {len(pdfs)} PDFs ({dropped} empty/picture-only slides dropped)")
    return df
