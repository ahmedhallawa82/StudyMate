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
    f = tmp_path_factory.mktemp("stu") / "students.json"
    students.FILE = lambda: f


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
        assert r.status_code == 302 and "/dashboard" in r.headers["Location"]
    html = c.get("/dashboard").get_data(as_text=True)
    assert "/practice" not in html and "/progress" not in html and "SEP1" not in html and "/evaluation" in html
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
        assert d1.get("/dashboard").status_code == 200 and d1.get("/evaluation").status_code == 200
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
        assert 'id="courseCombo"' in html and "DCT9" in html and "js/courses.js" in html
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
    assert "Doctors sheet" not in page and "Change my password" in page
    d.post("/admin", data={"action": "change_password", "old": "wrong", "new": "MyNewPass9", "confirm": "MyNewPass9"})
    assert pushed[-1][0][5] == ""                                   # wrong old password: nothing changed
    d.post("/admin", data={"action": "change_password", "old": first[4], "new": "short", "confirm": "short"})
    assert pushed[-1][0][5] == ""
    d.post("/admin", data={"action": "change_password", "old": first[4], "new": "MyNewPass9", "confirm": "MyNewPass9"})
    assert pushed[-1][0][5] == "MyNewPass9" and pushed[-1][0][4] == first[4]
    # new password works, the system one no longer does
    assert doctors.check("MyNewPass9") == did and doctors.check(first[4]) is None
    n = A.app.test_client(); n.post("/lecturer", data={"password": "MyNewPass9"})
    assert n.get("/admin").status_code == 200 and "Change my password" in n.get("/admin").get_data(as_text=True)
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
    assert "/dashboard" in a.post("/start", data={"username": "admin", "password": config.LECTURER_PASSWORD}).headers["Location"]
    admin.post("/admin", data={"action": "add_doctor", "doctor_name": "Dr Mail", "doctor_email": "dr@x.com"})
    d = doctors.list_doctors()[0]
    assert d["email"] == "dr@x.com" and d["username"].startswith("dr")
    pw = doctors._load()[0]["initial"]
    other = A.app.test_client()
    assert other.post("/start", data={"username": "dr-wrong", "password": pw}).status_code == 200   # username must match
    doc = A.app.test_client()
    assert "/dashboard" in doc.post("/start", data={"username": d["username"], "password": pw}).headers["Location"]
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
