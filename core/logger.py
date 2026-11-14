"""Log database (SQLite). Every write goes through ONE function: log_to_excel().

The name is kept from the Excel days so the rest of the site did not change; the data now lives in a SQLite file
(logs.db, next to the old logs.xlsx). Why: Excel rewrites the whole file on every save, SQLite adds one row;
many people can write at the same time; and a query does not have to read the whole file.

* `logs.xlsx` is imported ONCE the first time the database is created (nothing is lost, the old file stays as a backup).
* The Dashboard's "Download logs.xlsx" button builds an Excel file from the database (export_xlsx)."""
import io
import sqlite3
import threading
from datetime import datetime

import config

SHEETS = {
    "Questions": ["id", "time", "student_code", "question", "topic", "confidence", "first_slide",
                  "found", "method", "helpful", "course"],
    "Answers": ["id", "time", "student_code", "question_id", "topic", "correct", "hints_used", "mastery_after", "course"],
    "Visits": ["id", "time", "student_code", "page", "course"],
    "Feedback": ["id", "time", "student_code", "question_log_id", "helpful", "comment", "course"],
    "Students": ["id", "time", "student_code", "first_name", "last_name", "email"],
    "Exams": ["id", "time", "student_code", "attempt_id", "n_questions", "correct", "score_pct", "duration_sec", "lang", "wrong", "course"],
    "Assistant": ["id", "time", "student_code", "question", "intent", "matched", "course"],   # what people ask the chat assistant
}
_lock = threading.Lock()
_ready = set()          # database files already created / checked in this process


def db_path(path=None):
    """The SQLite file that belongs to a log path (config.LOGS_XLSX -> logs.db)."""
    p = path or config.LOGS_XLSX
    return p.with_suffix(".db")


def _connect(path=None):
    db = db_path(path)
    if db in _ready and not db.exists():              # the file was deleted (Danger zone): build it again
        _ready.discard(db)
    fresh = not db.exists()
    con = sqlite3.connect(db, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    if db not in _ready:
        with _lock:
            _init(con, path or config.LOGS_XLSX, fresh)
            _ready.add(db)
    return con


def _init(con, xlsx, fresh):
    for name, cols in SHEETS.items():
        # no column types on purpose: numbers stay numbers, text stays text, exactly as they were in Excel
        con.execute(f'CREATE TABLE IF NOT EXISTS "{name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                    + ", ".join(f'"{c}"' for c in cols[1:]) + ")")
        have = {r[1] for r in con.execute(f'PRAGMA table_info("{name}")')}
        for c in cols:                                    # a database made before a column existed
            if c not in have:
                con.execute(f'ALTER TABLE "{name}" ADD COLUMN "{c}"')
        for c in ("student_code", "course"):
            if c in cols:
                con.execute(f'CREATE INDEX IF NOT EXISTS "ix_{name}_{c}" ON "{name}" ("{c}")')
    con.commit()
    if fresh and xlsx.exists():
        try:
            _import_xlsx(con, xlsx)
        except Exception as e:                            # a broken old file must not stop the site
            print("logs.xlsx import:", e)


def _import_xlsx(con, xlsx):
    """One-time copy of the old Excel log into the new database (ids and times are kept)."""
    from openpyxl import load_workbook
    wb = load_workbook(xlsx, read_only=True)
    for name, cols in SHEETS.items():
        if name not in wb.sheetnames:
            continue
        rows = list(wb[name].iter_rows(values_only=True))
        if len(rows) < 2:
            continue
        header = [h for h in rows[0]]
        out = []
        for r in rows[1:]:
            if not any(v is not None for v in r):
                continue
            d = dict(zip(header, r))
            out.append([_clean(d.get(c)) for c in cols])
        if out:
            q = ", ".join(f'"{c}"' for c in cols)
            con.executemany(f'INSERT OR IGNORE INTO "{name}" ({q}) VALUES ({",".join("?" * len(cols))})', out)
    wb.close()
    con.commit()


def _clean(v):
    """Excel showed an empty cell as nothing; keep that (no empty strings in the database)."""
    if isinstance(v, str) and v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def log_async(sheet: str, record: dict, path=None):
    """Append a page-visit row. A SQLite insert takes about a millisecond, so no background thread is needed any more."""
    try:
        log_to_excel(sheet, record, path=path)
    except Exception as e:                                # logging must never break the site
        print("log writer:", e)


def log_to_excel(sheet: str, record: dict, update_id: int = None, path=None) -> int:
    """Append `record` to `sheet` (or update the row whose id == update_id). Returns the row id."""
    cols = SHEETS[sheet]
    con = _connect(path)
    try:
        if update_id is not None:
            sets = {k: _clean(v) for k, v in record.items() if k in cols and k != "id"}
            if sets:
                con.execute(f'UPDATE "{sheet}" SET ' + ", ".join(f'"{k}"=?' for k in sets) + " WHERE id=?",
                            [*sets.values(), update_id])
                con.commit()
            return update_id
        rec = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **record}
        keys = [c for c in cols if c != "id" and c in rec]
        cur = con.execute(f'INSERT INTO "{sheet}" (' + ", ".join(f'"{k}"' for k in keys) + ") VALUES ("
                          + ",".join("?" * len(keys)) + ")", [_clean(rec[k]) for k in keys])
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def read_sheet(sheet: str, path=None):
    """Read a sheet as a list of dicts, oldest first (dashboard, mastery replay, home)."""
    con = _connect(path)
    try:
        rows = [dict(r) for r in con.execute(f'SELECT * FROM "{sheet}" ORDER BY id')]
    finally:
        con.close()
    if "course" in SHEETS[sheet]:
        for r in rows:                                    # rows written before multi-course belong to the first course
            if not r.get("course"):
                r["course"] = config.DEFAULT_COURSE
    return rows


def ensure_workbook(path=None):
    """Make sure the database exists (kept under the old name)."""
    _connect(path).close()


ensure_db = ensure_workbook


def delete_course_rows(code: str, path=None) -> int:
    """Remove every logged row of one course (questions, answers, visits, feedback, exams). Rows with no course belong to the first one."""
    con = _connect(path)
    removed = 0
    try:
        for name, cols in SHEETS.items():
            if "course" in cols:
                removed += con.execute(f'DELETE FROM "{name}" WHERE COALESCE(NULLIF("course",\'\'), ?)=?',
                                       (config.DEFAULT_COURSE, code)).rowcount
        con.commit()
    finally:
        con.close()
    return removed


def delete_student_rows(student_code: str, path=None) -> int:
    """Remove every logged row of one student (questions, answers, visits, feedback, exams, registration)."""
    con = _connect(path)
    removed = 0
    try:
        for name, cols in SHEETS.items():
            if "student_code" in cols:
                removed += con.execute(f'DELETE FROM "{name}" WHERE "student_code"=?', (student_code,)).rowcount
        con.commit()
    finally:
        con.close()
    return removed


def export_xlsx(courses=None, path=None):
    """The whole log as an Excel file in memory (for the Dashboard download). `courses` limits the rows to those courses."""
    import pandas as pd
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for sheet, cols in SHEETS.items():
            rows = read_sheet(sheet, path=path)
            if courses is not None:                       # a doctor gets only his courses; sheets with no course (Students) stay closed
                rows = [r for r in rows if r.get("course") in courses]
            pd.DataFrame(rows, columns=cols).to_excel(xw, sheet_name=sheet, index=False)
    buf.seek(0)
    return buf
