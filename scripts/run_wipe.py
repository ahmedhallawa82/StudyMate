"""Run a scheduled deletion whose time has come (for a PythonAnywhere scheduled task, e.g. every hour):

    cd ~/StudyMate && python3 scripts/run_wipe.py

The site also runs it by itself on the first page request after the time, so this script is only a safety net.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import wipe

if __name__ == "__main__":
    p = wipe.pending()
    if not p:
        print("No deletion is scheduled.")
    elif p["left"] > 0:
        print(f"Scheduled for {p['due_text']} ({p['left'] // 60} minutes left). Nothing done.")
    else:
        print("Deleted", wipe.execute(), "items.")
