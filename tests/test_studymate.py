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


@pytest.fixture(autouse=True, scope="module")
def _students_file(tmp_path_factory):
    """Student accounts of the tests live in a temp folder, never in data/students.json."""
    from core import students
    from core import notify, schedule, profiles, support, badges, catalog, custom_badges, adminpw, chat
    d = tmp_path_factory.mktemp("stu")
    f = d / "students.json"
    students.FILE = lambda: f
    notify.FILE = lambda: d / "notifications.json"
    schedule.FILE = lambda: d / "schedule.json"
    profiles.FILE = lambda: d / "profiles.json"
    profiles.DIR = lambda: d / "avatars"
    support.FILE = lambda: d / "support.json"
    badges.FILE = lambda: d / "badges.json"
    custom_badges.FILE = lambda: d / "custom_badges.json"
    adminpw.FILE = lambda: d / "admin_auth.json"
    chat.FILE = lambda: d / "chat.json"
    catalog.FILE = lambda: d / "course_codes.json"


def as_student(c, name):
    """Register (or sign in) a test student and leave the client signed in."""
    r = c.post("/register", data={"first": name, "last": "Test", "email": f"{name.lower()}@test.com",
                                  "password": "secret1", "confirm": "secret1"})
    if "Location" not in r.headers or "/register" in r.headers.get("Location", ""):
        c.post("/start", data={"username": f"{name.lower()}@test.com", "password": "secret1"})
    c.post("/my-courses", data={"course": [config.DEFAULT_COURSE]})


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    config.LOGS_XLSX = tmp_path_factory.mktemp("logs") / "logs.xlsx"   # never touch the real logs
    import app as A
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    as_student(c, "TEST1")
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
    as_student(c, "SEP1")
    c.post("/lecturer", data={"password": config.LECTURER_PASSWORD})
    # inside Admin: no student pages, no student navigation, not signed in as a student any more
    for page in ("/ask", "/practice", "/progress", "/start"):
        r = c.get(page)
        assert r.status_code == 302 and "/overview" in r.headers["Location"]
    html = c.get("/dashboard").get_data(as_text=True)
    assert "/practice" not in html and "/progress" not in html and "/evaluation" in html
    # leaving Admin brings back the student side (needs a new sign-in)
    r = c.get("/lecturer/logout")
    assert "/start" in r.headers["Location"]
    assert c.get("/ask").status_code == 302
    assert c.post("/start", data={"username": "sep1@test.com", "password": "secret1"}).status_code == 302
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
    client.post("/my-courses", data={"course": ["AI", "MAM336"]})        # the student registers in both courses
    r = client.get("/course/MAM336")
    r = client.get("/ask", query_string={"q": "what does a clutch do"})
    assert "Lecture 3 · Slide" in r.get_data(as_text=True)
    r = client.get("/ask", query_string={"q": "who won the world cup"})
    assert "Not found in the course" in r.get_data(as_text=True)
    r = client.get("/ask", query_string={"q": "ايه هو محول العزم"})
    assert "Lecture 5 · Slide" in r.get_data(as_text=True)
    client.get("/course/AI")
    client.post("/my-courses", data={"course": ["AI"]})


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
        admin.post("/admin", data={"action": "delete_course", "confirm": "wrong"})
        assert (config.BASE_DIR / "data" / "DEL9").exists()
        admin.post("/admin", data={"action": "delete_course", "confirm": "DEL9"})
        assert not (config.BASE_DIR / "data" / "DEL9").exists()
    finally:
        shutil.rmtree(config.BASE_DIR / "data" / "DEL9", ignore_errors=True)
        shutil.rmtree(config.BASE_DIR / "models" / "DEL9", ignore_errors=True)
        admin.get("/course/AI")


def test_delete_several_lectures_at_once(admin):
    import io, shutil
    src = config.LECTURES_DIR
    pdfs = [src / "lecture 2 Intelligent Agents.pdf", src / "lecture 4 Informed Search.pdf", src / "lecture 5 Adversarial Search.pdf"]
    data = {"action": "add_course", "code": "del8", "name_en": "Bulk", "name_ar": "",
            "pdfs": [(io.BytesIO(p.read_bytes()), p.name) for p in pdfs]}
    folder = config.BASE_DIR / "data" / "DEL8" / "lectures"
    try:
        admin.post("/admin", data=data, content_type="multipart/form-data")
        assert len(list(folder.glob("*.pdf"))) == 3
        admin.post("/admin", data={"action": "delete_lecture", "lecture": ["2", "4"]})
        left = list(folder.glob("*.pdf"))
        assert len(left) == 1 and "Adversarial" in left[0].name
        admin.post("/admin", data={"action": "delete_lecture", "lecture": ["5"]})     # every lecture selected -> whole course content goes
        assert not (config.BASE_DIR / "data" / "DEL8").exists()
    finally:
        shutil.rmtree(config.BASE_DIR / "data" / "DEL8", ignore_errors=True)
        shutil.rmtree(config.BASE_DIR / "models" / "DEL8", ignore_errors=True)
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


