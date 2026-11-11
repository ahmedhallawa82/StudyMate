"""Exams: question banks (Arabic + English, paired by question number), random exams, grading.

data/<COURSE>/exams/bank.json       {"questions": {"12": {...}}, "settings": {...}}
data/<COURSE>/exams/attempts/<id>.json   one file per attempt (answers, score, details)

A question: {"type": "mcq"|"essay", "answer": option index or null,
             "en": {"q", "options", "model", "keywords"}, "ar": {...}}
MCQ is graded by the option INDEX, so it does not matter which language the student used.
Files accepted: PDF, DOCX, TXT, XLSX, CSV. Text format (works for both languages):
    Q1. question text            س1. نص السؤال
    A) option   B) option        أ) خيار   ب) خيار
    Answer: B                    الإجابة: ب          (essay: Answer: model answer text)
    Keywords: a; b; c            الكلمات المفتاحية: ك1؛ ك2
"""
import io
import json
import random
import re
import secrets
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import config

DEFAULTS = {"min_mcq": 1.0, "min_essay": 5.0}
_lock = threading.Lock()
LETTERS_EN = "ABCDEFGH"
LETTERS_AR = ["أ", "ب", "ج", "د", "هـ", "و", "ز", "ح"]
_AR_LETTER_IDX = {"أ": 0, "ا": 0, "ب": 1, "ج": 2, "د": 3, "ه": 4, "هـ": 4, "و": 5, "ز": 6, "ح": 7}


# ------------------------------------------------------------------ storage
def folder(code):
    return config.course_paths(code).data / "exams"


def load_bank(code):
    try:
        b = json.loads((folder(code) / "bank.json").read_text(encoding="utf-8"))
    except Exception:
        b = {}
    b.setdefault("questions", {})
    b["settings"] = {**DEFAULTS, **b.get("settings", {})}
    return b


def save_bank(code, bank):
    with _lock:
        folder(code).mkdir(parents=True, exist_ok=True)
        (folder(code) / "bank.json").write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")


def is_graded(q):
    if q.get("type") == "mcq":
        return q.get("answer") is not None
    return any(q.get(l, {}).get("keywords") or q.get(l, {}).get("model") for l in ("en", "ar"))


def summary(code):
    b = load_bank(code)
    qs = b["questions"].values()
    return {"total": len(b["questions"]), "en": sum("en" in q for q in qs), "ar": sum("ar" in q for q in qs),
            "mcq": sum(q["type"] == "mcq" for q in qs), "essay": sum(q["type"] == "essay" for q in qs),
            "graded": sum(is_graded(q) for q in qs), "settings": b["settings"]}


def clear_bank(code):
    b = load_bank(code)
    save_bank(code, {"questions": {}, "settings": b["settings"]})


def save_settings(code, min_mcq, min_essay):
    b = load_bank(code)
    b["settings"] = {"min_mcq": max(0.2, min(10.0, float(min_mcq))), "min_essay": max(0.5, min(60.0, float(min_essay)))}
    save_bank(code, b)


# ------------------------------------------------------------------ reading files
def clean(text):
    text = re.sub("[‪-‮‎‏⁦-⁩]", "", text)          # bidi marks from PDF
    text = text.replace("األ", "الأ").replace("اإل", "الإ").replace("اآل", "الآ")  # lam-alef artefacts
    return text.replace("\r", "")


def _pdf_texts(data):
    """All text versions we can get from a PDF (the caller keeps the one that parses best)."""
    out = []
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data); f.flush()
        try:
            out.append(subprocess.run(["pdftotext", "-enc", "UTF-8", f.name, "-"], capture_output=True, timeout=120).stdout.decode("utf-8", "ignore"))
        except Exception:
            pass
        try:
            import fitz                                           # PyMuPDF, if installed
            out.append("\n".join(p.get_text() for p in fitz.open(f.name)))
        except Exception:
            pass
        try:
            from pypdf import PdfReader
            out.append("\n".join((p.extract_text() or "") for p in PdfReader(f.name).pages))
        except Exception:
            pass
    return [clean(t) for t in out if t and t.strip()]


def _docx_text(data):
    import docx
    d = docx.Document(io.BytesIO(data))
    return clean("\n".join(p.text for p in d.paragraphs))


def _is_ar(text):
    ar = len(re.findall("[؀-ۿ]", text))
    return ar > 0.3 * max(1, len(re.findall(r"[A-Za-z؀-ۿ]", text)))


