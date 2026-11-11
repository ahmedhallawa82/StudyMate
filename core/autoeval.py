"""Automatic evaluation of the slide search for ANY course (no hand-made test set needed).

How it works (hold-out): from every slide with enough text, one sentence is taken out and used as the question; the
search index is built WITHOUT those sentences. A hit = the slide the sentence came from is ranked first (Top-1) or in
the first three (Top-3). The same is done for the four methods (TF-IDF, BM25, Hybrid, LSA), so the numbers change
every time a course is uploaded, rebuilt or retrained. Questions taken from the OTHER courses are used to check that
the "Not found" filter refuses what is not in the slides.
Results: <reports>/auto_metrics.json (latest run + a short history).
"""
import json
import random
import re
from datetime import datetime

import numpy as np
import pandas as pd

import config
from core.search import SearchEngine

METHODS = [("tfidf", "TF-IDF"), ("bm25", "BM25"), ("hybrid", "Hybrid (TF-IDF + semantic)"), ("lsa", "Semantic (LSA)")]
_SENT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text):
    return [s.strip() for s in _SENT.split(str(text).replace("\n", " ")) if s.strip()]


def _holdout(passages, n_queries, seed):
    rng = random.Random(seed)
    rows, queries = [], []
    for _, r in passages.iterrows():
        sents = _sentences(r["text"])
        good = [s for s in sents if 7 <= len(s.split()) <= 30]
        if len(sents) >= 3 and good:
            q = rng.choice(good)
            rest = " ".join(s for s in sents if s != q)
            queries.append((q, r["passage_id"]))
            rows.append({**r.to_dict(), "text": rest})
        else:
            rows.append(r.to_dict())
    rng.shuffle(queries)
    return pd.DataFrame(rows), queries[:n_queries]


def _other_course_questions(code, n=40, seed=0):
    rng = random.Random(seed)
    pool = []
    for c in config.list_courses():
        if c["code"] == code:
            continue
        f = config.course_paths(c["code"]).passages
        if f.exists():
            for t in pd.read_csv(f)["text"].astype(str):
                pool += [s for s in _sentences(t) if 6 <= len(s.split()) <= 20]
    rng.shuffle(pool)
    return pool[:n]


def run(code, n_queries=150, seed=0):
    """Evaluate one course and save the result. Returns the result dict (or None when the course has too little text)."""
    P = config.course_paths(code)
    if not P.passages.exists():
        return None
    passages = pd.read_csv(P.passages).fillna("")
    if "topic_name" not in passages:
        passages["topic_name"] = ""
    train, queries = _holdout(passages, n_queries, seed)
    if len(queries) < 5:
        return None
    eng = SearchEngine(train)
    ids = list(eng.passages["passage_id"])
    res = {}
    for key, name in METHODS:
        t1 = t3 = 0
        rr = []
        for q, pid in queries:
            order = np.argsort(-eng.scores(q, key))
            ranks = [ids[i] for i in order[:50]]
            pos = ranks.index(pid) + 1 if pid in ranks else None
            t1 += pos == 1
            t3 += bool(pos and pos <= 3)
            rr.append(1 / pos if pos else 0)
        n = len(queries)
        res[key] = {"name": name, "top1": round(t1 / n, 3), "top3": round(t3 / n, 3), "mrr": round(float(np.mean(rr)), 3)}
    off = _other_course_questions(code, seed=seed)
    rejected = sum(1 for q in off if not eng.is_in_course(q)[0])
    out = {"course": code, "when": datetime.now().strftime("%Y-%m-%d %H:%M"), "slides": int(len(passages)),
           "lectures": int(passages["lecture"].nunique()), "n_queries": len(queries), "methods": res,
           "offtopic": {"total": len(off), "rejected": rejected}}
    P.reports.mkdir(parents=True, exist_ok=True)
    f = P.reports / "auto_metrics.json"
    hist = []
    if f.exists():
        try:
            hist = json.loads(f.read_text(encoding="utf-8")).get("history", [])
        except (OSError, ValueError):
            hist = []
    hist.append({"when": out["when"], "slides": out["slides"], "tfidf": res["tfidf"]["top1"], "bm25": res["bm25"]["top1"],
                 "hybrid": res["hybrid"]["top1"], "lsa": res["lsa"]["top1"]})
    out["history"] = hist[-20:]
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load(code):
    f = config.course_paths(code).reports / "auto_metrics.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def safe_run(code):
    """run() that never breaks an upload."""
    try:
        return run(code)
    except Exception as e:                                           # noqa: BLE001
        print(f"Auto-evaluation of {code} skipped ({type(e).__name__}: {e})")
        return None
