"""Study Studio: study tools built from the lecture slides only (no language model, no internet).

Everything here is extractive: sentences, terms and definitions are taken from the slides themselves,
so the answer always points back to a slide. Tools: summary + info cards, glossary table, flashcards,
quick quiz, concept map, one-page infographic, revision slides and a read-aloud script.
"""
import math
import random
import re
from collections import Counter, defaultdict

import pandas as pd

import config
from core.search import STOP

MIN_WORDS, MAX_WORDS = 8, 45
BAD_START = {"example", "examples", "note", "notes", "the", "this", "that", "these", "those", "it", "there", "here", "figure", "fig",
             "for", "if", "when", "then", "so", "thus", "we", "you", "i", "our", "your", "what", "why", "how", "agenda", "slide", "chapter",
             "and", "but", "or", "in", "on", "at", "with", "as", "a", "an", "each", "every", "all", "some", "any", "can", "will", "assume",
             "assumptions", "problem", "solution", "goal", "where", "which", "who", "also", "now", "next", "first", "second", "third"}
GOOD_SHORT = {"goal", "problem"}                       # allowed as a term only when followed by a colon definition (see _terms)
WORD = re.compile(r"[A-Za-z][A-Za-z\-\*']+")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")
_UNUSED = [
    re.compile(r"(?P<t>[A-Z][A-Za-z0-9\-\*/ ]{1,45}?)\s+(?:is|are)\s+(?:defined as|called|known as|referred to as)\s+(?P<d>[^.;]{12,220})", re.S),
    re.compile(r"(?P<t>[A-Z][A-Za-z0-9\-\*/ ]{1,45}?)\s+(?:means|refers to|stands for|denotes)\s+(?P<d>[^.;]{12,220})", re.S),
    re.compile(r"(?P<t>[A-Z][A-Za-z0-9\-\*/ ]{1,45}?)\s+(?:is|are)\s+(?:an?|the)\s+(?P<d>[^.;]{16,220})", re.S),
    re.compile(r"(?P<t>[A-Z][A-Za-z0-9\-\*/ ]{1,35}?)\s*:\s+(?P<d>[A-Za-z][^.;:]{16,220})", re.S),
]


GENERIC = set("""second output aka list types type yes true false value values case cases node nodes state states step steps same each other another
many much more most less least only also well make makes made used uses using given take takes taken result results number numbers
level levels example examples following follows consider considered called define defined defines general generally often usually them they details return returns insert empty generated finished
consistent still update continue next reason more here there then thus given want like need needs""".split())


def _strip_titles(text, neighbours):
    """Slide texts start with the slide title (shared with the next or previous slide): cut it off."""
    ws = text.split()
    for _ in range(2):
        while ws and re.fullmatch(r"\d{1,2}", ws[0]):
            ws = ws[1:]
        best = 0
        for other in neighbours:
            ow = other.split()
            k = 0
            while k < min(len(ws), len(ow), 8) and ws[k].lower() == ow[k].lower():
                k += 1
            best = max(best, k)
        if best >= 2 and len(ws) - best >= 5:
            ws = ws[best:]
        else:
            break
    return " ".join(ws)


def prepare(passages):
    """Add a 'body' column: the slide text without its repeated title."""
    out = passages.copy().sort_values(["lecture", "slide"]).reset_index(drop=True)
    bodies = []
    for i, r in out.iterrows():
        nb = [out.at[j, "text"] for j in (i - 1, i + 1) if 0 <= j < len(out) and out.at[j, "lecture"] == r["lecture"]]
        bodies.append(_strip_titles(str(r["text"]), nb))
    out["body"] = bodies
    return out


def _words(text):
    return [w.lower() for w in WORD.findall(text)]


def _content(text):
    return [w for w in _words(text) if w not in STOP and len(w) > 2]


def _sentences(text):
    out = []
    for s in SENT_SPLIT.split(text):
        s = re.sub(r"\s+", " ", s).strip(" -•")
        n = len(s.split())
        if MIN_WORDS <= n <= MAX_WORDS and s[:1].isupper() and not _codey(s):
            out.append(s)
    return out


