"""Copies the doctors table to the admin's private Google Sheet (name | courses | system password | new password).

Needs a Google service account key (JSON) on the server:
  secrets/google_service_account.json   (or the path in the environment variable GOOGLE_SERVICE_ACCOUNT_FILE)
and the sheet shared (Editor) with the service account e-mail. Without the key the site works normally and the
Admin page says that the sheet is not connected. Writing runs in the background so pages stay fast.
"""
import json
import os
import threading
from datetime import datetime

import config

HEADER = ["اسم الدكتور", "المواد المسؤول عنها", "كلمة السر من النظام", "كلمة السر الجديدة (من الدكتور)"]
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "1yS6vzAKf4s_rAK7aN-o8NP9prge0SX2a1ofFTpJB4FU")
STATUS = {"ok": None, "time": "", "error": ""}
_lock = threading.Lock()


def key_file():
    return os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE") or str(config.BASE_DIR / "secrets" / "google_service_account.json")


def enabled():
    return os.path.exists(key_file())


def service_email():
    try:
        return json.load(open(key_file(), encoding="utf-8")).get("client_email", "")
    except Exception:
        return ""


def sheet_url():
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"


def _write(rows):
    with _lock:
        try:
            import gspread
            ws = gspread.service_account(filename=key_file()).open_by_key(SHEET_ID).sheet1
            ws.clear()
            ws.update(values=[HEADER] + rows, range_name="A1")
            STATUS.update(ok=True, error="")
        except Exception as e:                     # never break the site because of the sheet
            STATUS.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
        STATUS["time"] = datetime.now().strftime("%Y-%m-%d %H:%M")


def push(rows, wait=False):
    """Write the whole table (header + rows) to the first tab of the sheet."""
    if not enabled():
        STATUS.update(ok=None, error="", time="")
        return
    t = threading.Thread(target=_write, args=(rows,), daemon=True)
    t.start()
    if wait:
        t.join(30)