# ---------------- doctors: private codes, own courses only
def test_doctor_codes_own_courses_and_search(admin, tmp_path, monkeypatch):
    import io, shutil
    import app as A
    from core import doctors
    monkeypatch.setattr(doctors, "FILE", lambda: tmp_path / "doctors.json")
    did, code = doctors.add("Dr Test")
    did2, code2 = doctors.add("Dr Other")
    assert doctors.check(code.lower()) == did and doctors.check(did + "-WRONGWRONG") is None
    assert "hash" not in str(doctors.list_doctors())

    def login(c):
        return A.app.test_client(), c
    d1, d2 = A.app.test_client(), A.app.test_client()
    bad = A.app.test_client()
    bad.post("/lecturer", data={"password": did + "-NOPE2345"})
    assert bad.get("/dashboard").status_code == 302                      # wrong code: not admitted
    d1.post("/lecturer", data={"password": code})
    d2.post("/lecturer", data={"password": code2})
    html = d1.get("/admin").get_data(as_text=True)
    assert "Dr. Dr Test" in html and "Add a course" in html or "Dr Test" in html
    assert d1.get("/dashboard").status_code == 302                       # no course yet -> sent to Admin
    src = config.LECTURES_DIR
    pdfs = [src / "lecture 2 Intelligent Agents.pdf", src / "lecture 4 Informed Search.pdf"]
    try:
        d1.post("/admin", data={"action": "add_course", "code": "dct9", "name_en": "Doctor course", "name_ar": "",
                "pdfs": [(io.BytesIO(p.read_bytes()), p.name) for p in pdfs]}, content_type="multipart/form-data")
        assert next(c for c in config.list_courses() if c["code"] == "DCT9")["meta"]["owner"] == did
        assert d1.get("/dashboard").status_code == 200 and d1.get("/evaluation").status_code == 302   # evaluation: main admin only
        assert d1.get("/dashboard/logs.xlsx").status_code == 200
        # he sees only his own course (not AI / MAM336) in the course list
        page = d1.get("/admin").get_data(as_text=True)
        assert "DCT9" in page and "MAM336" not in page and "Doctors" not in page
        # another doctor can neither edit nor delete it, and cannot make doctors
        d2.post("/admin", data={"action": "delete_course", "confirm": "DCT9"})
        d2.post("/admin", data={"action": "add_doctor", "doctor_name": "Hacker"})
        assert (config.BASE_DIR / "data" / "DCT9").exists() and len(doctors.list_doctors()) == 2
        # the main admin sees everything and can manage doctors
        assert "Doctors" in admin.get("/admin").get_data(as_text=True)
        admin.post("/admin", data={"action": "delete_doctor", "doctor": did2})
        assert len(doctors.list_doctors()) == 1
        # a student sees only the courses he registered in (live-search list) and has no Admin link
        s = A.app.test_client(); as_student(s, "SRCH1")
        html = s.get("/ask").get_data(as_text=True)
        assert "DCT9" not in html and 'href="/admin"' not in html
        s.post("/my-courses", data={"course": [config.DEFAULT_COURSE, "DCT9"]})
        html = s.get("/ask").get_data(as_text=True)
        html = s.get("/home").get_data(as_text=True)
        assert 'id="courseCombo"' not in html and "course-chips" in html and "DCT9" in html
        # each doctor sees the student only in his own course, the main admin in both
        p1 = d1.get("/students").get_data(as_text=True)
        assert "srch1@test.com" in p1 and "Doctor course" in p1 and "Artificial Intelligence" not in p1
        assert "srch1@test.com" not in d2.get("/students").get_data(as_text=True)
        pa = admin.get("/students").get_data(as_text=True)
        assert "srch1@test.com" in pa and "Doctor course" in pa and "Artificial Intelligence" in pa
        csv1 = d1.get("/students.csv").get_data(as_text=True)
        assert "srch1@test.com" in csv1 and "DCT9" in csv1 and ",AI," not in csv1 and "doctor" not in csv1.splitlines()[0]
        assert "doctor" in admin.get("/students.csv").get_data(as_text=True).splitlines()[0]
    finally:
        shutil.rmtree(config.BASE_DIR / "data" / "DCT9", ignore_errors=True)
        shutil.rmtree(config.BASE_DIR / "models" / "DCT9", ignore_errors=True)


def test_doctor_changes_password_and_sheet_rows(admin, tmp_path, monkeypatch):
    import app as A
    from core import doctors, sheet_sync
    monkeypatch.setattr(doctors, "FILE", lambda: tmp_path / "doctors.json")
    pushed = []
    monkeypatch.setattr(sheet_sync, "push", lambda rows, wait=False: pushed.append(rows))
    monkeypatch.setattr(sheet_sync, "enabled", lambda: True)
    admin.post("/admin", data={"action": "add_doctor", "doctor_name": "Dr Sheet"})
    did = doctors.list_doctors()[0]["id"]
    first = pushed[-1][0]
    assert first[0] == "Dr Sheet" and first[4].startswith(did + "-") and first[5] == ""
    # the admin page shows the doctors sheet; a doctor never sees it
    assert "Doctors sheet" in admin.get("/admin").get_data(as_text=True)
    d = A.app.test_client()
    d.post("/lecturer", data={"password": first[4]})
    page = d.get("/admin").get_data(as_text=True)
    assert "Doctors sheet" not in page and "Change my password" not in page      # the password lives in the profile page
    d.post("/admin", data={"action": "change_password", "old": "wrong", "new": "MyNewPass9", "confirm": "MyNewPass9"})
    assert pushed[-1][0][5] == ""                                   # wrong old password: nothing changed
    d.post("/admin", data={"action": "change_password", "old": first[4], "new": "short", "confirm": "short"})
    assert pushed[-1][0][5] == ""
    d.post("/admin", data={"action": "change_password", "old": first[4], "new": "MyNewPass9", "confirm": "MyNewPass9"})
    assert pushed[-1][0][5] == "MyNewPass9" and pushed[-1][0][4] == first[4]
    # new password works, the system one no longer does
    assert doctors.check("MyNewPass9") == did and doctors.check(first[4]) is None
    n = A.app.test_client(); n.post("/lecturer", data={"password": "MyNewPass9"})
    assert n.get("/admin").status_code == 200 and "Change password" in n.get("/profile").get_data(as_text=True)
    # the admin makes a new password -> the doctor's own one is cleared
    admin.post("/admin", data={"action": "reset_doctor", "doctor": did})
    assert pushed[-1][0][5] == "" and doctors.check("MyNewPass9") is None


# ---------------- accounts: register, sign in with username/password, remember me, doctor username
def test_register_login_and_students_sheet(tmp_path):
    import app as A
    from core import students
    c = A.app.test_client()
    bad = c.post("/register", data={"first": "A", "last": "B", "email": "nope", "password": "secret1", "confirm": "secret1"})
    assert bad.status_code == 200 and "Location" not in bad.headers
    ok = c.post("/register", data={"first": "Sara", "last": "Ali", "email": "Sara@Mail.com", "password": "secret1", "confirm": "secret1"})
    assert ok.status_code == 302
    dup = c.post("/register", data={"first": "S", "last": "A", "email": "sara@mail.com", "password": "secret1", "confirm": "secret1"})
    assert dup.status_code == 200
    s = students.find("sara@mail.com")
    assert s["first"] == "Sara" and "secret1" not in json_text(students.FILE())          # only a hash is stored
    rows = read_sheet("Students")
    assert rows[-1]["email"] == "sara@mail.com" and "password" not in rows[-1]
    c2 = A.app.test_client()
    assert c2.post("/start", data={"username": "sara@mail.com", "password": "wrong"}).status_code == 200
    r = c2.post("/start", data={"username": "sara@mail.com", "password": "secret1", "remember": "1"})
    assert r.status_code == 302 and "/home" in r.headers["Location"]
    assert "Expires" in r.headers.get("Set-Cookie", "")                                   # remember me -> long cookie