# ------------------------------------------------------------------ text -> questions
_Q = re.compile(r"^\s*(?:(?:Q(?:uestion)?|س|السؤال|سؤال)\s*)?(\d{1,4})\s*[.):\-–]\s*(.*)$", re.I)
_QPREFIX = re.compile(r"^\s*(?:Q(?:uestion)?|س|السؤال|سؤال)\s*\d", re.I)
_OPT = re.compile(r"^\s*\(?([A-Ha-hأابجدهوزح]ـ?)\s*[.)\-]\s+(.*)$")
_ANS = re.compile(r"^\s*(?:Answer|Ans|Correct(?: answer)?|الإجابة|الاجابة|الجواب|الإجابة الصحيحة)\s*[:：\-]\s*(.*)$", re.I)
_KW = re.compile(r"^\s*(?:Keywords?|الكلمات المفتاحية|كلمات مفتاحية)\s*[:：]\s*(.*)$", re.I)


def _letter_index(s):
    s = s.strip().strip(".)(").strip()
    if len(s) == 1 and s.upper() in LETTERS_EN:
        return LETTERS_EN.index(s.upper())
    return _AR_LETTER_IDX.get(s)


def parse_text(text):
    """[{n, lang, type, q, options, answer, model, keywords}] from free text in the format above."""
    items, cur, field, last_n = [], None, None, 0

    def close():
        nonlocal cur
        if cur and cur["q"].strip():
            cur["q"] = re.sub(r"\s+", " ", cur["q"]).strip()
            cur["options"] = [re.sub(r"\s+", " ", o).strip() for o in cur["options"]]
            cur["type"] = "mcq" if len(cur["options"]) >= 2 else "essay"
            cur["lang"] = "ar" if _is_ar(cur["q"]) else "en"
            if cur["type"] == "mcq" and cur["answer_raw"]:
                cur["answer"] = _letter_index(cur["answer_raw"].split()[0]) if cur["answer_raw"].split() else None
                if cur["answer"] is not None and cur["answer"] >= len(cur["options"]):
                    cur["answer"] = None
            else:
                cur["model"] = re.sub(r"\s+", " ", cur["answer_raw"]).strip() if cur["type"] == "essay" else ""
            items.append(cur)
        cur = None

    for line in text.split("\n"):
        if not line.strip():
            continue
        m = _Q.match(line)
        if m and (_QPREFIX.match(line) or int(m.group(1)) in (last_n + 1, last_n) or cur is None and last_n == 0):
            close()
            last_n = int(m.group(1))
            cur = {"n": last_n, "q": m.group(2), "options": [], "answer": None, "answer_raw": "", "model": "", "keywords": []}
            field = "q"
            continue
        if cur is None:
            continue
        a, k, o = _ANS.match(line), _KW.match(line), _OPT.match(line)
        if a:
            cur["answer_raw"], field = a.group(1), "answer"
        elif k:
            cur["keywords"] = [x.strip() for x in re.split(r"[;,،؛]", k.group(1)) if x.strip()]
            field = "kw"
        elif o and field in ("q", "opt") and len(cur["options"]) < 8 and _letter_index(o.group(1)) == len(cur["options"]):
            cur["options"].append(o.group(2))
            field = "opt"
        elif field == "q":
            cur["q"] += " " + line.strip()
        elif field == "opt":
            cur["options"][-1] += " " + line.strip()
        elif field == "answer":
            cur["answer_raw"] += " " + line.strip()
        elif field == "kw":
            cur["keywords"] += [x.strip() for x in re.split(r"[;,،؛]", line) if x.strip()]
    close()
    return items


def parse_table(data, filename):
    """XLSX / CSV: columns number, type, question, A, B, C, D, answer, keywords (Arabic headers also work)."""
    import pandas as pd
    df = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig", dtype=str) if filename.lower().endswith(".csv") \
        else pd.read_excel(io.BytesIO(data), dtype=str)
    df = df.fillna("")
    ren = {"رقم": "number", "no": "number", "n": "number", "#": "number", "السؤال": "question", "نوع": "type", "النوع": "type",
           "الإجابة": "answer", "الاجابة": "answer", "الكلمات المفتاحية": "keywords", "أ": "a", "ب": "b", "ج": "c", "د": "d"}
    df.columns = [ren.get(str(c).strip().lower(), str(c).strip().lower()) for c in df.columns]
    items = []
    for i, r in df.iterrows():
        q = clean(str(r.get("question", ""))).strip()
        if not q:
            continue
        try:
            n = int(float(r.get("number") or i + 1))
        except ValueError:
            n = i + 1
        opts = [clean(str(r.get(c, ""))).strip() for c in ("a", "b", "c", "d", "e", "f") if str(r.get(c, "")).strip()]
        ans = str(r.get("answer", "")).strip()
        typ = "mcq" if len(opts) >= 2 else "essay"
        it = {"n": n, "q": q, "options": opts, "type": typ, "lang": "ar" if _is_ar(q) else "en", "answer": None, "model": "",
              "keywords": [x.strip() for x in re.split(r"[;,،؛]", str(r.get("keywords", ""))) if x.strip()]}
        if typ == "mcq":
            idx = _letter_index(ans.split()[0]) if ans.split() else None
            it["answer"] = idx if idx is not None and idx < len(opts) else None
        else:
            it["model"] = clean(ans)
        items.append(it)
    return items