def _codey(s):
    """Pseudo-code, formulas and tables are not good study sentences."""
    sym = sum(s.count(c) for c in "=<>[]{}()_:|\\")
    digits = sum(ch.isdigit() for ch in s)
    alpha = sum(ch.isalpha() or ch == " " for ch in s)
    return (sym > 6 or s.count("=") >= 2 or digits > 0.15 * len(s) or alpha < 0.82 * len(s) or "->" in s or "…" in s or "➔" in s or "∞" in s or bool(re.search(r"\d\)", s))
            or bool(re.search(r"\b(return|loop do|initialize|function)\b", s)))


def lectures_of(passages):
    """[(number, title, slide count)] for the course."""
    out = []
    for n, g in passages.groupby("lecture"):
        out.append({"n": int(n), "title": str(g["lecture_title"].iloc[0]), "slides": int(len(g))})
    return sorted(out, key=lambda x: x["n"])


def _df_table(passages):
    df = Counter()
    for t in passages["body"]:
        df.update(set(_content(t)))
    return df, max(1, len(passages))


def _tfidf(counter, df, n_docs):
    return {w: c * math.log((1 + n_docs) / (1 + df.get(w, 0))) + 0.0 for w, c in counter.items()}


# ------------------------------------------------------------------ terms and definitions
def _clean_term(t):
    t = re.sub(r"\s+", " ", t).strip(" :-*")
    t = re.sub(r"^(?:A|An|The)\s+", "", t)
    return t


def _good_term(t, allow_short=False):
    if t.lower() in GENERIC or t.lower() in STOP:
        return False
    ws = t.split()
    if not 1 <= len(ws) <= 5 or len(t) < 2:
        return False
    if ws[0].lower() in BAD_START and not (allow_short and ws[0].lower() in GOOD_SHORT):
        return False
    if any(w.lower() in {"is", "are", "was", "of", "to", "that", "which"} for w in ws[1:2]) and len(ws) > 3:
        return False
    return not any(ch.isdigit() for ch in t) or bool(re.match(r"^[A-Z][\w\*\-]*$", t))


_IS = r"(?:is|are|means|refers to|stands for|is defined as|are defined as|is called|is known as|is the|is a|is an|are the)"
_START = re.compile(r"^(?P<t>[A-Z][A-Za-z0-9\-\*/&' ]{1,40}?)\s+(?:is|are|means|refers to|stands for)\s+(?P<d>.{14,230})$")
_COLON = re.compile(r"^(?P<t>[A-Z][A-Za-z0-9\-\*/ ]{1,28}?)\s*:\s+(?P<d>[A-Za-z].{14,230})$")


def _known_vocab(passages, df, n_docs, glossary=None):
    v = set()
    for k in keywords(passages, df, n_docs, top=90):
        v.update(k.split())
    if glossary is not None and len(glossary):
        for e in glossary["english"]:
            v.update(str(e).lower().split())
    return v - GENERIC