def json_text(path):
    return path.read_text(encoding="utf-8")


def test_admin_and_doctor_username_login(admin, tmp_path, monkeypatch):
    import app as A
    from core import doctors
    monkeypatch.setattr(doctors, "FILE", lambda: tmp_path / "doctors.json")
    a = A.app.test_client()
    assert a.post("/start", data={"username": "admin", "password": "nope"}).status_code == 200
    assert "/overview" in a.post("/start", data={"username": "admin", "password": config.LECTURER_PASSWORD}).headers["Location"]
    admin.post("/admin", data={"action": "add_doctor", "doctor_name": "Dr Mail", "doctor_email": "dr@x.com"})
    d = doctors.list_doctors()[0]
    assert d["email"] == "dr@x.com" and d["username"].startswith("dr")
    pw = doctors._load()[0]["initial"]
    other = A.app.test_client()
    assert other.post("/start", data={"username": "dr-wrong", "password": pw}).status_code == 200   # username must match
    doc = A.app.test_client()
    assert "/overview" in doc.post("/start", data={"username": d["username"], "password": pw}).headers["Location"]
    page = doc.get("/admin").get_data(as_text=True)
    assert "Doctor" in page and "Dr Mail" in page                                        # role chip shows who is signed in
    assert "Admin" in admin.get("/admin").get_data(as_text=True)
    # exports are for the main admin only
    assert admin.get("/admin/doctors.csv").status_code == 200 and "dr@x.com" in admin.get("/admin/doctors.csv").get_data(as_text=True)
    assert admin.get("/admin/doctors.xlsx").status_code == 200
    assert doc.get("/admin/doctors.csv").status_code == 302


def test_materials_zip(client):
    r = client.get("/materials.zip")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    assert client.get("/materials").status_code == 200


# ---------------- exams
EXAM_TEXT = """Q1. What does PEAS stand for?
A) Performance, Environment, Actuators, Sensors
B) Planning
C) Policy
D) None
Answer: A
Q2. Explain A* search.
Answer: uses f(n)=g(n)+h(n)
Keywords: f(n); g(n); admissible
س1. ماذا تعني PEAS؟
أ) الأداء والبيئة
ب) التخطيط
ج) السياسة
د) لا شيء
الإجابة: أ
"""


def test_exam_parser_pairs_languages():
    from core import exams as EX
    items = EX.parse_text(EXAM_TEXT)
    assert [(i["n"], i["lang"], i["type"]) for i in items] == [(1, "en", "mcq"), (2, "en", "essay"), (1, "ar", "mcq")]
    assert items[0]["answer"] == 0 and items[2]["answer"] == 0 and items[1]["keywords"] == ["f(n)", "g(n)", "admissible"]


def test_exam_flow(admin, tmp_path, monkeypatch):
    import io
    import app as A
    from core import exams as EX
    monkeypatch.setattr(EX, "folder", lambda code: tmp_path / code / "exams")
    up = {"action": "upload_qa", "files": (io.BytesIO(EXAM_TEXT.encode("utf-8")), "bank.txt")}
    admin.post("/exams/manage", data=up, content_type="multipart/form-data")
    sm = EX.summary(config.DEFAULT_COURSE)
    assert sm["total"] == 2 and sm["en"] == 2 and sm["ar"] == 1 and sm["graded"] == 2
    # questions only: a new question without answers is stored but cannot be used in an exam
    admin.post("/exams/manage", data={"action": "upload_q", "files": (io.BytesIO(b"Q3. Define agent.\n"), "q.txt")}, content_type="multipart/form-data")
    assert EX.summary(config.DEFAULT_COURSE)["total"] == 3 and len(EX.eligible(config.DEFAULT_COURSE)) == 2
    s = A.app.test_client(); as_student(s, "EXAM1")
    assert s.get("/exams").status_code == 200
    assert s.post("/exams/start", data={"count": "2"}).status_code == 302
    page = s.get("/exams/take?lang=ar").get_data(as_text=True)
    assert "Answer:" not in page and "examForm" in page                                  # no answers while taking the exam
    att = EX.active_attempt(config.DEFAULT_COURSE, "S0001") or EX.list_attempts(config.DEFAULT_COURSE)[0]
    form = {}
    for k in att["qids"]:
        form[f"q_{k}"] = "0" if EX.load_bank(config.DEFAULT_COURSE)["questions"][k]["type"] == "mcq" else "it uses f(n) g(n) and an admissible heuristic"
    r = s.post("/exams/submit", data=form)
    assert r.status_code == 302 and "/exams/result/" in r.headers["Location"]
    res = s.get(r.headers["Location"]).get_data(as_text=True)
    assert "2 / 2" in res and "100%" in res
    assert read_sheet("Exams")[-1]["score_pct"] == 100
    # the doctor sees the attempt and can change an essay mark
    assert att["id"] in admin.get("/exams/manage").get_data(as_text=True)
    done = EX.load_attempt(config.DEFAULT_COURSE, att["id"])
    essay = next((d for d in done["details"] if d["type"] == "essay"), None)
    if essay:
        admin.post(f"/exams/attempt/{att['id']}", data={"qid": essay["id"], "score": "0"})
        assert EX.load_attempt(config.DEFAULT_COURSE, att["id"])["score"] < 2
    # another student cannot open this result
    o = A.app.test_client(); as_student(o, "EXAM2")
    assert o.get(f"/exams/result/{att['id']}").headers["Location"].endswith("/exams")


def test_exam_pdf_noise_and_answer_key():
    from core import exams as EX
    text = "\n".join(["Lecture 1: Intro", "Q1.", "What is a car?", "a) x", "b) y", "c) z", "d) w", "Page 1 / 36",
                      "Automotive Engineering — Question Bank", "Essay Questions", "Q2.", "Explain yaw.", "Lecture 2: Dynamics"])
    items = EX.parse_text(text)
    assert [i["type"] for i in items] == ["mcq", "essay"]
    assert items[0]["options"][-1] == "w" and items[1]["q"] == "Explain yaw."          # headers/footers do not stick to questions
    assert EX.parse_key("1-A 2-C 3-B\n4. d\nQ5. B\n") == {1: 0, 2: 2, 3: 1, 4: 3, 5: 1}
    assert EX.parse_key("Q1. What is a car?\na) x") == {}