def parse_file(filename, data):
    """-> (items, note). Tries every extractor and keeps the one that finds the most questions."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls", ".csv")):
        return parse_table(data, name), ""
    if name.endswith(".docx"):
        texts = [_docx_text(data)]
    elif name.endswith(".txt"):
        texts = [clean(data.decode("utf-8-sig", "ignore"))]
    elif name.endswith(".pdf"):
        texts = _pdf_texts(data)
    else:
        return [], "unsupported"
    best = max((parse_text(t) for t in texts), key=len, default=[])
    return best, ""


def template_xlsx():
    import pandas as pd
    rows = [
        {"number": 1, "type": "mcq", "question": "What does PEAS stand for?", "A": "Performance, Environment, Actuators, Sensors",
         "B": "Planning, Execution, Analysis, Search", "C": "Policy, Energy, Action, State", "D": "None of these", "answer": "A", "keywords": ""},
        {"number": 1, "type": "mcq", "question": "ماذا تعني PEAS؟", "A": "الأداء والبيئة والمشغلات والحساسات",
         "B": "التخطيط والتنفيذ والتحليل والبحث", "C": "السياسة والطاقة والفعل والحالة", "D": "لا شيء مما سبق", "answer": "أ", "keywords": ""},
        {"number": 2, "type": "essay", "question": "Explain the A* algorithm.", "A": "", "B": "", "C": "", "D": "",
         "answer": "A* uses f(n)=g(n)+h(n) with an admissible heuristic.", "keywords": "f(n); g(n); h(n); admissible"},
    ]
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


# ------------------------------------------------------------------ bank update
def add_items(code, items, with_answers):
    """Merge parsed questions into the bank (same number + same language = replaced). Returns counts."""
    bank = load_bank(code)
    qs, added, upd = bank["questions"], 0, 0
    for it in items:
        key = str(it["n"])
        e = qs.get(key)
        if e is None:
            e = qs[key] = {"type": it["type"], "answer": None}
            added += 1
        else:
            upd += 1
        if it["type"] == "mcq":
            e["type"] = "mcq"
        e[it["lang"]] = {"q": it["q"], "options": it["options"] if it["type"] == "mcq" else [],
                         **({"model": it["model"], "keywords": it["keywords"]} if with_answers else
                            {k: e.get(it["lang"], {}).get(k, v) for k, v in (("model", ""), ("keywords", []))})}
        if with_answers and it["type"] == "mcq" and it["answer"] is not None:
            e["answer"] = it["answer"]
    save_bank(code, bank)
    return {"added": added, "updated": upd}


# ------------------------------------------------------------------ taking an exam
def _pick_lang(q, lang):
    other = "en" if lang == "ar" else "ar"
    return q.get(lang) or q.get(other) or {"q": "", "options": []}, (lang if q.get(lang) else other)


def _seconds(q, settings):
    return int(round(60 * (settings["min_mcq"] if q["type"] == "mcq" else settings["min_essay"])))


def eligible(code):
    b = load_bank(code)
    return {k: q for k, q in b["questions"].items() if is_graded(q) and (q.get("en") or q.get("ar"))}


def count_choices(n):
    base = [c for c in (10, 20, 30, 40, 50, 100, 200) if c < n]
    return base + [n] if n else []


def avg_minutes(code):
    b = load_bank(code)
    qs = list(eligible(code).values())
    if not qs:
        return 1.0
    return sum(_seconds(q, b["settings"]) for q in qs) / len(qs) / 60


def new_attempt(code, student, lang, count):
    b = load_bank(code)
    pool = eligible(code)
    count = max(1, min(int(count), len(pool)))
    keys = random.sample(sorted(pool), count)
    secs = sum(_seconds(pool[k], b["settings"]) for k in keys)
    now = time.time()
    att = {"id": secrets.token_hex(6), "course": code, "student": student, "lang": lang, "qids": keys, "answers": {},
           "started": now, "deadline": now + secs, "seconds": secs, "status": "active"}
    save_attempt(att)
    return att


def _attempt_path(code, aid):
    return folder(code) / "attempts" / f"{re.sub('[^a-f0-9]', '', aid)}.json"


def save_attempt(att):
    p = _attempt_path(att["course"], att["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(att, ensure_ascii=False), encoding="utf-8")


def load_attempt(code, aid):
    try:
        return json.loads(_attempt_path(code, aid).read_text(encoding="utf-8"))
    except Exception:
        return None


def list_attempts(code, student=None):
    out = []
    for f in (folder(code) / "attempts").glob("*.json") if (folder(code) / "attempts").exists() else []:
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if student is None or a["student"] == student:
            out.append(a)
    return sorted(out, key=lambda a: a["started"], reverse=True)


def active_attempt(code, student):
    for a in list_attempts(code, student):
        if a["status"] == "active":
            if time.time() > a["deadline"] + 120:          # left open for good: grade what was saved
                finish(a, {})
                continue
            return a
    return None


def view_questions(att):
    """The questions of an attempt for the page, WITHOUT the answers."""
    bank = load_bank(att["course"])["questions"]
    out = []
    for i, k in enumerate(att["qids"], 1):
        q = bank.get(k)
        if not q:
            continue
        side, lang_used = _pick_lang(q, att["lang"])
        out.append({"i": i, "id": k, "type": q["type"], "q": side["q"], "options": side.get("options", []),
                    "lang": lang_used, "value": att["answers"].get(k, "")})
    return out


def _grade_essay(text, side, other):
    text = (text or "").strip().lower()
    if not text:
        return 0.0, []
    kws = side.get("keywords") or other.get("keywords") or []
    if kws:
        hit = [k for k in kws if k.lower() in text or all(w in text for w in k.lower().split())]
        ratio = len(hit) / len(kws)
    else:
        model = (side.get("model") or other.get("model") or "").lower()
        mw = {w for w in re.findall(r"\w{3,}", model)}
        tw = set(re.findall(r"\w{3,}", text))
        ratio, hit = (len(mw & tw) / len(mw) if mw else 0.0), []
    return (1.0 if ratio >= 0.7 else 0.5 if ratio >= 0.4 else 0.0), hit


def finish(att, form_answers):
    """Grade the attempt and store the result. form_answers = answers sent with the submit (may be empty)."""
    if att["status"] != "active":
        return att
    att["answers"].update({k: v for k, v in form_answers.items() if k in att["qids"]})
    bank = load_bank(att["course"])["questions"]
    details, total = [], 0.0
    for i, k in enumerate(att["qids"], 1):
        q = bank.get(k)
        if not q:
            continue
        side, lang_used = _pick_lang(q, att["lang"])
        other = q.get("en" if lang_used == "ar" else "ar", {})
        given = att["answers"].get(k, "")
        d = {"i": i, "id": k, "type": q["type"], "q": side["q"], "options": side.get("options", []), "given": given}
        if q["type"] == "mcq":
            try:
                g = int(given)
            except (TypeError, ValueError):
                g = None
            d.update(correct_idx=q.get("answer"), given_idx=g, score=1.0 if g is not None and g == q.get("answer") else 0.0)
        else:
            sc, hit = _grade_essay(given, side, other)
            d.update(score=sc, hit=hit, keywords=side.get("keywords") or other.get("keywords") or [],
                     model=side.get("model") or other.get("model") or "")
        total += d["score"]
        details.append(d)
    n = len(details)
    att.update(status="done", details=details, finished=time.time(), score=total, max=n,
               pct=round(100 * total / n) if n else 0,
               duration=int(min(time.time(), att["deadline"] + 60) - att["started"]))
    save_attempt(att)
    return att


def override(att, qid, score):
    """Doctor changes the mark of one question (0, 0.5 or 1)."""
    for d in att.get("details", []):
        if d["id"] == qid and d["type"] == "essay":
            d["score"] = score
            d["overridden"] = True
    att["score"] = sum(d["score"] for d in att["details"])
    att["pct"] = round(100 * att["score"] / att["max"]) if att["max"] else 0
    save_attempt(att)
