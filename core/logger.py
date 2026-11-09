"""Excel database (logs.xlsx). Every write goes through ONE function: log_to_excel()."""
import threading
from datetime import datetime
from openpyxl import Workbook, load_workbook

import config

SHEETS = {
    "Questions": ["id", "time", "student_code", "question", "topic", "confidence", "first_slide",
                  "found", "method", "helpful", "course"],
    "Answers": ["id", "time", "student_code", "question_id", "topic", "correct", "hints_used", "mastery_after", "course"],
    "Visits": ["id", "time", "student_code", "page", "course"],
    "Feedback": ["id", "time", "student_code", "question_log_id", "helpful", "comment", "course"],
}
_lock = threading.Lock()


def _open(path):
    if path.exists():
        wb = load_workbook(path)
    else:
        wb = Workbook()
        wb.remove(wb.active)
    for name, cols in SHEETS.items():
        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            ws.append(cols)
        else:                                   # older file without the new columns -> add their headers
            ws = wb[name]
            have = [c.value for c in ws[1]]
            for col in cols[len(have):]:
                if col not in have:
                    ws.cell(row=1, column=len(have) + 1, value=col)
                    have.append(col)
    return wb


def log_to_excel(sheet: str, record: dict, update_id: int = None, path=None) -> int:
    """Append `record` to `sheet` (or update the row whose id == update_id). Returns the row id."""
    path = path or config.LOGS_XLSX
    cols = SHEETS[sheet]
    with _lock:
        wb = _open(path)
        ws = wb[sheet]
        if update_id is not None:
            for row in ws.iter_rows(min_row=2):
                if row[0].value == update_id:
                    for key, val in record.items():
                        if key in cols:
                            row[cols.index(key)].value = val
                    break
            row_id = update_id
        else:
            row_id = ws.max_row  # header is row 1 -> first record gets id 1
            rec = {"id": row_id, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **record}
            ws.append([rec.get(c, "") for c in cols])
        wb.save(path)
    return row_id


def read_sheet(sheet: str, path=None):
    """Read a sheet as a list of dicts (used by the dashboard and the mastery replay)."""
    path = path or config.LOGS_XLSX
    if not path.exists():
        return []
    wb = load_workbook(path, read_only=True)
    if sheet not in wb.sheetnames:
        return []
    rows = list(wb[sheet].iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = rows[0]
    out = [dict(zip(header, r)) for r in rows[1:] if any(v is not None for v in r)]
    for r in out:                                # rows written before multi-course belong to the first course
        if not r.get("course"):
            r["course"] = config.DEFAULT_COURSE
    return out


def ensure_workbook(path=None):
    path = path or config.LOGS_XLSX
    with _lock:
        _open(path).save(path)