def test_student_home_and_login_landing():
    import app as A
    c = A.app.test_client()
    r = c.post("/register", data={"first": "Mona", "last": "K", "email": "mona@test.com", "password": "secret1", "confirm": "secret1"})
    assert r.headers["Location"].endswith("/my-courses")
    c.post("/my-courses", data={"course": ["AI"]})
    page = c.get("/home").get_data(as_text=True)
    assert "Mona" in page and "hero" in page and "Continue learning" in page
    ar = c.get("/home?lang=ar").get_data(as_text=True)
    assert "الرئيسية" in ar and "Mona" in ar


def test_essay_similarity_grading(tmp_path, monkeypatch):
    from core import exams as EX
    monkeypatch.setattr(EX, "folder", lambda code: tmp_path / code / "exams")
    EX.add_items("T", [{"n": 1, "lang": "en", "type": "essay", "q": "Explain A* search.", "options": [], "answer": None,
                        "model": "A* search expands the node with the lowest f(n) = g(n) + h(n), using an admissible heuristic so the path is optimal.", "keywords": []}], True)
    b = EX.load_bank("T")
    q, st = b["questions"]["1"], b["settings"]
    assert EX._grade_essay("T", "A* picks the node with smallest f = g + h and an admissible heuristic gives the optimal path", q, st)[0] == 1.0
    assert EX._grade_essay("T", "It is a sorting algorithm for arrays", q, st)[0] == 0.0
    assert EX._grade_essay("T", "", q, st)[0] == 0.0


def test_staff_home_admin_and_doctor(admin):
    from core import doctors
    import app as A
    r = admin.get("/overview")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "per-course" in html and "👨‍🏫" in html          # admin: doctors / students / traffic / courses
    assert admin.get("/", headers={"Sec-Fetch-Site": "same-origin"}).headers["Location"].endswith("/overview")
    did, code = doctors.add("Dr Home")
    try:
        d = A.app.test_client()
        d.post("/lecturer", data={"username": doctors.username_of(doctors.get(did)), "password": code})
        h = d.get("/overview").get_data(as_text=True)
        assert "per-course" in h and "👨‍🏫" not in h and "Dr Home" in h               # doctor: his courses / students / exams / questions
    finally:
        doctors.remove(did)


def test_overview_pages_and_card_order(admin):
    html = admin.get("/overview").get_data(as_text=True)
    assert html.index("Total site visits") < html.index("Doctors registered") < html.index("Students with an account") < html.index("Courses on the site")
    assert 'href="/doctors"' in html and 'href="/all-courses"' in html
    assert admin.get("/doctors").status_code == 200
    r = admin.get("/all-courses")
    assert r.status_code == 200 and "MAM336" in r.get_data(as_text=True)


def test_profile_photo_name_and_password(client):
    import io
    from PIL import Image
    as_student(client, "PROF1")
    assert 'href="/profile"' in client.get("/home").get_data(as_text=True)
    assert client.get("/profile").status_code == 200
    client.post("/profile", data={"action": "info", "first": "Newname", "last": "Last", "email": "newprof1@test.com"})
    assert "Newname" in client.get("/profile").get_data(as_text=True)
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (10, 120, 120)).save(buf, "PNG")
    buf.seek(0)
    client.post("/profile", data={"action": "photo", "photo": (buf, "me.png")}, content_type="multipart/form-data")
    html = client.get("/profile").get_data(as_text=True)
    assert "/avatar/s_" in html
    src = html.split('/avatar/')[1].split('"')[0].split("?")[0]
    assert client.get("/avatar/" + src).mimetype == "image/jpeg"
    bad = client.post("/profile", data={"action": "photo", "photo": (io.BytesIO(b"not an image"), "x.png")}, content_type="multipart/form-data", follow_redirects=True)
    assert "not a valid image" in bad.get_data(as_text=True)
    client.post("/profile", data={"action": "password", "old": "wrong", "new": "abcdef", "confirm": "abcdef"})
    client.post("/profile", data={"action": "password", "old": "secret1", "new": "abcdef12", "confirm": "abcdef12"})
    client.get("/logout")
    r = client.post("/start", data={"username": "newprof1@test.com", "password": "abcdef12"})
    assert r.status_code == 302 and "/start" not in r.headers["Location"]


def test_notifications_and_calendar(admin, client):
    from core import schedule
    as_student(client, "CAL1")
    ev = admin.get("/overview").get_data(as_text=True)
    assert "CAL1 Test" in ev                                                 # the admin's bell shows the new student
    assert admin.get("/notifications").status_code == 200
    assert admin.post("/calendar", data={"action": "add", "course": "AI", "title": "Midterm test", "when": "bad"}).status_code == 302
    assert not schedule.for_courses(["AI"])
    admin.post("/calendar", data={"action": "add", "course": "AI", "title": "Midterm test", "when": "2026-12-01T10:00", "note": "Bring ID"})
    items = schedule.for_courses(["AI"])
    assert len(items) == 1
    stu = client.get("/calendar").get_data(as_text=True)
    assert "Midterm test" in stu and "2026-12-01" in stu                     # the student sees it in the calendar
    assert "Midterm test" in client.get("/home").get_data(as_text=True)       # ...and in the bell
    assert "Schedule an exam" not in stu                                     # students cannot schedule
    assert "Schedule an exam" in admin.get("/calendar").get_data(as_text=True)
    client.post("/calendar", data={"action": "delete", "id": items[0]["id"]})
    assert schedule.for_courses(["AI"])                                      # a student cannot delete it
    admin.post("/calendar", data={"action": "delete", "id": items[0]["id"]})
    assert not schedule.for_courses(["AI"])


def test_semantic_and_hybrid_search_keep_the_not_found_gate():
    from core.search import SearchEngine
    eng = SearchEngine.load()
    for m in ("lsa", "hybrid"):
        found, hits = eng.search("What is minimax search?", method=m)
        assert found and hits and hits[0]["score"] > 0
        found, hits = eng.search("how to bake a chocolate cake", method=m)
        assert not found and hits == []


