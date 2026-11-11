"""Central settings for StudyMate (Project 1E - Course Study Assistant)."""
import os
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Every date and time on the site (today in the calendar, the greeting, log times) follows this time zone, not the server's.
TIMEZONE = os.environ.get("STUDYMATE_TZ", "Africa/Cairo")
os.environ["TZ"] = TIMEZONE
if hasattr(time, "tzset"):
    time.tzset()

COURSE_CODE = "AI"
COURSE_NAME = "Artificial Intelligence"

DATA_DIR = BASE_DIR / "data" / COURSE_CODE
LECTURES_DIR = DATA_DIR / "lectures"
PASSAGES_CSV = DATA_DIR / "passages.csv"
TOPICS_CSV = DATA_DIR / "topics.csv"            # topic id, name, prerequisites
TOPIC_MAP_CSV = DATA_DIR / "topic_map.csv"      # which slides belong to which topic
QUESTION_BANK_CSV = DATA_DIR / "question_bank.csv"
LABELED_CSV = DATA_DIR / "questions_labeled.csv"
SEARCH_TEST_CSV = DATA_DIR / "search_test.csv"
OFFTOPIC_CSV = DATA_DIR / "offtopic_test.csv"
ARABIC_GLOSSARY_CSV = DATA_DIR / "arabic_glossary.csv"

MODELS_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "static" / "reports"   # metrics.json + confusion matrix images
LOGS_XLSX = BASE_DIR / "logs.xlsx"

# Search: if the best cosine score is below this value the app answers "Not found in the course".
# evaluate.py tunes it on the search test + off-topic sets and stores the chosen value in models/.
DEFAULT_NOT_FOUND_THRESHOLD = 0.12
TOP_K = 3

# Mastery colours
RED_BELOW = 0.40
GREEN_FROM = 0.70

# Lecturer pages (Admin + Dashboard). Change before a real deployment.
import os
LECTURER_PASSWORD = os.environ.get("LECTURER_PASSWORD", "lecturer123")
MAX_COURSES_PER_DOCTOR = 10                       # keeps the free hosting disk from filling up
SECRET_KEY = os.environ.get("SECRET_KEY", "studymate-dev-key-change-me")

RANDOM_STATE = 42

# Interface theme: teal | midnight | notebook | indigo | benha   (preview any page with ?theme=name)
THEME = "edu"
THEMES = ["edu", "teal", "midnight", "notebook", "indigo", "benha"]


# ---------------------------------------------------------------- multi-course support
import json
from types import SimpleNamespace

DEFAULT_COURSE = COURSE_CODE


def course_paths(code=None):
    """All file locations of one course. The original course (AI) keeps its old places (models/, static/reports/)."""
    code = code or DEFAULT_COURSE
    d = BASE_DIR / "data" / code
    default = code == DEFAULT_COURSE
    return SimpleNamespace(
        code=code, data=d, lectures=d / "lectures", passages=d / "passages.csv", topics=d / "topics.csv",
        topic_map=d / "topic_map.csv", bank=d / "question_bank.csv", labeled=d / "questions_labeled.csv",
        search_test=d / "search_test.csv", offtopic=d / "offtopic_test.csv", glossary=d / "arabic_glossary.csv",
        info=d / "course.json", models=MODELS_DIR if default else MODELS_DIR / code,
        reports=REPORTS_DIR if default else REPORTS_DIR / code,
        reports_url="reports" if default else f"reports/{code}")


_counts = {}


def _counts_of(folder):
    """(lectures, slides) of a course, cached until its passages.csv changes."""
    f = folder / "passages.csv"
    key = (str(f), f.stat().st_mtime)
    if key not in _counts:
        import pandas as pd
        p = pd.read_csv(f, usecols=["lecture"])
        _counts[key] = (int(p.lecture.nunique()), len(p))
    return _counts[key]


def list_courses():
    """[{code, name_en, name_ar, full, lectures, slides, meta}] for every data/<CODE>/ with course.json + passages."""
    out = []
    for info in sorted((BASE_DIR / "data").glob("*/course.json")):
        try:
            meta = json.loads(info.read_text(encoding="utf-8"))
        except Exception:
            continue
        code = info.parent.name
        if (info.parent / "passages.csv").exists():
            lec, sl = _counts_of(info.parent)
            out.append({"code": code, "name_en": meta.get("name_en", code), "name_ar": meta.get("name_ar", ""),
                        "full": meta.get("full", True), "lectures": lec, "slides": sl, "meta": meta})
    return out


def default_course():
    """The course shown when none is picked: the original one if it still exists, else the first course, else ''."""
    codes = [c["code"] for c in list_courses()]
    return DEFAULT_COURSE if DEFAULT_COURSE in codes else (codes[0] if codes else "")
