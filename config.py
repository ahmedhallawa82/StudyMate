"""Central settings for StudyMate (Project 1E - Course Study Assistant)."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

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
SECRET_KEY = os.environ.get("SECRET_KEY", "studymate-dev-key-change-me")

RANDOM_STATE = 42

# Interface theme: teal | midnight | notebook | indigo | benha   (preview any page with ?theme=name)
THEME = "indigo"
THEMES = ["teal", "midnight", "notebook", "indigo", "benha"]