def test_wrong_passwords_popup_lock_and_support_messages():
    import app as A
    c = A.app.test_client()
    html = c.post("/start", data={"username": "nobody1@test.com", "password": "bad"}).get_data(as_text=True)
    assert 'role="alertdialog"' not in html                      # 1st wrong try: only the normal message
    html = c.post("/start", data={"username": "nobody1@test.com", "password": "bad"}).get_data(as_text=True)
    assert 'role="alertdialog"' in html and "contact support" in html.lower()
    for _ in range(2):
        c.post("/start", data={"username": "nobody1@test.com", "password": "bad"})
    html = c.post("/start", data={"username": "nobody1@test.com", "password": "bad"}).get_data(as_text=True)
    html = c.post("/start", data={"username": "nobody1@test.com", "password": "bad"}).get_data(as_text=True)
    assert "No attempts left" in html                    # locked even for the right password later
    ar = A.app.test_client().post("/start?lang=ar", data={"username": "x9@test.com", "password": "b"}, follow_redirects=True)
    assert 'id="supportBtn"' in ar.get_data(as_text=True)
    # send a support message, the admin reads it
    r = c.post("/support", data={"name": "Sara", "contact": "s@x.com", "message": "I cannot sign in"})
    assert r.get_json()["ok"] is True
    admin = A.app.test_client()
    admin.post("/lecturer", data={"username": "admin", "password": config.LECTURER_PASSWORD})
    assert "I cannot sign in" in admin.get("/support-inbox").get_data(as_text=True)


def test_password_generator_rules_and_button():
    import app as A
    from core import passgen
    lens = set()
    for _ in range(300):
        pw = passgen.generate()
        lens.add(len(pw))
        assert passgen.check(pw), pw
    assert min(lens) >= 8 and max(lens) <= 15 and len(lens) > 3
    c = A.app.test_client()
    pw = c.get("/generate-password").get_json()["password"]
    assert passgen.check(pw)
    assert "data-passgen" in c.get("/register").get_data(as_text=True)
    # a generated password is accepted by the registration rules
    r = c.post("/register", data={"first": "Gen", "last": "Pw", "email": "genpw@test.com", "password": pw, "confirm": pw})
    assert r.status_code in (200, 302)


def test_forgot_password_mails_a_strong_password_that_works_at_once(monkeypatch):
    import re
    import app as A
    from core import mailer, passgen
    c = A.app.test_client()
    as_student(c, "Forgetful")                                   # forgetful@test.com / secret1
    sent = []
    monkeypatch.setattr(mailer, "enabled", lambda: True)
    monkeypatch.setattr(mailer, "send_now", lambda to, subj, text, html=None: sent.append((to, subj, text, html)) or True)
    # lock the account first: 5 wrong tries
    k = A.app.test_client()
    for _ in range(5):
        k.post("/start", data={"username": "forgetful@test.com", "password": "nope"})
    assert "No attempts left" in k.post("/start", data={"username": "forgetful@test.com", "password": "secret1"}).get_data(as_text=True)
    r = A.app.test_client().post("/forgot", data={"email": "Forgetful@test.com"})
    assert r.status_code == 200 and len(sent) == 1
    to, subj, text, html = sent[0]
    pw = re.search(r"password: (\S+)|المؤقتة: (\S+)", text)
    pw = next(g for g in pw.groups() if g)
    import html as _h
    assert passgen.check(pw) and _h.escape(pw) in html and "<table" in html and to == "Forgetful@test.com"     # '&' is escaped in HTML
    d = A.app.test_client().post("/start", data={"username": "forgetful@test.com", "password": pw})
    assert d.status_code == 302                                     # the mailed password opens the site at once (even after the lock)
    assert A.app.test_client().post("/start", data={"username": "forgetful@test.com", "password": "secret1"}).status_code == 200  # old one is dead
    # unknown e-mail: same page, nothing is sent
    A.app.test_client().post("/forgot", data={"email": "nobody@test.com"})
    assert len(sent) == 1
    # mail provider fails: the old password keeps working
    monkeypatch.setattr(mailer, "send_now", lambda *a, **k: False)
    A.app.test_client().post("/forgot", data={"email": "forgetful@test.com"})
    assert A.app.test_client().post("/start", data={"username": "forgetful@test.com", "password": pw}).status_code == 302


def test_admin_resets_a_password_from_the_support_inbox_and_it_works_at_once():
    import re
    import app as A
    from core import passgen
    c = A.app.test_client()
    as_student(c, "Locked")                                      # locked@test.com / secret1
    k = A.app.test_client()
    for _ in range(5):
        k.post("/start", data={"username": "locked@test.com", "password": "nope"})
    adm = A.app.test_client()
    adm.post("/lecturer", data={"password": config.LECTURER_PASSWORD})
    A.app.test_client().post("/support", data={"name": "Locked", "contact": "locked@test.com", "message": "forgot it"})
    page = adm.get("/support-inbox").get_data(as_text=True)
    assert 'name="action" value="reset"' in page                 # the message links to a real account
    r = adm.post("/support-inbox", data={"action": "reset", "who": "", "who2": "locked@test.com"})
    html = r.get_data(as_text=True)
    pw = __import__("html").unescape(re.search(r'id="newPw"[^>]*>([^<]+)<', html).group(1))
    assert passgen.check(pw) and r.headers["Cache-Control"] == "no-store"
    assert A.app.test_client().post("/start", data={"username": "locked@test.com", "password": pw}).status_code == 302
    assert A.app.test_client().post("/start", data={"username": "locked@test.com", "password": "secret1"}).status_code == 200
    assert "newPw" not in adm.get("/support-inbox").get_data(as_text=True)      # never stored or shown again
    assert "newPw" not in adm.post("/support-inbox", data={"action": "reset", "who": "ghost@x.com"}).get_data(as_text=True)
    assert A.app.test_client().post("/support-inbox", data={"action": "reset", "who": "locked@test.com"}).status_code == 302  # not an admin


def test_badge_metrics_dates_and_streaks():
    from core import badges
    q = lambda t: {"time": t, "course": "AI"}
    a = lambda t, ok, qid="Q1", lvl=0.2, topic="T1": {"time": t, "course": "AI", "question_id": qid, "correct": ok, "mastery_after": lvl, "topic": topic}
    qs = [q("2026-01-01 09:00:00"), q("2026-01-02 02:30:00"), q("2026-01-03 05:00:00")]
    an = [a("2026-01-03 10:00:00", 0), a("2026-01-03 10:01:00", 1, lvl=0.75), a("2026-01-05 10:00:00", 1, "Q2", 0.8, "T2")]
    ex = [{"time": "2026-01-06 12:00:00", "course": "AI", "score_pct": 95}]
    all_ = {b["id"]: b for b in badges.compute(qs, an, ex, {"AI": ["T1", "T2"]})}
    assert all_["q1"]["earned"] and all_["q1"]["when"] == "2026-01-01" and not all_["q10"]["earned"] and all_["q10"]["value"] == 3
    assert all_["s3"]["earned"] and all_["s3"]["when"] == "2026-01-03" and not all_["s7"]["earned"]      # 1,2,3 Jan in a row
    assert all_["fix"]["earned"] and all_["t1"]["earned"] and not all_["t5"]["earned"]
    assert all_["tall"]["earned"] and all_["tall"]["when"] == "2026-01-05"                                 # every topic of the course went green
    assert all_["e1"]["earned"] and all_["e90"]["earned"] and all_["early"]["earned"] and all_["night"]["earned"]
    assert all_["d10"]["value"] == 5 and all_["d10"]["pct"] == 50 and len(all_) == 25
    assert badges.compute([], [], [], {})[0]["earned"] is False


