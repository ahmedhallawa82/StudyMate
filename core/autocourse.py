"""Build a whole new course from lecture PDFs (used by Admin -> Add a new course).

Creates: data/<CODE>/ (lectures, passages, topics = one per lecture, question bank of fill-in-the-blank
questions made from the slides), a topic classifier trained on the slide texts, and the search index.
A course with a hand-made question bank and labelled questions can replace these files later.
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.pipeline import Pipeline

import config
from core.classifier import make_pipeline, TopicClassifier
from core.passages import build_passages, lecture_number, lecture_title
from core.search import build_index, STOP
from core.text import normalize_question

_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{5,}")


def clean_code(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", code or "").upper()[:10]


def _cloze(passages: pd.DataFrame, code: str, per_topic: int = 6) -> pd.DataFrame:
    """Fill-in-the-blank questions: blank the rarest long word of a good sentence of each slide."""
    docs = [set(w.lower() for w in _WORD.findall(t)) for t in passages.text]
    df = Counter(w for d in docs for w in d)
    n = len(docs)
    rows = []
    for topic, g in passages.groupby("topic", sort=False):
        cands = []
        for _, r in g.iterrows():
            for line in re.split(r"[\n•▪·]|(?<=[.!?])\s+", r.text):
                line = line.strip(" -–:;,")
                words = line.split()
                if not (6 <= len(words) <= 32) or not (35 <= len(line) <= 230):
                    continue
                terms = [w for w in _WORD.findall(line) if w.lower() not in STOP]
                if not terms:
                    continue
                term = max(terms, key=lambda w: (math.log(n / (1 + df[w.lower()])), len(w)))
                cands.append((r.lecture, r.slide, line, term))
        step = max(1, len(cands) // per_topic)
        for lec, slide, line, term in cands[::step][:per_topic]:
            blank = re.sub(rf"\b{re.escape(term)}\b", "_____", line, count=1)
            half = term[0] + "".join(c if i % 2 == 1 else "_" for i, c in enumerate(term[1:], 1))
            rows.append({"topic": topic, "question": "Fill in the blank: " + blank,
                         "hint1": f"It starts with “{term[0]}” and has {len(term)} letters.",
                         "hint2": f"The word looks like: {half}",
                         "answer": line, "keywords": term.lower(), "lecture": lec, "slide": slide})
    out = pd.DataFrame(rows)
    out.insert(0, "q_id", [f"{code}-Q{i:03d}" for i in range(1, len(out) + 1)])
    return out


def regenerate(code: str):
    """(Re)build everything of an automatic course from the PDFs in data/<CODE>/lectures."""
    P = config.course_paths(code)
    nums = sorted({lecture_number(f.name) for f in P.lectures.glob("*.pdf") if lecture_number(f.name)})
    if not nums:
        raise RuntimeError("no lectures")
    pd.DataFrame({"lecture": nums, "slide_from": 1, "slide_to": 9999,
                  "topic": [f"lec{n}" for n in nums]}).to_csv(P.topic_map, index=False)
    passages = build_passages(course=code, verbose=False)
    if passages.empty:
        raise RuntimeError("empty")
    nums = sorted(passages.lecture.unique())
    titles = passages.drop_duplicates("lecture").set_index("lecture")["lecture_title"].to_dict()
    topics = pd.DataFrame({
        "topic": [f"lec{n}" for n in nums],
        "name": [f"L{n}: {titles.get(n, 'Lecture')}" for n in nums],
        "name_ar": [f"م{n}: {titles.get(n, 'محاضرة')}" for n in nums],
        "prerequisites": [""] + [f"lec{n}" for n in nums[:-1]],
        "why": [f"lecture {n} of the course" for n in nums]})
    topics.to_csv(P.topics, index=False, encoding="utf-8")
    bank = _cloze(passages, code)
    bank.to_csv(P.bank, index=False, encoding="utf-8-sig")
    # topic classifier trained on slide texts + the generated questions
    train = pd.concat([passages.rename(columns={"text": "question"})[["question", "topic"]],
                       bank[["question", "topic"]]], ignore_index=True)
    if train.topic.nunique() >= 2:
        pipe = make_pipeline("logreg").fit(train.question, train.topic)
    else:
        pipe = Pipeline([("features", make_pipeline("logreg").named_steps["features"]),
                         ("model", DummyClassifier(strategy="prior"))]).fit(train.question, train.topic)
    TopicClassifier(pipe, "logreg").save(best=True, course=code)
    build_index(passages, dict(zip(topics.topic, topics.name)), course=code)
    return {"slides": len(passages), "lectures": len(nums), "questions": len(bank), "code": code}


def save_lecture(code: str, fname: str, blob: bytes, number=None, title=None):
    """Store one PDF as 'lecture <n> <title>.pdf' (a lecture with the same number is replaced)."""
    P = config.course_paths(code)
    P.lectures.mkdir(parents=True, exist_ok=True)
    taken = {lecture_number(f.name) for f in P.lectures.glob("*.pdf")}
    num = number or lecture_number(fname)
    if not num:
        num = next(k for k in range(1, 999) if k not in taken)
    for old in P.lectures.glob(f"lecture {num} *.pdf"):
        old.unlink()
    title = re.sub(r"[^A-Za-z0-9 ]", " ", title or lecture_title(fname)).strip() or f"Lecture {num}"
    (P.lectures / f"lecture {num} {title}.pdf").write_bytes(blob)
    return num


def build_course(code: str, name_en: str, name_ar: str, files):
    """files: list of (filename, bytes). Raises ValueError (bad input) / FileExistsError / RuntimeError."""
    code = clean_code(code)
    if len(code) < 2 or not files:
        raise ValueError("bad")
    P = config.course_paths(code)
    if P.data.exists():
        raise FileExistsError(code)
    P.lectures.mkdir(parents=True)
    try:
        used = set()
        for fname, blob in files:
            num = lecture_number(fname)
            if num is None or num in used:
                num = next(k for k in range(1, 999) if k not in used)
            used.add(num)
            save_lecture(code, fname, blob, number=num)
        report = regenerate(code)
        P.info.write_text(json.dumps({"name_en": name_en or code, "name_ar": name_ar or name_en or code,
                                      "full": False}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        import shutil
        shutil.rmtree(P.data, ignore_errors=True)
        shutil.rmtree(P.models, ignore_errors=True)
        raise
    return report
