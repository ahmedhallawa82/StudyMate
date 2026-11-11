"""Excel database (logs.xlsx). Every write goes through ONE function: log_to_excel()."""
import queue
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
    "Students": ["id", "time", "student_code", "first_name", "last_name", "email"],
    "Exams": ["id", "time", "student_code", "attempt_id", "n_questions", "correct", "score_pct", "duration_sec", "lang", "wrong", "course"],
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


def _next_id(ws):
    """One more than the biggest id in column A (rows can be deleted, so max_row is not safe any more)."""
    ids = [r[0] for r in ws.iter_rows(min_row=2, max_col=1, values_only=True) if isinstance(r[0], (int, float))]
    return int(max(ids)) + 1 if ids else 1


_CACHE = {}          # path -> (mtime_ns, {sheet: [row dicts]})  (re-read only when the file changes)
_Q = queue.Queue()   # page-visit rows waiting to be written by the background thread
_worker = None


def _writer():
    """Writes queued visit rows in one batch (one load + one save), so a page view never waits for the Excel file."""
    while True:
        batch = [_Q.get()]
        try:
            while True:
                batch.append(_Q.get_nowait())
        except queue.Empty:
            pass
        try:
            by_path = {}
            for sheet, record, path in batch:
                by_path.setdefault(path, []).append((sheet, record))
            for path, items in by_path.items():
                with _lock:
                    wb = _open(path)
                    for sheet, record in items:
                        ws = wb[sheet]
                        rec = {"id": _next_id(ws), "time": record.pop("_time"), **record}
                        ws.append([rec.get(c, "") for c in SHEETS[sheet]])
                    wb.save(path)
                    _CACHE.pop(path, None)
        except Exception as e:            # logging must never break the site
            print("log writer:", e)
        finally:
            for _ in batch:
                _Q.task_done()


def log_async(sheet: str, record: dict, path=None):
    """Fire-and-forget append (used for page visits). Returns at once."""
    global _worker
    path = path or config.LOGS_XLSX
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_writer, daemon=True)
        _worker.start()
    _Q.put((sheet, {**record, "_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, path))


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
            row_id = _next_id(ws)  # first record gets id 1
            rec = {"id": row_id, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **record}
            ws.append([rec.get(c, "") for c in cols])
        wb.save(path)
        _CACHE.pop(path, None)
    return row_id


def read_sheet(sheet: str, path=None):
    """Read a sheet as a list of dicts (dashboard, mastery replay, home). The file is parsed once per change, not once per call."""
    path = path or config.LOGS_XLSX
    if not path.exists():
        return []
    if _worker is not None:
        _Q.join()                                # let pending visit rows reach the file first
    mt = path.stat().st_mtime_ns
    hit = _CACHE.get(path)
    if not hit or hit[0] != mt:
        wb = load_workbook(path, read_only=True)
        data = {}
        for name in wb.sheetnames:
            rows = list(wb[name].iter_rows(values_only=True))
            if not rows:
                data[name] = []
                continue
            header = rows[0]
            out = [dict(zip(header, r)) for r in rows[1:] if any(v is not None for v in r)]
            for r in out:                        # rows written before multi-course belong to the first course
                if not r.get("course"):
                    r["course"] = config.DEFAULT_COURSE
            data[name] = out
        wb.close()
        hit = _CACHE[path] = (mt, data)
    return [dict(r) for r in hit[1].get(sheet, [])]


def ensure_workbook(path=None):
    path = path or config.LOGS_XLSX
    with _lock:
        _open(path).save(path)


def delete_course_rows(code: str, path=None) -> int:
    """Remove every logged row of one course (questions, answers, visits, feedback, exams). Rows with no course belong to the first one."""
    path = path or config.LOGS_XLSX
    if not path.exists():
        return 0
    if _worker is not None:
        _Q.join()
    removed = 0
    with _lock:
        wb = _open(path)
        for name, cols in SHEETS.items():
            if "course" not in cols:
                continue
            ws, ci = wb[name], cols.index("course")
            gone = [i for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2)
                    if ((r[ci] if len(r) > ci else None) or config.DEFAULT_COURSE) == code]
            for i in reversed(gone):
                ws.delete_rows(i)
            removed += len(gone)
        wb.save(path)
        _CACHE.pop(path, None)
    return removed


def delete_student_rows(student_code: str, path=None) -> int:
    """Remove every logged row of one student (questions, answers, visits, feedback, exams, registration)."""
    path = path or config.LOGS_XLSX
    if not path.exists():
        return 0
    if _worker is not None:
        _Q.join()
    removed = 0
    with _lock:
        wb = _open(path)
        for name, cols in SHEETS.items():
            if "student_code" not in cols:
                continue
            ws, ci = wb[name], cols.index("student_code")
            gone = [i for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2) if (r[ci] if len(r) > ci else None) == student_code]
            for i in reversed(gone):
                ws.delete_rows(i)
            removed += len(gone)
        wb.save(path)
        _CACHE.pop(path, None)
    return removed