def test_badges_page_notifies_and_review_mode_fixes_mistakes():
    import app as A
    from core import notify, badges
    c = A.app.test_client()
    as_student(c, "Badger")
    code = next(s["code"] for s in A.students.list_students() if s["email"] == "badger@test.com")
    c.get("/ask?q=what+is+an+intelligent+agent")
    assert any(r["kind"] == "badge" for r in notify.for_user("s:" + code))                  # "First question" announced in the bell
    assert badges.unseen_count(code) >= 1
    page = c.get("/badges").get_data(as_text=True)
    assert "First question" in page and 'class="bd on' in page and "Beginner" in page
    assert badges.unseen_count(code) == 0                                                    # opening the page clears the counter
    # mistakes review
    c.get("/practice")
    assert "mode=mistakes" not in c.get("/practice").get_data(as_text=True)                  # nothing wrong yet -> no button
    c.post("/practice", data={"action": "wrong"})
    r = c.get("/practice")
    assert "mode=mistakes" in r.get_data(as_text=True)
    r = c.get("/practice?mode=mistakes")
    assert r.status_code == 200 and "Mistakes review" in r.get_data(as_text=True)
    c.post("/practice", data={"action": "right"})
    done = c.get("/practice").get_data(as_text=True)
    assert "Review finished" in done and "1 of 1" in done
    assert "mode=mistakes" not in done                                                       # fixed: nothing left to review
    assert "Fixed a mistake" in c.get("/badges").get_data(as_text=True)


def test_any_course_can_be_deleted_even_all_and_the_codes_list_feeds_the_dropdown(tmp_path, monkeypatch):
    """Runs on a throw-away COPY of the data, so the real AI course is never touched."""
    import io, shutil
    import app as A
    from core import catalog
    root = tmp_path / "site"
    (root / "static").mkdir(parents=True)
    shutil.copytree(config.BASE_DIR / "data", root / "data", ignore=shutil.ignore_patterns("ocr_cache"))
    shutil.copytree(config.BASE_DIR / "models", root / "models")
    shutil.copytree(config.BASE_DIR / "static" / "reports", root / "static" / "reports")
    for k, v in (("BASE_DIR", root), ("MODELS_DIR", root / "models"), ("REPORTS_DIR", root / "static" / "reports")):
        monkeypatch.setattr(config, k, v)
    monkeypatch.setattr(A, "STATE", {})
    monkeypatch.setattr(catalog, "FILE", lambda: root / "data" / "course_codes.json")
    admin = A.app.test_client()
    admin.post("/lecturer", data={"password": config.LECTURER_PASSWORD})
    # the admin uploads the codes sheet -> the add-course form becomes a dropdown
    sheet = catalog.template_xlsx([{"code": "AUTO", "name_en": "Automotive", "name_ar": "سيارات"}, {"code": "CTRL", "name_en": "Control", "name_ar": ""}])
    admin.post("/admin", data={"action": "upload_codes", "codes": (io.BytesIO(sheet), "codes.xlsx")}, content_type="multipart/form-data")
    page = admin.get("/admin").get_data(as_text=True)
    assert '<select name="code" id="courseCode"' in page and 'value="CTRL"' in page and "Automotive" in page
    pdfs = [root / "data" / "AI" / "lectures" / "lecture 2 Intelligent Agents.pdf"]
    pdf_bytes, pdf_name = pdfs[0].read_bytes(), pdfs[0].name                 # read now: the AI course is deleted below
    mk = lambda code: {"action": "add_course", "code": code, "name_en": "", "name_ar": "", "pdfs": [(io.BytesIO(pdf_bytes), pdf_name)]}
    # delete the AI course (the original one): its files go, the other course's models stay
    from core import doctors
    monkeypatch.setattr(doctors, "FILE", lambda: tmp_path / "doctors.json")
    did, dcode = doctors.add("Dr Codes")
    dr = A.app.test_client()
    dr.post("/lecturer", data={"username": doctors.username_of(doctors.get(did)), "password": dcode})
    assert dr.get("/admin").status_code == 200 and "courseCode" in dr.get("/admin").get_data(as_text=True)   # signed in, sees the dropdown
    dr.post("/admin", data=mk("ZZZZ"), content_type="multipart/form-data")                 # not in the admin's list -> refused
    assert "ZZZZ" not in [c["code"] for c in config.list_courses()]
    admin.get("/course/AI")
    admin.post("/admin", data={"action": "delete_course", "confirm": "AI"})
    assert not (root / "data" / "AI").exists() and not list((root / "models").glob("*.joblib")) + list((root / "models").glob("*.pkl"))
    assert (root / "models" / "MAM336").exists() and "AI" not in [c["code"] for c in config.list_courses()]
    st = A.app.test_client()
    as_student(st, "Nocourse")
    st.post("/my-courses", data={"course": ["MAM336"]})
    assert config.default_course() == "MAM336" and st.get("/home").status_code == 200   # the site falls back to another course
    # delete the last course: nothing crashes, students see "no courses yet", the admin can add a new one
    admin.get("/course/MAM336")
    admin.post("/admin", data={"action": "delete_course", "confirm": "MAM336"})
    assert config.list_courses() == []
    assert "No courses yet" in st.get("/home").get_data(as_text=True) and st.get("/profile").status_code == 200
    assert admin.get("/admin").status_code == 200 and "Add a new course" in admin.get("/admin").get_data(as_text=True)
    assert admin.get("/overview").status_code in (200, 302)
    # a new course by listed code: name comes from the list and the AI pipeline trains it
    admin.post("/admin", data=mk("AUTO"), content_type="multipart/form-data")
    got = {c["code"]: c for c in config.list_courses()}
    assert "AUTO" in got and got["AUTO"]["name_en"] == "Automotive" and got["AUTO"]["name_ar"] == "سيارات"
    assert (root / "models" / "AUTO").exists()
    st.post("/my-courses", data={"course": ["AUTO"]})
    assert st.get("/ask", query_string={"q": "what is a model-based reflex agent"}).status_code == 200 and st.get("/home").status_code == 200
    admin.post("/admin", data=mk("AUTO"), content_type="multipart/form-data")           # same code again: refused, nothing breaks
    assert len(config.list_courses()) == 1