def terms(passages, glossary=None, vocab=None):
    """Definitions found in the slides: a sentence that starts with the term and then says what it is.

    Returns a list of {term, definition, slide, lecture, ar}. The Arabic word comes from the course glossary.
    """
    gl = {}
    if glossary is not None and len(glossary):
        for a, e in zip(glossary["arabic"], glossary["english"]):
            gl.setdefault(str(e).strip().lower(), str(a).strip())
    found, seen = [], set()
    for _, r in passages.iterrows():
        for s in _sentences(str(r["body"])):
            for pat in (_START, _COLON):
                m = pat.match(s)
                if not m:
                    continue
                t, d = _clean_term(m.group("t")), re.sub(r"\s+", " ", m.group("d")).strip(" .,;:")
                key = t.lower()
                d = re.sub(r"^(?:is|are|means)\s+", "", d, flags=re.I)
                d = re.sub(r"^(?:cont\.?\s*\d*|\(\w+\))\s*", "", d)
                toks = [w.lower() for w in WORD.findall(t)]
                t = " ".join(dict.fromkeys(t.split())) if len(set(toks)) < len(toks) else t
                core = [w for w in toks if w not in STOP]
                known = vocab is None or (len(t.split()) <= 3 and core and all(w in vocab for w in core)) or bool(re.fullmatch(r"[A-Z][A-Z\-\*]{1,14}( algorithm)?", t))
                if key in seen or not known or not _good_term(t, allow_short=pat is _COLON) or len(d.split()) < 5 or _codey(d):
                    continue
                seen.add(key)
                found.append({"term": t, "definition": d[0].upper() + d[1:] + ("" if d[-1] in "?!" else "."), "slide": int(r["slide"]), "lecture": int(r["lecture"]), "ar": gl.get(key, "")})
                break
    # a course glossary term whose own sentence says what it is (the term is in the first words of the sentence)
    for en, ar in gl.items():
        if en in seen or len(en) < 4 or en in GENERIC or en in {"what is", "games"}:
            continue
        done = False
        for _, r in passages.iterrows():
            for s in _sentences(str(r["body"])):
                m = re.match(r"^(?:\W*\w+\W+){0,3}?" + re.escape(en) + r"\b\W*(?:is|are|means|refers to|can be|consists|uses)\b", s, re.I)
                if m and len(s.split()) >= 9 and not _codey(s):
                    seen.add(en)
                    found.append({"term": en.title() if en.islower() else en, "definition": s if s.endswith(".") else s + ".", "slide": int(r["slide"]), "lecture": int(r["lecture"]), "ar": ar})
                    done = True
                    break
            if done:
                break
    found.sort(key=lambda x: (x["lecture"], x["slide"], x["term"].lower()))
    return found


# ------------------------------------------------------------------ keywords
def keywords(passages, df, n_docs, top=12, per_topic=None):
    """Most characteristic words and two-word phrases (each must appear on at least two slides)."""
    c, slides = Counter(), Counter()
    for t in passages["body"]:
        ws = _content(t)
        c.update(ws)
        slides.update(set(ws))
    sc = {w: v for w, v in _tfidf(c, df, n_docs).items() if slides[w] >= (2 if len(passages) > 3 else 1) and len(w) >= 4 and w not in GENERIC and not w.endswith("'s")}
    bi, bslides = Counter(), defaultdict(set)
    for idx, t in enumerate(passages["body"]):
        ws = _words(t)
        for a, b in zip(ws, ws[1:]):
            if a != b and a not in STOP and b not in STOP and len(a) > 2 and len(b) > 2 and a not in GENERIC and b not in GENERIC:
                bi[(a, b)] += 1
                bslides[(a, b)].add(idx)
    phrases = {" ".join(k): v * (sc.get(k[0], 1) + sc.get(k[1], 1)) / 2 for k, v in bi.items()
               if len(bslides[k]) >= 2 and v >= 3 and k[0] in sc and k[1] in sc and c[k[0]] >= 3 and c[k[1]] >= 3}
    cand = {**sc, **{p: s * 1.4 for p, s in phrases.items()}}
    ranked = sorted(cand.items(), key=lambda x: -x[1])
    out, used = [], set()
    for w, _ in ranked:
        parts = set(w.split())
        if parts & used:
            continue
        out.append(w)
        used |= parts
        if len(out) >= top:
            break
    return out


# ------------------------------------------------------------------ extractive summary
_NOTE_JUNK = re.compile(r"^(Note|Notes|Next lecture|Reference|References|See)\b|\b\d(?:st|nd|rd|th) Ed\b|\bEd\.\)|Regulation No\.?$|\bISBN\b|©", re.I)


