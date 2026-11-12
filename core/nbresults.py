"""Results of the Google Colab notebooks, brought into the site, and the "what should I improve" advice.

Colab cannot be a live server for the site (the session stops after some hours of silence and the address changes), so the
notebooks are used as a LAB: the doctor runs a notebook, downloads its results (.zip or .json) and imports them on the
"AI models" page. The site then shows them beside the automatic evaluation and turns every weak number into a concrete
next step. Accepted files (inside the zip or alone):
    auto_metrics.json      search quality measured on Colab         (StudyMate_Search_Models.ipynb)
    topic_classifier.json  topic classifier cross-validation        (StudyMate_Search_Models.ipynb)
    image_metrics.json     lecture-image recognition + image search (StudyMate_Image_Recognition.ipynb)
    figure_text.json       text read from the pictures of the slides, {"L01S05": "..."}  -> used by the search
"""
import io
import json
import os
import zipfile
from datetime import datetime

import config
from core import figures

COLAB_BASE = os.environ.get("STUDYMATE_COLAB_BASE", "https://colab.research.google.com/github/pikachu8240/StudyMate/blob/main/notebooks/")
NOTEBOOKS = {"search": "StudyMate_Search_Models.ipynb", "image": "StudyMate_Image_Recognition.ipynb"}
KINDS = {"auto_metrics.json": "search", "topic_classifier.json": "topic", "image_metrics.json": "image", "figure_text.json": "figures"}
MAX_FILE = 6 * 1024 * 1024
SHORT_SLIDE = 150


def colab_url(which):
    return COLAB_BASE.rstrip("/") + "/" + NOTEBOOKS[which]


def _file(code):
    return config.course_paths(code).reports / "notebook_results.json"


def load(code):
    try:
        return json.loads(_file(code).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _members(filename, data):
    """{basename: bytes} of the accepted files. Only known names are read; paths inside a zip are ignored."""
    out = {}
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                base = os.path.basename(info.filename)
                if base in KINDS and 0 < info.file_size <= MAX_FILE:
                    out[base] = z.read(info)
    elif os.path.basename(filename) in KINDS:
        out[os.path.basename(filename)] = data
    return out


def import_results(code, filename, data):
    """Store the results of a notebook. Returns {"kinds": [...], "figures": n} or None when nothing usable was found."""
    if len(data) > 20 * 1024 * 1024:
        return None
    try:
        found = _members(filename or "", data)
    except zipfile.BadZipFile:
        return None
    cur = load(code) or {}
    kinds, n_fig = [], 0
    for name, raw in found.items():
        try:
            obj = json.loads(raw.decode("utf-8-sig"))
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = KINDS[name]
        if kind == "figures":
            n_fig = figures.save_imported(config.course_paths(code).data, obj)
        elif kind == "search" and not isinstance(obj.get("methods"), dict):
            continue
        else:
            cur[kind] = obj
        kinds.append(kind)
    if not kinds:
        return None
    cur["when"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur["figures"] = n_fig or cur.get("figures", 0)
    f = _file(code)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"kinds": kinds, "figures": n_fig}


def _pct(x):
    return round(float(x) * 100)


def advise(ae, nb, short_slides=0, slides=0):
    """Next steps from the numbers. Returns [(level, key, args)] where level is bad / warn / ok / info."""
    out = []
    if ae:
        ms = ae.get("methods", {})
        best = max(ms.values(), key=lambda m: m["top1"]) if ms else None
        if best:
            if best["top1"] < 0.30:
                out.append(("bad", "adv_top1_low", {"n": _pct(best["top1"]), "m": best["name"]}))
            if best["top3"] - best["top1"] >= 0.20:
                out.append(("warn", "adv_top3_gap", {"a": _pct(best["top1"]), "b": _pct(best["top3"])}))
        off = ae.get("offtopic", {})
        if off.get("total") and off["rejected"] / off["total"] < 0.75:
            out.append(("bad", "adv_gate_weak", {"r": off["rejected"], "t": off["total"]}))
        hist = ae.get("history", [])
        if len(hist) >= 2 and hist[-1].get("slides") == hist[-2].get("slides") and hist[-2]["hybrid"] - hist[-1]["hybrid"] >= 0.04:
            out.append(("warn", "adv_dropped", {"a": _pct(hist[-2]["hybrid"]), "b": _pct(hist[-1]["hybrid"])}))
        if ae.get("slides", 0) < 100:
            out.append(("warn", "adv_few_slides", {"n": ae.get("slides", 0)}))
    if slides and short_slides / slides >= 0.15:
        out.append(("warn", "adv_short_slides", {"k": short_slides, "n": slides, "p": round(100 * short_slides / slides)}))
    nb = nb or {}
    topic = nb.get("topic") or {}
    if topic:
        best = max(topic.values())
        if best < 80:
            out.append(("warn", "adv_topic_low", {"n": round(best)}))
    img = nb.get("image") or {}
    if img:
        acc = img.get("test_accuracy", 0)
        if acc < 0.5:
            out.append(("warn", "adv_image_low", {"n": _pct(acc), "k": img.get("images", 0)}))
        if "ImageNet weights not available" in str(img.get("model", "")):
            out.append(("info", "adv_image_weights", {}))
    if not nb.get("search") and not img:
        out.append(("info", "adv_no_notebook", {}))
    if not out:
        out.append(("ok", "adv_all_good", {}))
    return out
