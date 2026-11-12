"""Readable slide results: repeated header/footer removal, structured text, best sentence, grouping and a short summary.

Used when lecture PDFs are read (build_passages) and when search hits are shown (build_view).
"""
import math
import re
import shutil
import subprocess
from pathlib import Path

PAGE_NO = re.compile(r"^\s*(slide\s*)?\d+\s*(/|of)\s*\d+\s*$|^\s*\d{1,3}\s*$", re.IGNORECASE)
INLINE_NO = re.compile(r"\bslide\s*\d+\s*/\s*\d+\b", re.IGNORECASE)
STOP = set("a an the is are was were be been of in on at to for from by with and or what which who whom how why when where does do did "
           "this that these those it its as into than then there their about can could should would will shall may might me my your our "
           "explain describe define tell give show mean means difference between".split())
NOTE_RE = re.compile(r"^(note|notes|example|e\.g\.|tip|warning|remember|important)\s*:", re.IGNORECASE)


def _norm(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", (line or "").lower())).strip()


def learn_boilerplate(pages_lines, share: float = 0.35, min_pages: int = 5) -> set:
    """Lines (digits ignored) that appear on many slides of one PDF: headers, footers, 'Slide 3 / 15', sources."""
    n = len(pages_lines)
    if n < min_pages:
        return set()
    need = max(3, math.ceil(share * n))
    seen = {}
    for lines in pages_lines:
        for k in {_norm(x) for x in lines if x.strip()}:
            seen[k] = seen.get(k, 0) + 1
    return {k for k, c in seen.items() if c >= need and (len(k) >= 12 or not re.sub(r"[#/\sof|]", "", k))}


def strip_lines(raw: str, boiler: set) -> list:
    """Lines of a page without page numbers and the learned repeated lines."""
    out = []
    for ln in (raw or "").splitlines():
        if not ln.strip() or PAGE_NO.match(ln) or _norm(ln) in boiler:
            continue
        ln = INLINE_NO.sub(" ", ln)
        if ln.strip():
            out.append(ln)
    return out


# ------------------------------------------------------------------ structure
def _sentences(t: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", t) if s.strip()]


def structure(display: str, text: str = "") -> dict:
    """{'title': str, 'items': [{'kind': 'li'|'p'|'note', 'text': str}]} from the line-structured slide text."""
    display = display if isinstance(display, str) and display.strip() else ""
    if display:
        lines = [l for l in display.split("\n") if l.strip()]
    else:                                              # passages built before this feature: split the flat text
        flat = re.sub(r"\s+(?=(Note|Example)\s*:)", "\n", text or "")
        lines = [s for part in flat.split("\n") for s in _sentences(part)]
    title = ""
    if len(lines) > 1 and not lines[0].startswith("• ") and len(lines[0]) <= 90 and not lines[0].rstrip().endswith("."):
        title, lines = lines[0], lines[1:]
    items = []
    for l in lines:
        if l.startswith("• "):
            items.append({"kind": "li", "text": l[2:].strip()})
        elif NOTE_RE.match(l):
            items.append({"kind": "note", "text": l.strip()})
        elif items and items[-1]["kind"] in ("p", "li") and l[:1].islower() and not items[-1]["text"].endswith((".", "!", "?", ":")):
            items[-1]["text"] += " " + l                  # a wrapped line continues the previous one
        else:
            items.append({"kind": "p", "text": l.strip()})
    return {"title": title, "items": items}


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def q_tokens(question: str) -> set:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", (question or "").lower().replace("a*", "astar")) if len(w) > 1 and w not in STOP}


def coverage(text: str, qt: set) -> float:
    if not qt:
        return 0.0
    have = {_stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower())}
    return sum(1 for w in qt if w in have or any(h.startswith(w) for h in have)) / len(qt)


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


def _jacc(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# ------------------------------------------------------------------ the view
def build_view(hits: list, question: str, hl, show_best: int = 2, collapse_over: int = 3) -> dict:
    """hits (search results) -> {'summary': [...], 'groups': [...], 'hidden': n}. hl(text, question) -> safe HTML."""
    qt = q_tokens(question)
    kept, hidden = [], 0
    for h in hits:                                           # drop near-identical slides (keep the better ranked one)
        w = _words(h.get("text", ""))
        if any(_jacc(w, _words(k.get("text", ""))) >= 0.85 for k in kept):
            hidden += 1
            continue
        kept.append(h)
    views = []
    for h in kept:
        st = structure(h.get("display", ""), h.get("text", ""))
        items = st["items"]
        for it in items:
            it["cov"] = coverage(it["text"], qt)
        order = sorted(range(len(items)), key=lambda i: (-items[i]["cov"], i))
        best = {i for i in order[:show_best] if items[i]["cov"] > 0} or set(order[:show_best])
        collapse = len(items) > collapse_over
        shown = [dict(it, html=hl(it["text"], question), best=(i in best)) for i, it in enumerate(items) if not collapse or i in best]
        rest = [dict(it, html=hl(it["text"], question), best=False) for i, it in enumerate(items) if collapse and i not in best]
        views.append({"passage_id": h["passage_id"], "lecture": h["lecture"], "slide": h["slide"], "lecture_title": h.get("lecture_title", ""),
                      "topic": h.get("topic"), "score": h.get("score"), "title": st["title"], "title_html": hl(st["title"], question) if st["title"] else "",
                      "shown": shown, "rest": rest, "items": items})
    # group by lecture (best score first), slides in order inside a group; adjacent slides are marked
    groups = {}
    for v in views:
        groups.setdefault(v["lecture"], []).append(v)
    out = []
    for lec, vs in groups.items():
        top = max(v["score"] or 0 for v in vs)
        vs.sort(key=lambda v: v["slide"])
        for i, v in enumerate(vs):
            v["adj"] = i > 0 and v["slide"] == vs[i - 1]["slide"] + 1
        out.append({"lecture": lec, "title": vs[0]["lecture_title"], "top": top, "slides": vs})
    out.sort(key=lambda g: -g["top"])
    return {"summary": summary(views, qt, question, hl), "groups": out, "hidden": hidden}


def summary(views: list, qt: set, question: str, hl, n: int = 3) -> list:
    """Two or three of the best sentences of the top slides, each with its source."""
    cand = []
    for rank, v in enumerate(views[:3]):
        for pos, it in enumerate(v["items"]):
            t = it["text"]
            if 25 <= len(t) <= 260 and it["kind"] != "note":
                cand.append((it["cov"] if qt else 0, -rank, -pos, t, v))
    if not cand:
        return []
    cand.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)
    if qt and cand[0][0] <= 0:
        cand = sorted(cand, key=lambda c: (c[1], c[2]), reverse=True)[:1]      # nothing matches the words (e.g. an Arabic question)
    picked = []
    for c in cand:
        if len(picked) >= n or (qt and c[0] <= 0 and picked):
            break
        if all(_jacc(_words(c[3]), _words(p[3])) < 0.6 for p in picked):
            picked.append(c)
    picked.sort(key=lambda c: (-c[1], -c[2]))
    return [{"html": hl(c[3], question), "src": f"L{c[4]['lecture']} · S{c[4]['slide']}", "passage_id": c[4]["passage_id"]} for c in picked]


# ------------------------------------------------------------------ slide pictures
def slide_png(pdf: Path, page: int, out_dir: Path, big: bool = False):
    """PNG of one slide (cached next to the course data). None when poppler's pdftoppm is not installed."""
    if not shutil.which("pdftoppm"):
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{pdf.stem}__p{page:03d}{'_big' if big else ''}"
    png = base.with_suffix(".png")
    if png.exists() and png.stat().st_mtime >= pdf.stat().st_mtime:
        return png
    subprocess.run(["pdftoppm", "-r", "150" if big else "70", "-f", str(page), "-l", str(page), "-png", "-singlefile", str(pdf), str(base)],
                   check=False, capture_output=True, timeout=60)
    return png if png.exists() else None