def summarize(passages, df, n_docs, n=8):
    """The n most informative sentences of the lecture, in slide order. Each: {text, slide, lecture}."""
    c = Counter()
    for t in passages["body"]:
        c.update(_content(t))
    w = _tfidf(c, df, n_docs)
    cand = []
    for _, r in passages.iterrows():
        for i, s in enumerate(_sentences(str(r["body"]))):
            toks = _content(s)
            if _NOTE_JUNK.search(s):
                continue
            if len(toks) < 4 or len(s.split()) > 32 or s.split()[0].lower() in BAD_START - {"the", "this", "a", "an", "in"}:
                continue
            score = sum(w.get(t, 0) for t in set(toks)) / (len(toks) ** 0.6)
            if re.search(r"\b(is|are|means|defined|called|consists|uses|expands|chooses|finds|represents|ensures|guarantees)\b", s):
                score *= 1.25                                   # explanatory sentences first
            if i == 0:
                score *= 1.1
            cand.append((score, int(r["lecture"]), int(r["slide"]), s))
    cand.sort(key=lambda x: -x[0])
    picked, per_slide, seen_toks = [], Counter(), []
    for score, lec, slide, s in cand:
        if per_slide[(lec, slide)] >= 1:
            continue
        toks = set(_content(s))
        if any(len(toks & p) / max(1, min(len(toks), len(p))) > 0.7 for p in seen_toks):   # near duplicate
            continue
        picked.append({"text": s, "slide": slide, "lecture": lec})
        per_slide[(lec, slide)] += 1
        seen_toks.append(toks)
        if len(picked) >= n:
            break
    return sorted(picked, key=lambda x: (x["lecture"], x["slide"]))


# ------------------------------------------------------------------ flashcards, quiz
def flashcards(defs, summary, seed=0, vocab=None):
    cards = [{"front": d["term"], "back": d["definition"], "slide": d["slide"], "lecture": d["lecture"], "ar": d["ar"]} for d in defs]
    if len(cards) < 8:                                        # not many definitions: add fill-the-gap cards from the summary
        for s in summary:
            gap = _gap(s["text"], vocab)
            if gap:
                cards.append({"front": gap[0], "back": gap[1], "slide": s["slide"], "lecture": s["lecture"], "ar": "", "cloze": True})
    random.Random(seed).shuffle(cards)
    return cards[:40]


def _case_like(word, model):
    return word.lower() if model.islower() else word.title() if model.istitle() else word


def _gap(sentence, vocab=None):
    """Hide the most important word of a sentence: (sentence with ____, answer)."""
    toks = [w for w in WORD.findall(sentence) if w.lower() not in STOP and w.lower() not in GENERIC and len(w) > 4]
    if vocab:
        good = [w for w in toks if w.lower() in vocab]
        toks = good or toks
    if not toks:
        return None
    pick = max(toks, key=lambda w: (w.lower() in (vocab or ()), len(w)))
    return re.sub(r"\b" + re.escape(pick) + r"\b", "______", sentence, count=1), pick


def quiz(defs, summary, kws, seed=0, count=10, words=None, vocab=None):
    """Multiple-choice questions: which term matches a definition, and fill-the-gap. Each has 4 options."""
    rnd = random.Random(seed)
    pool_terms = [d["term"] for d in defs]
    pool_words = [w.title() for w in (words or []) if " " not in w] + [k.title() for k in kws if " " not in k]
    qs = []
    for d in defs:
        others = [t for t in pool_terms if t.lower() != d["term"].lower()]
        if len(others) < 3:
            continue
        opts = rnd.sample(others, 3) + [d["term"]]
        rnd.shuffle(opts)
        qs.append({"q": d["definition"], "kind": "term", "options": opts, "answer": opts.index(d["term"]), "slide": d["slide"], "lecture": d["lecture"],
                   "why": d["term"] + ": " + d["definition"]})
    for s in summary:
        gap = _gap(s["text"], vocab)
        if not gap:
            continue
        sentence, ans = gap
        near = sorted({_case_like(k, ans) for k in pool_words if k.lower() != ans.lower() and k.lower() not in s["text"].lower() and abs(len(k) - len(ans)) <= 4})
        if len(near) < 3:
            continue
        opts = rnd.sample(near, 3) + [ans]
        rnd.shuffle(opts)
        qs.append({"q": sentence, "kind": "gap", "options": opts, "answer": opts.index(ans), "slide": s["slide"], "lecture": s["lecture"],
                   "why": s["text"]})
    rnd.shuffle(qs)
    return qs[:count]


