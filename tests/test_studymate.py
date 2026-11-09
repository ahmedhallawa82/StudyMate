"""Automatic tests. Run from the project folder:  python -m pytest -q"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

import config
from core import mastery as M
from core.text import clean_slide_text
from core.logger import log_to_excel, read_sheet


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    config.LOGS_XLSX = tmp_path_factory.mktemp("logs") / "logs.xlsx"   # never touch the real logs
    import app as A
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.post("/start", data={"code": "TEST1"})
    return c


@pytest.fixture()
def admin(client):
    """A separate browser session logged in as Admin (the student `client` stays a student)."""
    import app as A
    c = A.app.test_client()
    c.post("/lecturer", data={"password": config.LECTURER_PASSWORD})
    return c


# ---------------- data requirements from the project sheet
def test_dataset_sizes():
    labelled = pd.read_csv(config.LABELED_CSV)
    bank = pd.read_csv(config.QUESTION_BANK_CSV)
    assert len(labelled) >= 300
    assert bank.topic.nunique() >= 8 and bank.groupby("topic").size().min() >= 5
    assert len(pd.read_csv(config.SEARCH_TEST_CSV)) == 30
    assert len(pd.read_csv(config.OFFTOPIC_CSV)) == 10


def test_test_sets_not_in_training():
    labelled = set(pd.read_csv(config.LABELED_CSV).question.str.lower())
    for f in (config.SEARCH_TEST_CSV, config.OFFTOPIC_CSV):
        assert not labelled & set(pd.read_csv(f).question.str.lower())


def test_every_passage_has_lecture_slide_topic():
    p = pd.read_csv(config.PASSAGES_CSV)
    assert len(p) > 100 and p[["lecture", "slide", "topic", "text"]].notna().all().all()


# ---------------- helpers
def test_clean_text_fixes_symbols_and_glued_words():
    assert "Alpha-Beta Pruning" in clean_slide_text(" - Pruning")
    assert "Bayes network" in clean_slide_text("Bayesnetwork is a graph")


def test_mastery_update_and_colours():
    assert M.update(0.0, True, 0) > M.update(0.0, True, 2) > M.update(0.0, False, 0) == 0.0
    assert M.colour(0.1) == "red" and M.colour(0.5) == "amber" and M.colour(0.9) == "green"


def test_log_to_excel_append_and_update(tmp_path):
    path = tmp_path / "logs.xlsx"
    rid = log_to_excel("Questions", {"student_code": "S9", "question": "q"}, path=path)
    log_to_excel("Questions", {"helpful": "yes"}, update_id=rid, path=path)
    rows = read_sheet("Questions", path=path)
    assert rows[0]["helpful"] == "yes" and rows[0]["student_code"] == "S9"


# ---------------- app behaviour
def test_ask_returns_three_sources(client):
    r = client.get("/ask", query_string={"q": "What is an admissible heuristic?"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and html.count("Lecture 4 · Slide") == 3


def test_off_topic_returns_not_found(client):
    r = client.get("/ask", query_string={"q": "who won the last football world cup"})
    assert "Not found in the course" in r.get_data(as_text=True)


def test_arabic_question(client):
    r = client.get("/ask", query_string={"q": "ايه هو البحث بالعرض"})
    assert "Lecture 3 · Slide" in r.get_data(as_text=True)


def test_practice_flow_logs_answer(client):
    client.get("/practice", query_string={"topic": "minimax"})
    client.post("/practice", data={"action": "hint"})
    client.post("/practice", data={"action": "reveal"})
    r = client.post("/practice", data={"action": "right"}, follow_redirects=True)
    assert "Mastery" in r.get_data(as_text=True)
    assert read_sheet("Answers")[-1]["hints_used"] == 1


@pytest.mark.parametrize("page", ["/progress"])
def test_pages_open(client, page):
    assert client.get(page).status_code == 200


def test_admin_pages(client, admin):
    assert client.get("/dashboard").status_code == 302          # needs the admin password
    assert client.get("/evaluation").status_code == 302         # evaluation is for the admin only
    assert admin.get("/dashboard").status_code == 200
    assert admin.get("/admin").status_code == 200
    assert admin.get("/evaluation").status_code == 200
    assert admin.get("/dashboard/logs.xlsx").status_code == 200


def test_admin_and_student_areas_are_separate():
    import app as A
    c = A.app.test_client()
    c.post("/start", data={"code": "SEP1"})
    c.post("/lecturer", data={"password": config.LECTURER_PASSWORD})
    # inside Admin: no student pages, no student navigation, not signed in as a student any more
    for page in ("/ask", "/practice", "/progress", "/start"):
        r = c.get(page)
        assert r.status_code == 302 and "/dashboard" in r.headers["Location"]
    html = c.get("/dashboard").get_data(as_text=True)
    assert "/practice" not in html and "/progress" not in html and "SEP1" not in html and "/evaluation" in html
    # leaving Admin brings back the student side (needs a new sign-in)
    r = c.get("/lecturer/logout")
    assert "/start" in r.headers["Location"]
    assert c.get("/ask").status_code == 302
    assert c.post("/start", data={"code": "SEP1"}).status_code == 302
    assert c.get("/ask").status_code == 200


# ---------------- language, dark mode, courses
def test_arabic_interface_is_rtl_and_translated(client):
    html = client.get("/ask", query_string={"lang": "ar"}).get_data(as_text=True)
    assert 'dir="rtl"' in html and "اسأل" in html and "تدرّب" in html
    html = client.get("/ask", query_string={"lang": "en"}).get_data(as_text=True)
    assert 'dir="ltr"' in html and "Practice" in html


def test_dark_mode_assets_and_toggle(client):
    html = client.get("/ask").get_data(as_text=True)
    assert "dark.css" in html and 'id="modeBtn"' in html
    assert client.get("/static/css/dark.css").status_code == 200


def test_all_texts_have_both_languages():
    from core.i18n import T
    assert all(en and ar for en, ar in T.values())


def test_add_course_from_pdfs(client, admin):
    import io, shutil
    src = config.LECTURES_DIR
    pdfs = [(src / "lecture 2 Intelligent Agents.pdf"), (src / "lecture 4 Informed Search.pdf")]
    data = {"action": "add_course", "code": "tst9", "name_en": "Test Course", "name_ar": "مادة",
            "pdfs": [(io.BytesIO(p.read_bytes()), p.name) for p in pdfs]}
    try:
        admin.post("/admin", data=data, content_type="multipart/form-data")
        assert "TST9" in [c["code"] for c in config.list_courses()]
        client.get("/course/TST9")
        r = client.get("/ask", query_string={"q": "what is a model-based reflex agent"})
        assert r.status_code == 200 and "Lecture 2 · Slide" in r.get_data(as_text=True)
        assert client.get("/practice").status_code == 200 and admin.get("/evaluation").status_code == 200
        # progress of the new course is separate from the first course
        assert client.get("/progress").status_code == 200
    finally:
        shutil.rmtree(config.BASE_DIR / "data" / "TST9", ignore_errors=True)
        shutil.rmtree(config.BASE_DIR / "models" / "TST9", ignore_errors=True)
        client.get("/course/AI")


def test_guest_login_and_no_evaluation_link_for_students():
    import app as A
    c = A.app.test_client()
    r = c.post("/start", data={"guest": "1", "code": ""}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "GUEST-" in html and "/evaluation" not in html


def test_second_course_search_and_arabic(client):
    r = client.get("/course/MAM336")
    r = client.get("/ask", query_string={"q": "what does a clutch do"})
    assert "Lecture 3 · Slide" in r.get_data(as_text=True)
    r = client.get("/ask", query_string={"q": "who won the world cup"})
    assert "Not found in the course" in r.get_data(as_text=True)
    r = client.get("/ask", query_string={"q": "ايه هو محول العزم"})
    assert "Lecture 5 · Slide" in r.get_data(as_text=True)
    client.get("/course/AI")


def test_delete_lecture_and_course_from_admin(admin):
    import io, shutil
    src = config.LECTURES_DIR
    pdfs = [src / "lecture 2 Intelligent Agents.pdf", src / "lecture 4 Informed Search.pdf"]
    data = {"action": "add_course", "code": "del9", "name_en": "Delete me", "name_ar": "",
            "pdfs": [(io.BytesIO(p.read_bytes()), p.name) for p in pdfs]}
    try:
        admin.post("/admin", data=data, content_type="multipart/form-data")
        assert "DEL9" in [c["code"] for c in config.list_courses()]
        admin.post("/admin", data={"action": "delete_lecture", "lecture": "2"})
        left = list((config.BASE_DIR / "data" / "DEL9" / "lectures").glob("*.pdf"))
        assert len(left) == 1 and "Informed" in left[0].name
        admin.post("/admin", data={"action": "delete_lecture", "lecture": "4"})      # last lecture: refused
        assert len(list((config.BASE_DIR / "data" / "DEL9" / "lectures").glob("*.pdf"))) == 1
        admin.post("/admin", data={"action": "delete_course", "confirm": "wrong"})
        assert (config.BASE_DIR / "data" / "DEL9").exists()
        admin.post("/admin", data={"action": "delete_course", "confirm": "DEL9"})
        assert not (config.BASE_DIR / "data" / "DEL9").exists()
        admin.post("/admin", data={"action": "delete_course", "confirm": "AI"})      # first course is protected
        assert (config.BASE_DIR / "data" / "AI").exists()
    finally:
        shutil.rmtree(config.BASE_DIR / "data" / "DEL9", ignore_errors=True)
        shutil.rmtree(config.BASE_DIR / "models" / "DEL9", ignore_errors=True)
        admin.get("/course/AI")


def test_upload_several_lectures_at_once(admin):
    import io, shutil
    src = config.LECTURES_DIR
    pdfs = [src / "lecture 2 Intelligent Agents.pdf", src / "lecture 4 Informed Search.pdf", src / "lecture 5 Adversarial Search.pdf"]
    mk = {"action": "add_course", "code": "mul9", "name_en": "Multi", "name_ar": "",
          "pdfs": [(io.BytesIO(pdfs[0].read_bytes()), pdfs[0].name)]}
    try:
        admin.post("/admin", data=mk, content_type="multipart/form-data")
        admin.post("/admin", data={"action": "upload",
                    "pdf": [(io.BytesIO(p.read_bytes()), p.name) for p in pdfs[1:]]}, content_type="multipart/form-data")
        names = sorted(f.name for f in (config.BASE_DIR / "data" / "MUL9" / "lectures").glob("*.pdf"))
        assert len(names) == 3 and any(n.startswith("lecture 5") for n in names)
        assert len(__import__("pandas").read_csv(config.BASE_DIR / "data" / "MUL9" / "passages.csv").lecture.unique()) == 3
    finally:
        shutil.rmtree(config.BASE_DIR / "data" / "MUL9", ignore_errors=True)
        shutil.rmtree(config.BASE_DIR / "models" / "MUL9", ignore_errors=True)
        admin.get("/course/AI")