def test_delete_course_rows_removes_only_that_course_and_ids_stay_unique(tmp_path):
    from core import logger
    f = tmp_path / "logs.xlsx"
    for course in ("AI", "X1", "AI", "X1"):
        logger.log_to_excel("Questions", {"student_code": "S1", "question": "q", "course": course}, path=f)
    logger.log_to_excel("Answers", {"student_code": "S1", "course": ""}, path=f)           # old row without a course = the first course
    assert logger.delete_course_rows("X1", path=f) == 2
    assert logger.delete_course_rows("AI", path=f) == 3
    rows = logger.read_sheet("Questions", path=f)
    assert rows == [] and logger.read_sheet("Answers", path=f) == []
    a = logger.log_to_excel("Questions", {"student_code": "S1", "question": "n", "course": "X1"}, path=f)
    b = logger.log_to_excel("Questions", {"student_code": "S1", "question": "m", "course": "X1"}, path=f)
    assert (a, b) == (1, 2)


def test_admin_badges_doctor_scope_notifications_and_student_view(tmp_path):
    from core import custom_badges, doctors, notify
    import app as A
    A.app.config["TESTING"] = True
    # a doctor and his course
    did, _pw = doctors.add("Dr Scope")
    cb = custom_badges
    b = cb.create("Star", "⭐", "Answer in class", did)
    assert b and b["owner"] == did
    assert cb.create("", "x", "y", did) is None
    new = cb.award(b["id"], ["S1", "S2"], did, "well done")
    assert set(new) == {"S1", "S2"} and cb.award(b["id"], ["S1"], did, "") == []
    assert cb.unseen_count("S1") == 1
    assert cb.for_student("S9", set()) == []                 # not his student: invisible
    assert [x["id"] for x in cb.for_student("S9", {did})] == [b["id"]]
    cb.mark_seen("S1"); assert cb.unseen_count("S1") == 0
    assert cb.delete(b["id"], "someone-else", False) is False
    assert cb.delete(b["id"], did, False) is True


def test_admin_badges_page_notifies_students_and_hides_them_from_other_doctors(client, monkeypatch, tmp_path):
    import app as A
    from core import doctors, notify
    monkeypatch.setattr(doctors, "FILE", lambda: tmp_path / "doctors.json")
    did, pw = doctors.add("Dr Nobody")                # owns no course -> sees no students
    master, doc = A.app.test_client(), A.app.test_client()
    master.post("/lecturer", data={"username": "admin", "password": config.LECTURER_PASSWORD})
    doc.post("/lecturer", data={"password": pw})
    with client.session_transaction() as ss:
        code = ss["student_code"]                     # whoever the shared client is signed in as
    page = master.get("/badges-admin").get_data(as_text=True)
    assert code in page                                # master sees every student
    assert code not in doc.get("/badges-admin").get_data(as_text=True)   # a doctor with no courses sees none
    r = master.post("/badges-admin", data={"action": "create_badge", "name": "Hero", "icon": "🦸", "desc": "Help a friend"})
    assert r.status_code == 302
    mine = [n for n in notify.for_user("s:" + code) if "Hero" in n["title"]]
    assert mine and "Help a friend" in mine[0]["body"]       # students are told how to earn it
    bid = master.get("/badges-admin").get_data(as_text=True).split('name="badge" value="')[1].split('"')[0]
    # a doctor cannot give (or delete) the master's badge
    doc.post("/badges-admin", data={"action": "award_badge", "badge": bid, "all_students": "1"})
    doc.post("/badges-admin", data={"action": "delete_badge", "badge": bid})
    from core import custom_badges
    assert custom_badges.get(bid) and not custom_badges.awards()
    master.post("/badges-admin", data={"action": "award_badge", "badge": bid, "students": code, "note": "Great"})
    assert "Hero" in client.get("/badges").get_data(as_text=True)
    assert custom_badges.unseen_count(code) == 0       # opening the page marks it seen


def test_main_admin_can_change_password_and_has_no_support_button():
    import app as A
    a = A.app.test_client()
    a.post("/lecturer", data={"username": "admin", "password": config.LECTURER_PASSWORD})
    assert 'id="supportBtn"' not in a.get("/profile").get_data(as_text=True)
    a.post("/profile", data={"action": "password", "old": "wrong", "new": "NewAdmin#77", "confirm": "NewAdmin#77"})
    assert A.adminpw.verify(config.LECTURER_PASSWORD)                      # wrong old password: unchanged
    a.post("/profile", data={"action": "password", "old": config.LECTURER_PASSWORD, "new": "NewAdmin#77", "confirm": "NewAdmin#77"})
    assert A.adminpw.verify("NewAdmin#77") and not A.adminpw.verify(config.LECTURER_PASSWORD)
    b = A.app.test_client()
    b.post("/lecturer", data={"username": "admin", "password": "NewAdmin#77"})
    assert b.get("/dashboard").status_code == 200


def test_catalog_sync_adds_codes_and_fills_names():
    from core import catalog
    catalog.save([{"code": "AUTO", "name_en": "", "name_ar": ""}])
    n = catalog.sync([{"code": "auto", "name_en": "Automotive", "name_ar": "سيارات"}, {"code": "new1", "name_en": "New", "name_ar": ""}])
    rows = {r["code"]: r for r in catalog.load()}
    assert n == 2 and rows["AUTO"]["name_en"] == "Automotive" and rows["NEW1"]["name_en"] == "New"
    assert catalog.sync([{"code": "AUTO", "name_en": "Other", "name_ar": ""}]) == 0 and catalog.load()[0]["name_en"] == "Automotive"


def test_exam_notification_has_no_link_to_the_student_attempt():
    from core import notify
    notify.push(["d:master"], "exam", "Exam finished", "Sara scored 2/10", "/exams/attempt/abc123")
    notify.push(["d:master"], "student", "New student", "Sara registered", "/students")
    rows = {r["title"]: r for r in notify.for_user("d:master")}
    assert rows["Exam finished"]["link"] == "" and rows["New student"]["link"] == "/students"