# ------------------------------------------------------------------ concept map
def concept_map(passages, topics_df, df, n_docs, title, lang="en", width=1100, height=640, defs=None):
    """Radial map: lecture title in the middle, its topics around it, key terms around each topic.

    Returns {nodes:[{id,label,kind,x,y,w,slides:[..]}], links:[{a,b,kind}]}; kind: root | topic | term.
    """
    names = dict(zip(topics_df.topic, topics_df.name_ar if lang == "ar" else topics_df.name))
    prereq = {r.topic: r.prereq_list for r in topics_df.itertuples()}
    need = 3 if len(passages) > 12 else 1
    present = [t for t in topics_df.topic if (passages["topic"] == t).sum() >= need]
    lec_kw = keywords(passages, df, n_docs, top=40)
    term_names = [d["term"] for d in (defs or []) if len(d["term"].split()) <= 3]
    cx, cy = width / 2, height / 2
    nodes = [{"id": "root", "label": title, "kind": "root", "x": cx, "y": cy, "slides": []}]
    links = []

    alltext = " ".join(str(b) for b in passages["body"])
    lower_words = set(re.findall(r"\b[a-z]{3,}\b", alltext))

    def _ok_label(lab):                                       # drop author names / book credits (never written in lower case)
        ws = [w for w in re.findall(r"[A-Za-z]{3,}", lab)]
        return bool(ws) and any(w.lower() in lower_words for w in ws)

    def _joined(lab):                                         # "mecha tronic" -> "mechatronic" when the slides write it as one word
        j = lab.replace(" ", "").lower()
        return j if " " in lab and re.search(r"\b" + re.escape(j) + r"\b", alltext.lower()) else lab

    used = set()                                              # a term appears once on the whole map

    def pick_terms(sub, k):
        text = " ".join(sub["body"]).lower()
        slides_of = lambda lab: [[int(a), int(b)] for a, b, tx in zip(sub["lecture"], sub["slide"], sub["body"]) if lab.lower() in tx.lower()][:6]
        cand = [(3 * text.count(t.lower()), t) for t in term_names if t.lower() in text]
        cand += [(text.count(w) * (2 if " " in w else 1), w) for w in lec_kw if text.count(w) >= 2]
        out, seen = [], set()
        for _, lab in sorted(cand, key=lambda x: -x[0]):
            lab = _joined(lab)
            if not _ok_label(lab):
                continue
            if lab.lower() in used or lab.lower() in seen or any(lab.lower() in o.lower() or o.lower() in lab.lower() for o in out):
                continue
            out.append(lab)
            seen.add(lab.lower())
            used.add(lab.lower())
            if len(out) >= k:
                break
        return [(lab, slides_of(lab)) for lab in out]

    n = len(present)
    if n <= 1:                                                 # one topic: key terms straight around the title
        sub = passages
        items = pick_terms(sub, 7)
        for j, (lab, sl) in enumerate(items):
            ang = -math.pi / 2 + 2 * math.pi * j / max(1, len(items))
            nodes.append({"id": f"k_{j}", "label": lab, "kind": "term", "x": cx + width * 0.32 * math.cos(ang), "y": cy + height * 0.34 * math.sin(ang), "slides": sl})
            links.append({"a": "root", "b": f"k_{j}", "kind": "main"})
    else:
        per = 1 if n > 9 else 2 if n > 6 else 3
        rx, ry = width * 0.27, height * 0.27
        for i, t in enumerate(present):
            ang = -math.pi / 2 + 2 * math.pi * i / n
            tx, ty = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
            sub = passages[passages["topic"] == t]
            nodes.append({"id": "t_" + t, "label": names.get(t, t), "kind": "topic", "x": tx, "y": ty,
                          "slides": [[int(a), int(b)] for a, b in zip(sub["lecture"], sub["slide"])][:8]})
            links.append({"a": "root", "b": "t_" + t, "kind": "main"})
            items = pick_terms(sub, per)
            spread = 0.5 if per > 1 else 0
            for j, (lab, sl) in enumerate(items):
                a2 = ang + (j - (len(items) - 1) / 2) * spread * 0.9
                nodes.append({"id": f"k_{t}_{j}", "label": lab, "kind": "term", "x": tx + width * 0.19 * math.cos(a2), "y": ty + height * 0.21 * math.sin(a2), "slides": sl})
                links.append({"a": "t_" + t, "b": f"k_{t}_{j}", "kind": "term"})
        for t in present:                                      # prerequisites between topics (dashed)
            for p in prereq.get(t, []):
                if p in present:
                    links.append({"a": "t_" + p, "b": "t_" + t, "kind": "prereq"})
    _finish_layout(nodes, width, height)
    return {"nodes": nodes, "links": links, "w": width, "h": height}


