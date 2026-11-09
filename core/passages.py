"""Turn lecture PDFs into passages (about one passage per slide) with pypdf."""
import re
import pandas as pd
from pypdf import PdfReader

import config
from core.text import clean_slide_text, is_useful


def lecture_number(filename: str):
    m = re.search(r"lecture\s*[_-]?\s*(\d+)", filename, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def lecture_title(filename: str) -> str:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    stem = re.sub(r"lecture\s*[_-]?\s*\d+", "", stem, flags=re.IGNORECASE)
    return stem.strip(" _-").title() or "Lecture"


def load_topic_map():
    if not config.TOPIC_MAP_CSV.exists():
        return pd.DataFrame(columns=["lecture", "slide_from", "slide_to", "topic"])
    return pd.read_csv(config.TOPIC_MAP_CSV)


def topic_for(topic_map, lecture, slide):
    rows = topic_map[(topic_map.lecture == lecture) & (topic_map.slide_from <= slide) & (topic_map.slide_to >= slide)]
    return rows.iloc[0]["topic"] if len(rows) else None


def build_passages(predict_topic=None, verbose=True) -> pd.DataFrame:
    """Read every PDF in data/AI/lectures and write passages.csv.

    predict_topic: optional function(text) -> topic, used for slides of a NEW lecture
    that is not listed in topic_map.csv (e.g. a PDF uploaded from the Admin page).
    """
    topic_map = load_topic_map()
    rows, dropped = [], 0
    pdfs = sorted(config.LECTURES_DIR.glob("*.pdf"), key=lambda p: (lecture_number(p.name) or 999, p.name))
    for pdf in pdfs:
        lec = lecture_number(pdf.name)
        if lec is None:
            if verbose:
                print(f"  skipped {pdf.name}: file name must contain 'lecture <number>'")
            continue
        reader = PdfReader(str(pdf))
        for i, page in enumerate(reader.pages, start=1):
            text = clean_slide_text(page.extract_text() or "")
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
                "course": config.COURSE_CODE,
                "lecture": lec,
                "lecture_title": lecture_title(pdf.name),
                "slide": i,
                "text": text,
                "topic": topic,
                "topic_source": source,
            })
    df = pd.DataFrame(rows)
    df.to_csv(config.PASSAGES_CSV, index=False, encoding="utf-8-sig")
    if verbose:
        print(f"  {len(df)} passages from {len(pdfs)} PDFs ({dropped} empty/picture-only slides dropped)")
    return df