def test_true_false_questions_have_their_own_time_and_settings_only_hold_two_times():
    from core import exams as EX
    tf = {"type": "mcq", "answer": 0, "en": {"q": "Sky is blue", "options": ["True", "False"]}}
    mc = {"type": "mcq", "answer": 1, "en": {"q": "Pick", "options": ["a", "b", "c", "d"]}}
    assert EX.is_tf(tf) and not EX.is_tf(mc)
    st = {**EX.DEFAULTS, "min_mcq": 1.0, "min_tf": 0.5}
    assert EX._seconds(tf, st) == 30 and EX._seconds(mc, st) == 60


def test_chat_between_people_by_username_with_privacy_and_notification():
    import app as A
    from core import chat, doctors, notify
    did, pw = doctors.add("Dr Chat")
    a, b, d = A.app.test_client(), A.app.test_client(), A.app.test_client()
    as_student(a, "CHATA"); as_student(b, "CHATB"); d.post("/lecturer", data={"password": pw})
    from core import students
    ua = students.find("chata@test.com"); ub = students.find("chatb@test.com")
    ka, kb = "s:" + ua["code"], "s:" + ub["code"]
    # start by username (e-mail does not work), then send both ways
    assert "chat" in a.post("/chat", data={"username": "chatb@test.com"}).headers["Location"] and kb not in a.post("/chat", data={"username": "chatb@test.com"}).headers["Location"]
    r = a.post("/chat", data={"username": ub["username"]})
    assert r.status_code == 302 and "with=" in r.headers["Location"]
    assert a.post("/chat/send", data={"with": kb, "text": "hello <b>x</b>"}).get_json()["ok"]
    assert chat.unread_total(kb) == 1 and chat.unread_total(ka) == 0
    assert any("CHATA" in n["title"].upper() or "Test" in n["title"] for n in notify.for_user(kb))   # told once
    page = b.get("/chat?with=" + ka).get_data(as_text=True)
    assert "hello &lt;b&gt;x&lt;/b&gt;" in page and chat.unread_total(kb) == 0      # escaped, and read now
    assert b.post("/chat/send", data={"with": ka, "text": "hi back"}).get_json()["ok"]
    j = a.get(f"/chat/poll?with={kb}&after=0").get_json()
    assert [m["text"] for m in j["msgs"]] == ["hello <b>x</b>", "hi back"] and j["msgs"][1]["mine"] is False
    # a third person never sees their messages; nobody can write to himself or to a missing user
    assert chat.messages("s:S9999", ka) == []
    assert a.post("/chat/send", data={"with": ka, "text": "x"}).status_code == 400
    assert a.post("/chat/send", data={"with": "s:NOPE", "text": "x"}).status_code == 400
    # the doctor can write to a student and the student answers him
    assert d.post("/chat/send", data={"with": ka, "text": "Dr here"}).get_json()["ok"]
    assert "Dr here" in a.get("/chat?with=d:" + did).get_data(as_text=True)
    # guests have no chat
    g = A.app.test_client()
    assert g.get("/chat").status_code == 302


def test_opening_the_site_link_from_outside_always_asks_for_a_sign_in():
    import app as A
    c = A.app.test_client(); as_student(c, "LINK1")
    # a click inside the site (the logo) keeps the session
    assert c.get("/", headers={"Sec-Fetch-Site": "same-origin"}).headers["Location"].endswith("/home")
    # a typed address / shared link signs out and shows the start page with the message
    r = c.get("/", headers={"Sec-Fetch-Site": "none"})
    assert r.status_code == 302 and "/start" in r.headers["Location"]
    assert c.get("/home").status_code == 302                    # really signed out
    assert "sign in to enter" in c.get("/start").get_data(as_text=True)
    # same without the modern header: no Referer = from outside, own Referer = inside
    as_student(c, "LINK1")
    assert c.get("/", headers={"Referer": "http://localhost/home"}).headers["Location"].endswith("/home")
    assert "/start" in c.get("/").headers["Location"]


# ---------------- Study Studio (study tools built from the slides)
def _studio_inputs(lecture):
    p = pd.read_csv(config.course_paths("AI").passages).fillna("")
    t = pd.read_csv(config.course_paths("AI").topics).fillna("")
    t["name_ar"] = [a or n for a, n in zip(t.get("name_ar", t.name), t.name)]
    t["prereq_list"] = t.prerequisites.map(lambda s: [x for x in str(s).split(";") if x])
    g = pd.read_csv(config.course_paths("AI").glossary)
    return p, t, g


def test_studio_kit_comes_from_the_slides():
    from core import studio
    p, t, g = _studio_inputs(3)
    kit = studio.build(p, t, g, lecture=3)
    assert kit["lecture"] == 3 and kit["info"]["slides"] == len(p[p.lecture == 3])
    slide_text = " ".join(p[p.lecture == 3].text).lower()
    assert kit["summary"] and all(s["lecture"] == 3 for s in kit["summary"])
    assert all(d["definition"].lower().rstrip(".?!")[:25] in slide_text for d in kit["terms"])     # nothing invented
    for q in kit["quiz"]:
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4 and 0 <= q["answer"] < 4
    ids = {n["id"] for n in kit["map"]["nodes"]}
    assert "root" in ids and all(l["a"] in ids and l["b"] in ids for l in kit["map"]["links"])
    assert all(0 <= n["x"] <= kit["map"]["w"] and 0 <= n["y"] <= kit["map"]["h"] for n in kit["map"]["nodes"])
    assert studio.build(p, t, g, lecture=None)["info"]["slides"] == len(p)                         # all lectures


def test_studio_pages_and_downloads(client):
    for url in ("/studio", "/studio?lecture=5&tool=quiz", "/studio?lecture=zzz", "/studio?tool=nope&lang=ar"):
        r = client.get(url)
        assert r.status_code == 200 and "studioData" in r.get_data(as_text=True)
    r = client.get("/studio/terms.xlsx?lecture=3")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    try:
        import pptx  # noqa: F401
        r = client.get("/studio/slides.pptx?lecture=3")
        assert r.status_code == 200 and r.data[:2] == b"PK"
    except ImportError:
        pass
    assert 'href="/studio"' in client.get("/home").get_data(as_text=True)                                # tab in the nav


def test_studio_needs_sign_in():
    import app as A
    assert A.app.test_client().get("/studio").status_code == 302