def _wrap(label, width, max_lines=2):
    """Split a label into at most `max_lines` lines of about `width` characters (the last line gets an ellipsis if cut)."""
    words, lines, cur = label.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(1, width - 1)].rstrip() + "…"
    return lines


def _finish_layout(nodes, width, height):
    """Give every node its text lines and box size, push overlapping boxes apart, keep all inside the picture."""
    spec = {"root": (16, 9.2, 46), "topic": (22, 8.0, 0), "term": (16, 7.0, 0)}
    for nd in nodes:
        wch, cw, _ = spec[nd["kind"]]
        nd["lines"] = _wrap(nd["label"], wch, 3 if nd["kind"] == "topic" else 2)
        nd["w"] = int(max(len(l) for l in nd["lines"]) * cw + 28)
        nd["h"] = 21 * len(nd["lines"]) + 14 if nd["kind"] != "term" else 20 * len(nd["lines"]) + 12
    gap = 10
    for _ in range(140):
        moved = False
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                ox = (a["w"] + b["w"]) / 2 + gap - abs(dx)
                oy = (a["h"] + b["h"]) / 2 + gap - abs(dy)
                if ox > 0 and oy > 0:
                    moved = True
                    fix_a, fix_b = a["kind"] == "root", b["kind"] == "root"
                    share_a = 0 if fix_a else (1 if fix_b else .5)
                    share_b = 0 if fix_b else (1 if fix_a else .5)
                    if oy <= ox:                                   # push apart on the shorter way
                        sgn = 1 if dy >= 0 else -1
                        a["y"] -= sgn * oy * share_a
                        b["y"] += sgn * oy * share_b
                    else:
                        sgn = 1 if dx >= 0 else -1
                        a["x"] -= sgn * ox * share_a
                        b["x"] += sgn * ox * share_b
        for nd in nodes:
            nd["x"] = min(width - nd["w"] / 2 - 4, max(nd["w"] / 2 + 4, nd["x"]))
            nd["y"] = min(height - nd["h"] / 2 - 4, max(nd["h"] / 2 + 4, nd["y"]))
        if not moved:
            break
    for nd in nodes:
        nd["x"], nd["y"] = round(nd["x"], 1), round(nd["y"], 1)


# ------------------------------------------------------------------ info cards
def info_cards(passages, defs, kws, topic_names):
    words = sum(len(str(t).split()) for t in passages["body"])
    return {"slides": int(len(passages)), "terms": len(defs), "minutes": max(1, round(words / 150)), "topics": topic_names, "keywords": kws[:8]}


