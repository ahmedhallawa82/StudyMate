"""The list of course codes the admin uploads (Excel). Doctors pick a code from it when they add a course.

data/course_codes.json -> [{"code": "AUTO", "name_en": "Automotive", "name_ar": ""}]
"""
import io
import json
import threading

import config

FILE = lambda: config.BASE_DIR / "data" / "course_codes.json"
_lock = threading.Lock()
HEADER = ["Code", "Course Name (English)", "Course Name (Arabic)"]


def load():
    try:
        return json.loads(FILE().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save(rows):
    f = FILE()
    f.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def lookup(code):
    code = (code or "").strip().upper()
    return next((r for r in load() if r["code"] == code), None)


def _find(heads, *keys, exact=False):
    for i, h in enumerate(heads):
        if any((h == k) if exact else (k in h) for k in keys):
            return i
    return None


def parse_xlsx(data: bytes):
    """Rows of the first sheet -> [{code, name_en, name_ar}].
    Understands 'Official Code' / 'Code' / 'Suggested Code' (the official one wins when it is filled) and the names columns;
    without recognisable headers the columns are taken as code, English name, Arabic name."""
    from openpyxl import load_workbook
    from core.autocourse import clean_code
    ws = load_workbook(io.BytesIO(data), data_only=True, read_only=True).worksheets[0]
    rows = [[("" if c is None else str(c).strip()) for c in r] for r in ws.iter_rows(values_only=True)]
    rows = [r for r in rows if any(r)]
    if not rows:
        raise ValueError("empty")
    heads = [h.lower() for h in rows[0]]
    off = _find(heads, "official")
    plain = _find(heads, "code", exact=True) if _find(heads, "code", exact=True) is not None else _find(heads, "course code", exact=True)
    sug = _find(heads, "suggested")
    ar = _find(heads, "arabic", "name_ar", "عرب")
    en = _find(heads, "course name", "name (english)", "english", "name_en", exact=False)
    if en is not None and en == ar:
        en = _find(heads, "course name (english)", "name (english)", "english", "name_en")
    if en is None:
        en = _find(heads, "name", exact=True)
    body = rows[1:]
    if off is None and plain is None and sug is None:               # no headers: code | English name | Arabic name
        off, en, ar, body = 0, 1 if len(rows[0]) > 1 else None, 2 if len(rows[0]) > 2 else None, rows
    cell = lambda r, i: r[i] if i is not None and i < len(r) else ""
    out, seen = [], set()
    for r in body:
        code = clean_code(cell(r, off) or cell(r, plain) or cell(r, sug))
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name_en": cell(r, en)[:120], "name_ar": cell(r, ar)[:120]})
    if not out:
        raise ValueError("no codes")
    return out


def template_xlsx(rows=None):
    """A ready-to-fill sheet (filled with the given rows, or a few examples)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Course Codes"
    ws.append(HEADER)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows or [{"code": "AUTO", "name_en": "Automotive Engineering", "name_ar": "هندسة السيارات"},
                      {"code": "CTRL", "name_en": "Control Systems", "name_ar": "نظم التحكم"}]:
        ws.append([r["code"], r["name_en"], r["name_ar"]])
    for col, w in zip("ABC", (14, 38, 34)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