# ------------------------------------------------------------------ the whole kit for one lecture (or all)
def build(passages, topics_df, glossary, lecture=None, lang="en", seed=0, n_summary=8, course_title=""):
    allp = prepare(passages)
    df, n_docs = _df_table(allp)
    sel = allp if not lecture else allp[allp["lecture"] == int(lecture)]
    if sel.empty:
        sel, lecture = allp, None
    names = dict(zip(topics_df.topic, topics_df.name_ar if lang == "ar" else topics_df.name))
    vocab = _known_vocab(allp, df, n_docs, glossary)
    defs = terms(sel, glossary, vocab)
    kws = keywords(sel, df, n_docs, top=14)
    summ = summarize(sel, df, n_docs, n=n_summary)
    tp = [names.get(t, t) for t in topics_df.topic if (sel["topic"] == t).sum() >= 2]
    title = str(sel["lecture_title"].iloc[0]) if lecture else ""
    return {"lecture": int(lecture) if lecture else None, "title": title, "summary": summ, "terms": defs, "keywords": kws,
            "cards": flashcards(defs, summ, seed, vocab), "quiz": quiz(defs, summ, kws, seed, words=keywords(sel, df, n_docs, top=40) + keywords(allp, df, n_docs, top=60), vocab=vocab), "info": info_cards(sel, defs, kws, tp),
            "map": concept_map(sel, topics_df, df, n_docs, title or course_title or "Course", lang, defs=defs), "notes": listen_notes(title, summ, defs)}


def listen_notes(title, summary, defs):
    """The read-aloud material as separate notes: [{kind, text, slide, lecture, ar}]; shown one under the other."""
    notes = [{"kind": "note", "text": x["text"], "slide": x["slide"], "lecture": x["lecture"]} for x in summary]
    for d in defs[:6]:
        notes.append({"kind": "term", "text": f"{d['term']}: {d['definition']}", "term": d["term"], "ar": d.get("ar", ""),
                      "slide": d["slide"], "lecture": d["lecture"]})
    return notes


# ------------------------------------------------------------------ files
def table_xlsx(defs, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Terms"
    ws.append(["Term", "Arabic", "Definition (from the slides)", "Slide", "Lecture"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F6F6A")
    for d in defs:
        ws.append([d["term"], d["ar"], d["definition"], d["slide"], d["lecture"]])
    for col, w in zip("ABCDE", (28, 24, 90, 8, 9)):
        ws.column_dimensions[col].width = w
    wb.save(path)


def slides_pptx(kit, course_title, path):
    """Revision deck: title, one slide per summary group, a terms slide. Needs python-pptx."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    teal, ink = RGBColor(0x2F, 0x6F, 0x6A), RGBColor(0x1F, 0x2A, 0x2A)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.33), Inches(7.5)
    blank = prs.slide_layouts[6]

    def slide(title, lines, size=22):
        s = prs.slides.add_slide(blank)
        bar = s.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(1.1))
        bar.fill.solid(); bar.fill.fore_color.rgb = teal; bar.line.fill.background()
        tb = s.shapes.add_textbox(Inches(0.6), Inches(0.2), Inches(12), Inches(0.8)).text_frame
        tb.text = title
        tb.paragraphs[0].runs[0].font.size = Pt(32); tb.paragraphs[0].runs[0].font.bold = True
        tb.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        body = s.shapes.add_textbox(Inches(0.7), Inches(1.5), Inches(11.9), Inches(5.4)).text_frame
        body.word_wrap = True
        for i, ln in enumerate(lines):
            p = body.paragraphs[0] if i == 0 else body.add_paragraph()
            p.text = ln; p.space_after = Pt(14)
            for r in p.runs:
                r.font.size = Pt(size); r.font.color.rgb = ink
        return s

    t = kit["title"] or course_title
    slide(t, [course_title, f"{kit['info']['slides']} slides · {kit['info']['terms']} key terms · about {kit['info']['minutes']} min to review",
              "Built from the lecture slides only."], size=24)
    for i in range(0, len(kit["summary"]), 3):
        chunk = kit["summary"][i:i + 3]
        slide("Key ideas", [f"• {c['text']}  (slide {c['slide']})" for c in chunk], size=22)
    for i in range(0, min(len(kit["terms"]), 12), 4):
        slide("Key terms", [f"{d['term']}: {d['definition']}" for d in kit["terms"][i:i + 4]], size=20)
    prs.save(path)
