"""StudyMate - Course Study Assistant (AI Lab Project 1E).

Run:  python app.py      then open http://127.0.0.1:5000
"""
import json
import random
import re
from pathlib import Path
from collections import Counter, defaultdict
from functools import wraps

import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g, abort, send_file
from markupsafe import Markup
from werkzeug.utils import secure_filename

import config
from core import doctors, sheet_sync, students, mailer, notify, profiles, support, passgen, badges, catalog, custom_badges, adminpw, chat
from core import studio as STU
from core import accountdel
from core import faq, modelspw, autoeval, followup, videos, neural, insights, nbresults
from core import slideview
from core.passages import lecture_number
from core import schedule as SCH
from core import exams as EX
from core import mastery as M
from core.classifier import TopicClassifier, KIND_NAME
from core.logger import log_to_excel, read_sheet, ensure_workbook
from core.search import SearchEngine, build_index, highlight
from core.topics import load_topics, study_next
from core.i18n import tr

app = Flask(__name__)
app.jinja_env.globals["neural_ok"] = lambda: neural.available()
app.secret_key = config.SECRET_KEY
from datetime import timedelta
app.permanent_session_lifetime = timedelta(days=30)      # "remember me"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 7 * 24 * 3600     # CSS / JS / images are cached by the browser; the ?v= stamp below changes when a file does
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024  # PDFs (50 MB) and recorded lectures (videos)

STATE = {}          # course code -> loaded models and data


def load_state(code=None):
    """Load models + data of one course into memory (also called after the admin rebuilds the index)."""
    code = code or config.default_course()
    if not code:
        return None                                        # no course at all (the admin deleted them all)
    P = config.course_paths(code)
    st = {}
    try:
        st["engine"] = SearchEngine.load(code)
        st["clf"] = TopicClassifier.load(course=code)
    except Exception as e:  # models missing or saved with another scikit-learn version -> rebuild them
        print(f"Could not load the saved models of {code} ({type(e).__name__}). Rebuilding them, please wait ...")
        if code == config.DEFAULT_COURSE and any(c["full"] for c in config.list_courses() if c["code"] == code):
            import scripts.train as T
            import scripts.evaluate as E
            if not config.PASSAGES_CSV.exists():
                from core.passages import build_passages
                build_passages()
            T.train()
            build_index()
            E.main()
        else:
            from core.autocourse import regenerate
            regenerate(code)
        st["engine"] = SearchEngine.load(code)
        st["clf"] = TopicClassifier.load(course=code)
    st["topics"] = load_topics(code)
    st["names"] = dict(zip(st["topics"].topic, st["topics"].name))
    st["names_ar"] = dict(zip(st["topics"].topic, st["topics"].name_ar))
    qb = pd.read_csv(P.bank).fillna("")
    st["bank"] = qb
    st["qid_topic"] = dict(zip(qb.q_id, qb.topic))
    STATE[code] = st
    ensure_workbook()
    return st


def course_codes():
    return [c["code"] for c in config.list_courses()]


def sync_codes_from_courses():
    """Every uploaded course (its code and names) goes into the course-codes list."""
    return catalog.sync([{"code": c["code"], "name_en": c["name_en"], "name_ar": c["name_ar"]} for c in config.list_courses()])


def student_course_list():
    """Courses a signed-in student account is registered in; None for a guest (a guest may open any course)."""
    me = session.get("student_code")
    if not me or me.startswith("GUEST-"):
        return None
    st = students.get(me)
    return [c for c in (st["courses"] if st else []) if c in course_codes()]


def course_code():
    c = session.get("course")
    if not session.get("lecturer"):
        mine = student_course_list()
        if mine:
            return c if c in mine else mine[0]
    if session.get("lecturer") and not is_master():            # a doctor works only on his own courses
        own = [x["code"] for x in visible_courses()]
        if own:
            return c if c in own else own[0]
    return c if c in course_codes() else config.default_course()


def S():
    code = course_code()
    return STATE.get(code) or load_state(code)


def lang():
    l = request.args.get("lang")
    if l in ("en", "ar"):
        session["lang"] = l
    return session.get("lang", "en")


def is_full_course():
    return any(c["full"] for c in config.list_courses() if c["code"] == course_code())


def course_title(code=None, l=None):
    code, l = code or course_code(), l or lang()
    for c in config.list_courses():
        if c["code"] == code:
            return (c["name_ar"] or c["name_en"]) if l == "ar" else c["name_en"]
    return config.COURSE_NAME


def flash_t(key, **kw):
    flash(tr(key, lang(), **kw))


def log(sheet, record, update_id=None):
    """Every write goes through log_to_excel(); the course is added here."""
    if update_id is None:
        record = {**record, "course": course_code()}
    return log_to_excel(sheet, record, update_id=update_id)


# ------------------------------------------------------------------ helpers
def student():
    return session.get("student_code")


def student_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if session.get("lecturer"):                    # the admin area and the student area are separate
            return redirect(url_for("staff_home"))
        if not student():
            return redirect(url_for("start", next=request.path))
        if request.endpoint != "my_courses" and student_course_list() == []:     # first visit: choose the courses first
            return redirect(url_for("my_courses"))
        return view(*a, **kw)
    return wrapper


def lecturer_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("lecturer"):
            return redirect(url_for("lecturer_login", next=request.path))
        return view(*a, **kw)
    return wrapper


# ------------------------------------------------------------------ who is the admin? (master or one doctor)
def admin_id():
    return session.get("admin_id") if session.get("lecturer") else None


def is_main():
    """The one main admin (the owner of the site)."""
    return admin_id() == doctors.MASTER


def is_subadmin():
    a = admin_id()
    return bool(a) and a != doctors.MASTER and (doctors.get(a) or {}).get("role") == "admin"


def is_master():
    """Main admin or a sub-admin: both see every course. What a sub-admin may open is decided by has_perm()."""
    return is_main() or is_subadmin()


def my_perms():
    if is_main():
        return set(doctors.PERMS)
    if is_subadmin():
        return set(doctors.get(admin_id()).get("perms", []))
    return set(doctors.PERMS) - {"doctors", "support"}        # a doctor keeps his old access (his own courses)


def has_perm(key):
    """Main admin: everything. Sub-admin: only the permissions the main admin ticked."""
    return key in my_perms()


def perm_required(key):
    def deco(view):
        @wraps(view)
        def wrapper(*a, **kw):
            if session.get("lecturer") and not has_perm(key):
                flash_t("adms_no_perm")
                return redirect(url_for("staff_home") if request.endpoint != "staff_home" else url_for("my_courses"))
            return view(*a, **kw)
        return wrapper
    return deco


def course_owner(code):
    return next((c["meta"].get("owner") for c in config.list_courses() if c["code"] == code), None)


def can_manage(code):
    """The master manages every course; a doctor only the courses registered under his name."""
    if not session.get("lecturer"):
        return False
    return is_master() or (course_owner(code) is not None and course_owner(code) == admin_id())


def visible_courses():
    allc = config.list_courses()
    if session.get("lecturer") and not is_master():
        return [c for c in allc if can_manage(c["code"])]
    return allc


def remove_course_files(code):
    """Delete one course: its data folder, models and reports. The AI course keeps its files straight inside models/ and
    static/reports/ (next to the other courses' folders), so there only its own files go."""
    import shutil
    P = config.course_paths(code)
    shutil.rmtree(P.data, ignore_errors=True)
    for d in (P.models, P.reports):
        if code == config.DEFAULT_COURSE:
            for f in d.glob("*"):
                if f.is_file():
                    f.unlink()
        else:
            shutil.rmtree(d, ignore_errors=True)
    STATE.pop(code, None)
    session.pop("practice", None)


OPEN_WITHOUT_COURSES = {"static", "start", "register", "forgot", "logout", "lecturer_login", "lecturer_logout", "admin", "support_send",
                        "support_inbox", "staff_home", "doctors_page", "export_doctors", "students_page", "students_export", "export_students",
                        "profile", "avatar", "notifications_page", "notifications_read", "generate_password", "download_logs", "course_codes_template"}


@app.url_defaults
def _static_stamp(endpoint, values):
    """/static/x.css?v=<file time>: a changed file gets a new address, an unchanged one stays cached for a week."""
    if endpoint == "static" and "filename" in values and "v" not in values:
        try:
            values["v"] = int((Path(app.static_folder) / values["filename"]).stat().st_mtime)
        except OSError:
            pass


@app.before_request
def _no_courses_guard():
    """With every course deleted only the account / admin pages work; the rest shows 'no courses yet'."""
    if request.endpoint is None or request.endpoint in OPEN_WITHOUT_COURSES or course_codes():
        return None
    if session.get("lecturer"):
        return redirect(url_for("admin"))
    return render_template("no_courses.html"), 200


def visit(page):
    if session.get("lecturer"):                        # admin pages are not student visits
        return
    from core.logger import log_async
    log_async("Visits", {"student_code": student() or ("lecturer" if session.get("lecturer") else ""), "page": page, "course": course_code()})


def my_mastery(code=None):
    code = code or student()
    rows = [a for a in read_sheet("Answers") if a.get("student_code") == code and a.get("course") == course_code()]
    return M.replay(rows, S()["qid_topic"])


def my_reviews(mastery=None, code=None):
    """Spaced repetition for the signed-in student: weak topics practised before, with their next review date."""
    code = code or student()
    if not code:
        return []
    rows = [a for a in read_sheet("Answers") if a.get("student_code") == code and a.get("course") == course_code()]
    out = insights.reviews(rows, my_mastery(code) if mastery is None else mastery, S()["qid_topic"])
    for r in out:
        r["name"] = topic_name(r["topic"])
    return out


def topic_panel(mastery):
    items, l = [], lang()
    for _, t in S()["topics"].iterrows():
        lvl = mastery.get(t.topic, 0.0)
        items.append({"topic": t.topic, "name": t["name_ar"] if l == "ar" else t["name"], "level": lvl,
                      "pct": round(lvl * 100), "colour": M.colour(lvl), "started": t.topic in mastery})
    due = [r for r in my_reviews(mastery) if r["overdue"]] if student() and not session.get("lecturer") else []
    if due:                                               # a review that is due comes before new material
        r = due[0]
        return items, {"topic": r["topic"], "name": r["name"], "review": True,
                       "why": tr("sr_why", l, t=r["name"], d=r["days_ago"], g=r["gap"])}
    nxt, why = study_next(mastery, S()["topics"], l)
    return items, ({"topic": nxt, "name": topic_name(nxt), "why": why} if nxt else {"why": why})


def topic_name(topic, default=None):
    d = S()["names_ar"] if lang() == "ar" else S()["names"]
    return d.get(topic, default or topic)


def current_theme():
    t = request.args.get("theme")
    if t in config.THEMES:
        session["theme"] = t
    return session.get("theme", config.THEME)


def user_key():
    """'s:<code>' for a signed-in student account, 'd:<id>' for a doctor / the admin, None for guests and visitors."""
    if session.get("lecturer"):
        return "d:" + (admin_id() or doctors.MASTER)
    me = student()
    return "s:" + me if me and not me.startswith("GUEST-") else None


def _me_context():
    key = user_key()
    if not key:
        return {"me_key": None, "me_avatar": None, "me_name": "", "me_role": "", "notifs": [], "unread": 0, "badge_new": 0, "chat_unread": 0}
    pkey = profiles.safe(key)
    if key.startswith("s:"):
        st = students.get(key[2:]) or {}
        name, role = (st.get("first", "") + " " + st.get("last", "")).strip() or key[2:], tr("role_student", lang())
    elif key == "d:" + doctors.MASTER:
        name, role = profiles.get(pkey).get("name") or tr("role_admin", lang()), tr("role_admin", lang())
    else:
        name, role = session.get("admin_name", ""), tr("role_doctor", lang())
    return {"me_key": key, "me_avatar": url_for("avatar", key=pkey) + "?v=" + str(int(profiles.avatar_path(key).stat().st_mtime)) if profiles.avatar_path(key) else None,
            "me_name": name, "me_role": role, "notifs": notify.for_user(key, 6), "unread": notify.unread_count(key),
            "badge_new": (badges.unseen_count(key[2:]) + custom_badges.unseen_count(key[2:])) if key.startswith("s:") else 0,
            "chat_unread": chat.unread_total(key)}


def quick_links():
    """Pages and sections the top-bar search can jump to: [{t: title, u: url, i: icon, k: extra words (English + Arabic)}]."""
    l = lang()
    T = lambda k: tr(k, l)
    items = []

    def add(icon, key, endpoint, words="", **kw):
        try:
            items.append({"i": icon, "t": T(key), "u": url_for(endpoint, **kw), "k": words})
        except Exception:                                    # noqa: BLE001 - a missing route must never break a page
            pass
    if session.get("lecturer"):
        master = is_master()
        add("🏠", "nav_home", "staff_home", "home overview الرئيسية")
        add("📊", "nav_dashboard", "dashboard", "dashboard statistics data احصائيات بيانات")
        add("🛠️", "nav_content", "admin", "content lectures upload slides pdf محاضرات رفع محتوى")
        add("🎬", "vid_title", "admin", "videos youtube recorded فيديو فيديوهات", _anchor="videos")
        add("📝", "nav_exams", "exams_manage", "exams questions bank upload true false mcq امتحان اسئلة بنك")
        add("⚙️", "ex_tab_s", "exams_manage", "exam settings time minutes اعدادات وقت", tab="settings")
        add("📋", "ex_tab_r", "exams_manage", "exam results attempts degrees نتايج درجات", tab="results")
        add("👥", "nav_students", "students_page", "students طلاب message رسالة export")
        add("📈", "risk_title", "dashboard", "at risk students inactive low level طلاب متعثرين", _anchor="risk")
        add("❔", "ua_title", "dashboard", "not found unanswered questions اسئلة مفيش اجابة", _anchor="unanswered")
        add("🏅", "nav_badges", "badges_admin", "badges awards شارات")
        add("💬", "nav_chat", "chat_page", "chat messages رسائل محادثة")
        add("📅", "nav_calendar", "calendar_page", "calendar schedule تقويم")
        add("🔔", "notif_title", "notifications_page", "notifications اشعارات")
        add("❓", "nav_help", "help_page", "help faq formats accepted question files مساعدة")
        add("👤", "nav_profile", "profile", "profile password account حسابي")
        add("📚", "sh_courses", "all_courses", "courses مواد")
        if master:
            add("🛡️", "doc_title", "doctors_page", "admins doctors add doctor دكاترة ادمن")
            add("🛟", "support_inbox", "support_inbox", "support help requests دعم")
    elif student():
        add("🏠", "nav_home", "student_home", "home الرئيسية")
        add("🔎", "nav_ask", "ask", "ask question search slides اسأل سؤال بحث")
        add("🎓", "nav_studio", "studio", "studio quiz mind map videos فيديوهات كويز")
        add("🎯", "nav_practice", "practice", "practice questions hints تدريب")
        add("📈", "nav_progress", "progress", "progress level mastery review تقدم مستوى مراجعة")
        add("📝", "nav_exams", "exams", "exams امتحانات")
        add("📄", "nav_materials", "materials", "materials lectures slides pdf محاضرات ملفات")
        add("🎒", "my_courses", "my_courses", "my courses مواد")
        if user_key():
            add("🏅", "nav_badges", "badges_page", "badges شارات")
            add("💬", "nav_chat", "chat_page", "chat doctor message رسالة دكتور")
            add("📅", "nav_calendar", "calendar_page", "calendar تقويم")
            add("🔔", "notif_title", "notifications_page", "notifications اشعارات")
            add("👤", "nav_profile", "profile", "profile password حسابي")
        add("❓", "nav_help", "help_page", "help faq مساعدة")
    return items


@app.context_processor
def inject():
    l = lang()
    args = request.args.to_dict()
    args["lang"] = "en" if l == "ar" else "ar"
    from urllib.parse import urlencode
    return {"embed": request.args.get("embed") == "1" or request.headers.get("Sec-Fetch-Dest") == "iframe", "lang_url": request.path + "?" + urlencode(args), "theme": current_theme(), "course": course_title(), "course_code": course_code(), "student_code": student(), "student_name": session.get("student_name", ""),
            "is_lecturer": session.get("lecturer"), "is_master_user": bool(session.get("lecturer")) and is_main(), "is_subadmin": bool(session.get("lecturer")) and is_subadmin(), "perms": my_perms() if session.get("lecturer") else set(), "can_see_all": bool(session.get("lecturer")) and is_master(), "names": (S() or {}).get("names_ar" if l == "ar" else "names", {}),
            "quick_links": quick_links(), "lang": l, "dir": "rtl" if l == "ar" else "ltr", "t": lambda key, **kw: tr(key, l, **kw),
            "courses": [{**c, "title": c["name_ar"] if l == "ar" and c["name_ar"] else c["name_en"]}
                        for c in visible_courses() if session.get("lecturer") or student_course_list() is None
                        or c["code"] in student_course_list()],
            "admin_role": ("master" if is_main() else ("admin" if is_subadmin() else "doctor")) if session.get("lecturer") else None,
            "admin_name": session.get("admin_name", ""), "login_alert": getattr(g, "login_alert", None), "support_open": support.open_count() if session.get("lecturer") and is_master() and has_perm("support") else 0, **_me_context()}


# ------------------------------------------------------------------ student login (code only, no names)
def sign_in_as(kind, who, name, remember):
    """Put the person in the session (student, doctor or admin)."""
    course = session.get("course")
    lang_ = session.get("lang")
    theme_ = session.get("theme")
    session.clear()
    for k, v in (("course", course), ("lang", lang_), ("theme", theme_)):
        if v:
            session[k] = v
    session.permanent = bool(remember)
    if kind == "student":
        session["student_code"], session["student_name"] = who["code"], who["first"]
    else:
        session["lecturer"] = True
        session["admin_id"], session["admin_name"] = who, name


def try_login(ident, pw):
    """(kind, who, name) for admin / doctor / student, else None."""
    import hmac
    ident, pw = (ident or "").strip(), (pw or "").strip()
    if not pw:
        return None
    if ident.lower() in ("admin", ""):
        if adminpw.verify(pw):
            return "admin", doctors.MASTER, ""
    if "@" not in ident:                                   # doctors sign in with their username (or the password alone)
        did = doctors.check(pw, username=ident or None)
        if did:
            return "doctor", did, doctors.get(did)["name"]
    if ident:
        st = students.check(ident, pw)
        if st:
            did = doctors.by_student(st["code"])              # a student the main admin made an admin signs in to the admin side
            if did:
                return "doctor", did, doctors.get(did)["name"]
            return "student", st, ""
    return None


def handle_login(default_next):
    """Shared by /start and /lecturer. Returns a redirect on success, else None (a message was flashed).
    The typed username/e-mail and password are compared with the stored accounts (students, doctors, admin).
    Each typed name gets 5 tries; from the 2nd wrong one a pop-up asks the person to contact support."""
    import time
    key = _key()
    if _locked(key):
        g.login_alert = {"kind": "locked", "left": 0, "ident": key}
        return None
    if not (request.form.get("password") or "").strip():
        flash_t("login_empty")
        return None
    got = try_login(request.form.get("username", ""), request.form.get("password", ""))
    if not got:
        n, t0 = _FAILS.get(key, (0, time.time()))
        n += 1
        _FAILS[key] = (n, t0)
        if n >= MAX_TRIES:
            g.login_alert = {"kind": "locked", "left": 0, "ident": key}
        elif n >= 2:
            g.login_alert = {"kind": "help", "left": MAX_TRIES - n, "ident": key}
        flash_t("wrong_login")
        return None
    _FAILS.pop(key, None)
    kind, who, name = got
    chosen = request.form.get("course")
    sign_in_as(kind, who, name, request.form.get("remember"))
    if chosen in course_codes() and kind == "student":
        session["course"] = chosen
    if kind == "student":
        return redirect(request.args.get("next") or url_for("student_home"))
    return redirect(request.args.get("next") or url_for("staff_home"))


@app.route("/start", methods=["GET", "POST"])
def start():
    if session.get("lecturer"):
        return redirect(url_for("staff_home"))
    if request.method == "POST":
        if request.form.get("guest"):                  # guest: no account needed, a temporary code is made
            import secrets
            code = "GUEST-" + secrets.token_hex(2).upper()
            sign_in_as("student", {"code": code, "first": code}, "", False)
            chosen = request.form.get("course")
            if chosen in course_codes():
                session["course"] = chosen
            return redirect(request.args.get("next") or url_for("student_home"))
        r = handle_login(None)
        if r:
            return r
    return render_template("start.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        if f.get("password") != f.get("confirm"):
            flash_t("pw_mismatch")
        else:
            reserved = {"admin"} | {d["username"].lower() for d in doctors.list_doctors()}
            st, err = students.register(f.get("first"), f.get("last"), f.get("email"), f.get("password", ""),
                                        f.get("username", ""), reserved)
            if err:
                flash_t(err, n=students.MIN_LEN)
            else:
                log_to_excel("Students", {"student_code": st["code"], "first_name": st["first"],
                                          "last_name": st["last"], "email": st["email"]})
                sign_in_as("student", st, "", f.get("remember"))
                notify.push(["s:" + st["code"]], "welcome", tr("n_welcome_title", lang()), tr("n_welcome_body", lang()), url_for("profile"))
                return redirect(url_for("my_courses"))
    return render_template("register.html")


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    """A strong random password is e-mailed with the 'login details' template. It is saved in the account only AFTER the
    e-mail was accepted, so it always works the moment the person types it (and nobody is locked out if mail fails)."""
    from core import mailtemplates, passgen
    sent = False
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if mailer.enabled():
            st, d = students.find_by_email(email), None
            if not st:
                d = doctors.find_by_email(email)
            if st or d:
                pw = passgen.generate()
                who = (st["first"], st["email"], "student") if st else (d["name"], doctors.username_of(d), "doctor")
                subject, text, html = mailtemplates.password_email(who[0], who[1], pw, who[2], url_for("start", _external=True), lang())
                if mailer.send_now(email, subject, text, html):
                    (students.set_password(st["code"], pw) if st else doctors.set_password(d["id"], pw))
                    for k in {email.lower(), who[1].lower()}:         # a locked-out person gets in again with the new password
                        _FAILS.pop(k, None)
        sent = True                                   # same answer whether the e-mail exists or not
    return render_template("forgot.html", sent=sent, mail_on=mailer.enabled())


@app.route("/course/<code>")
def choose_course(code):
    mine = student_course_list() if not session.get("lecturer") else None
    if code in course_codes() and code != session.get("course") and (not session.get("lecturer") or can_manage(code)) \
            and (mine is None or code in mine):
        session["course"] = code
        session.pop("practice", None)
    if session.get("lecturer"):
        return redirect(request.args.get("next") or url_for("staff_home"))
    return redirect(request.args.get("next") or url_for("student_home" if student() else "start"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("start"))


def _opened_from_outside():
    """True when this page was opened by a typed address, a bookmark or a link from another site (not by a click inside StudyMate)."""
    site = request.headers.get("Sec-Fetch-Site")
    if site:
        return site != "same-origin"
    ref = request.headers.get("Referer", "")
    return not ref.startswith(request.host_url)


@app.route("/")
def home():
    if _opened_from_outside() and (session.get("lecturer") or student()):
        keep = {k: session[k] for k in ("lang", "theme", "mode") if k in session}          # a shared link always asks for a sign-in
        session.clear()
        session.update(keep)
        flash_t("login_required")
        return redirect(url_for("start"))
    if session.get("lecturer"):
        return redirect(url_for("staff_home"))
    return redirect(url_for("student_home") if student() else url_for("start"))


def _streak(days):
    """Consecutive days of activity ending today (or yesterday)."""
    from datetime import date, timedelta
    ds = {d for d in days if d}
    cur, n = date.today(), 0
    if cur.isoformat() not in ds:
        cur -= timedelta(days=1)
    while cur.isoformat() in ds:
        n += 1
        cur -= timedelta(days=1)
    return n


def _course_owner_map():
    return {c["code"]: c["meta"].get("owner") for c in config.list_courses()}


def student_owners(code):
    """Doctor ids whose courses this student is registered in (their custom badges reach him)."""
    st = students.get(code) or {}
    om = _course_owner_map()
    return {om[c] for c in st.get("courses", []) if om.get(c)}


def _special_cards(code):
    out = []
    for b in custom_badges.for_student(code, student_owners(code)):
        out.append({"id": b["id"], "group": "special", "icon": b["icon"], "name": b["name"], "desc": b["desc"], "target": 1,
                    "value": int(b["earned"]), "earned": b["earned"], "when": b["when"], "pct": 100 if b["earned"] else 0,
                    "note": b["note"], "new": b["new"]})
    return out


GROUP_ORDER = badges.GROUPS


def my_mistakes():
    """Questions of this course whose latest answer by this student was wrong (oldest first)."""
    last = {}
    for a in read_sheet("Answers"):
        if a.get("student_code") == student() and a.get("course") == course_code():
            last[a["question_id"]] = str(a["correct"]) in ("1", "True")
    known = S()["qid_topic"]
    return [q for q, ok in last.items() if not ok and q in known]


def award(code=None):
    """Work out the student's badges, announce the new ones in the bell, and return all of them."""
    code = code or student()
    if not code or code.startswith("GUEST-"):
        return []
    mine = lambda rows: [r for r in rows if r.get("student_code") == code]
    topics_of = {}
    for c in config.list_courses():
        try:
            topics_of[c["code"]] = list(load_topics(c["code"]).topic)
        except Exception:
            pass
    allb = badges.compute(mine(read_sheet("Questions")), mine(read_sheet("Answers")), mine(read_sheet("Exams")), topics_of, config.GREEN_FROM, lang())
    got = {b["id"]: b["when"] for b in allb if b["earned"]}
    by_id = {b["id"]: b for b in allb}
    for bid in badges.new_ids(code, got):
        b = by_id[bid]
        notify.push(["s:" + code], "badge", tr("badge_new", lang(), name=b["name"]), b["desc"], url_for("badges_page"))
    return allb


@app.route("/home")
@student_required
def student_home():
    visit("home")
    award()
    check_risk(course_code())
    code, me = course_code(), student()
    mastery = my_mastery()
    items, nxt = topic_panel(mastery)
    qs = [q for q in read_sheet("Questions") if q.get("student_code") == me and q.get("course") == code]
    ans = [a for a in read_sheet("Answers") if a.get("student_code") == me and a.get("course") == code]
    allv = [v for v in read_sheet("Visits") if v.get("student_code") == me]
    exams_done = [a for a in EX.list_attempts(code, me) if a["status"] == "done"]
    correct = sum(str(a["correct"]) in ("1", "True") for a in ans)
    overall = round(100 * sum(i["level"] for i in items) / len(items)) if items else 0
    days = [str(x.get("time", ""))[:10] for x in qs + ans + allv]
    stats = {"asked": len(qs), "answered": len(ans), "acc": round(100 * correct / len(ans)) if ans else None,
             "green": sum(i["colour"] == "green" for i in items), "topics": len(items), "overall": overall,
             "exams": len(exams_done), "exam_avg": round(sum(a["pct"] for a in exams_done) / len(exams_done)) if exams_done else None,
             "streak": _streak(days), "mistakes": len(my_mistakes())}
    weak = sorted(items, key=lambda i: i["level"])[:4]
    recent_q = [{"q": q["question"], "found": q.get("found") == "yes"} for q in qs[-4:][::-1]]
    recent_e = [{"when": datetime_str(a["started"]), "pct": a["pct"], "score": a["score"], "max": a["max"], "id": a["id"]} for a in exams_done[:3]]
    import datetime as _dt
    td = _dt.date.today()
    start = td - _dt.timedelta(days=(td.weekday() + 2) % 7)   # week starts Saturday
    wk = []
    for i in range(7):
        d = start + _dt.timedelta(days=i)
        n = sum(1 for x in days if x == d.isoformat())
        wk.append({"iso": d.isoformat(), "day": d.day, "wd": d.weekday(), "n": n, "today": d == td})
    wmax = max([w["n"] for w in wk] + [1])
    for w in wk:
        w["h"] = round(100 * w["n"] / wmax)
    plan = sorted([i for i in items if i["colour"] != "green"], key=lambda i: i["level"])[:5]
    cont = nxt if nxt.get("topic") else None
    hour = __import__("datetime").datetime.now().hour
    greet = "gm" if hour < 12 else "ga" if hour < 18 else "ge"
    name = session.get("student_name") or me
    return render_template("home.html", stats=stats, items=items, weak=weak, week=wk, plan=plan, cont=cont, week_total=sum(w["n"] for w in wk), nxt=nxt, recent_q=recent_q, recent_e=recent_e,
                           greet=greet, name=name, exam_ready=len(EX.eligible(code)) > 0, today=__import__("datetime").date.today().isoformat())


# ------------------------------------------------------------------ Ask
def best_method():
    """The search model with the best measured quality for this course (MRR, then top-1), from its last evaluation; BM25 when nothing was measured yet."""
    try:
        m = json.loads((config.course_paths(course_code()).reports / "auto_metrics.json").read_text(encoding="utf-8"))["methods"]
        ok = [k for k in m if k in ("tfidf", "bm25", "lsa", "hybrid")]
        return max(ok, key=lambda k: (m[k]["mrr"], m[k]["top1"], k == "bm25"))
    except (OSError, ValueError, KeyError, TypeError):
        return "bm25"


@app.route("/ask", methods=["GET", "POST"])
@student_required
def ask():
    result = None
    question = request.values.get("q", "").strip()
    method = best_method()                                         # the site picks the most accurate search model itself
    if question:
        clf, eng = S()["clf"], S()["engine"]
        topic, conf = clf.predict(question)
        found, hits = eng.search(question, method=method)
        if found and hits and not is_full_course():
            # courses without labelled questions: the topic of the closest slides is more reliable than the classifier
            votes = Counter()
            for h in hits:
                votes[h["topic"]] += h["score"]
            topic = votes.most_common(1)[0][0]
            conf = votes[topic] / sum(votes.values())
        for h in hits:
            h["html"] = Markup(highlight(h["text"], question))
        view = slideview.build_view(hits, question, lambda t, q: Markup(highlight(t, q))) if found and hits else None
        log_id = log("Questions", {
            "student_code": student(), "question": question, "topic": topic if found else "",
            "confidence": round(conf, 3), "first_slide": hits[0]["passage_id"] if hits else "",
            "found": "yes" if found else "no", "method": method, "helpful": "",
        })
        award()
        result = {"found": found, "hits": hits, "topic": topic, "topic_name": topic_name(topic),
                  "confidence": round(conf * 100), "log_id": log_id, "view": view}
    else:
        visit("ask")
    items, nxt = topic_panel(my_mastery())
    return render_template("ask.html", question=question, method=method, result=result, items=items, nxt=nxt,
                           examples=examples())


@app.route("/slide-image/<pid>.png")
def slide_image(pid):
    """Picture of one slide (made from the lecture PDF the first time and then cached); 404 when it cannot be made."""
    if not (student() or session.get("lecturer")) or not re.fullmatch(r"L\d{2,3}S\d{1,3}", pid):
        abort(404)
    lec, slide = (int(x) for x in re.findall(r"\d+", pid))
    P = config.course_paths(course_code())
    pdf = next((f for f in sorted(P.lectures.glob("*.pdf")) if lecture_number(f.name) == lec), None)
    png = slideview.slide_png(pdf, slide, P.data / "slides", big=request.args.get("size") == "big") if pdf else None
    if not png:
        abort(404)
    resp = send_file(png, mimetype="image/png")
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


def examples():
    """Example questions in the interface language (only the first course has hand-picked ones)."""
    if course_code() == config.DEFAULT_COURSE:
        if lang() == "ar":
            return ["ايه هو البحث بالعرض", "ما هو اختبار تورنج", "ما هي خوارزمية مينيماكس",
                    "ايه هو التقليم الفا بيتا", "ما هي شبكة بايز"]
        return ["What is an admissible heuristic?", "difference between BFS and uniform cost search",
                "when does alpha beta prune a branch", "what does PEAS stand for", "how does variable elimination work"]
    meta = next((c["meta"] for c in config.list_courses() if c["code"] == course_code()), {})
    ex = meta.get("examples_ar" if lang() == "ar" else "examples_en")
    if ex:
        return ex
    bank = S()["bank"]
    plain = bank[~bank.question.str.startswith("Fill in the blank")]
    return list(plain.question.head(4)) if len(plain) else []


@app.route("/helpful/<int:log_id>/<answer>", methods=["POST"])
@student_required
def helpful(log_id, answer):
    answer = "yes" if answer == "yes" else "no"
    log("Questions", {"helpful": answer}, update_id=log_id)
    log("Feedback", {"student_code": student(), "question_log_id": log_id, "helpful": answer,
                              "comment": request.form.get("comment", "")[:300]})
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    flash_t("thanks")
    return redirect(url_for("ask"))


# ------------------------------------------------------------------ Practice
def next_question(topic, done):
    bank = S()["bank"]
    pool = bank[bank.topic == topic] if topic else bank
    if pool.empty:
        pool = bank
    left = pool[~pool.q_id.isin(done)]
    if left.empty:
        left = pool
    return left.sample(1, random_state=random.randint(0, 10**6)).iloc[0].q_id


def keyword_match(answer, keywords):
    keys = [k.strip().lower() for k in str(keywords).split(";") if k.strip()]
    if not keys or not answer.strip():
        return None
    a = answer.lower()
    hit = [k for k in keys if k in a or all(w in a for w in k.split())]
    return {"hit": len(hit), "total": len(keys), "found": hit}


@app.route("/practice", methods=["GET", "POST"])
@student_required
def practice():
    p = session.get("practice")
    topic = request.args.get("topic")
    if p is not None and p.get("course") != course_code():
        p = None
    if request.method == "GET" and request.args.get("mode") == "mistakes":
        ids = my_mistakes()
        if not ids:
            return redirect(url_for("practice"))
        p = {"topic": None, "review": True, "queue": ids, "total": len(ids), "fixed": 0, "done": [], "count": 0, "goal": len(ids),
             "course": course_code(), "q_id": ids[0], "hints": 0, "stage": "ask", "answer": ""}
        session["practice"] = p
        visit("practice")
    elif request.method == "GET" and (p is None or topic is not None and topic != p.get("topic") or (p.get("review") and request.args.get("new"))):
        if topic is None:
            topic, _ = study_next(my_mastery(), S()["topics"], lang())
        p = {"topic": topic, "done": [], "count": 0, "goal": 5, "course": course_code()}
        p.update({"q_id": next_question(topic, []), "hints": 0, "stage": "ask", "answer": ""})
        session["practice"] = p
        visit("practice")

    if request.method == "POST":
        action = request.form.get("action")
        if p is None or p.get("stage") == "finished":
            return redirect(url_for("practice"))
        if action == "hint" and p["hints"] < 2:
            p["hints"] += 1
        elif action == "check":
            p["answer"] = request.form.get("answer", "")[:1000]
            p["stage"] = "check"
        elif action == "reveal":
            p["stage"] = "check"
        elif action in ("right", "wrong"):
            correct = action == "right"
            q_topic = S()["qid_topic"][p["q_id"]]
            old = my_mastery().get(q_topic, 0.0)
            new = M.update(old, correct, p["hints"])
            log("Answers", {"student_code": student(), "question_id": p["q_id"], "topic": q_topic,
                                     "correct": int(correct), "hints_used": p["hints"], "mastery_after": new})
            award()
            p["done"].append(p["q_id"])
            p["count"] += 1
            p["last"] = {"correct": correct, "old": round(old * 100), "new": round(new * 100),
                         "colour": M.colour(new)}
            if p.get("review"):                                    # mistakes review: go through the wrong ones one by one
                p["queue"] = p["queue"][1:]
                p["fixed"] += int(correct)
                if p["queue"]:
                    p.update({"q_id": p["queue"][0], "hints": 0, "stage": "ask", "answer": ""})
                else:
                    p.update({"hints": 0, "stage": "finished", "answer": ""})
            else:
                p.update({"q_id": next_question(p["topic"], p["done"]), "hints": 0, "stage": "ask", "answer": ""})
        session["practice"] = p
        return redirect(url_for("practice"))

    q = S()["bank"].set_index("q_id").loc[p["q_id"]]
    match = keyword_match(p.get("answer", ""), q.keywords) if p["stage"] == "check" else None
    topics = [{"topic": r.topic, "name": r.name_ar if lang() == "ar" else r["name"]} for _, r in S()["topics"].iterrows()]
    last = p.pop("last", None)
    session["practice"] = p
    return render_template("practice.html", p=p, q=q, match=match, topics=topics, last=last, mistakes=len(my_mistakes()),
                           topic_name=tr("review_title", lang()) if p.get("review") else topic_name(p["topic"], tr("all_topics", lang())))


# ------------------------------------------------------------------ Badges
@app.route("/badges")
@student_required
def badges_page():
    visit("badges")
    allb = award()
    code = student()
    fresh = badges.unseen_ids(code)
    badges.mark_seen(code)
    special = _special_cards(code)
    custom_badges.mark_seen(code)
    groups = []
    for g in GROUP_ORDER:
        items = [dict(b, new=b["id"] in fresh) for b in allb if b["group"] == g]
        groups.append({"id": g, "name": badges.GROUP_NAMES[g][1 if lang() == "ar" else 0], "items": items,
                       "got": sum(b["earned"] for b in items)})
    if special:
        groups.append({"id": "special", "name": tr("bg_special", lang()), "items": special, "got": sum(b["earned"] for b in special)})
    everything = allb + special
    done = [b for b in everything if b["earned"]]
    todo = sorted([b for b in allb if not b["earned"] and b["value"]], key=lambda b: -b["pct"])
    return render_template("badges.html", groups=groups, total=len(everything), got=len(done), nxt=todo[0] if todo else None,
                           latest=sorted(done, key=lambda b: b["when"])[-1] if done else None)


# ------------------------------------------------------------------ Progress
@app.route("/progress")
@student_required
def progress():
    visit("progress")
    m = my_mastery()
    items, nxt = topic_panel(m)
    answers = [a for a in read_sheet("Answers") if a.get("student_code") == student() and a.get("course") == course_code()]
    stats = {"answered": len(answers), "correct": sum(str(a["correct"]) in ("1", "True") for a in answers),
             "green": sum(i["colour"] == "green" for i in items), "total": len(items)}
    return render_template("progress.html", items=items, nxt=nxt, stats=stats, reviews=my_reviews(m))


# ------------------------------------------------------------------ Help / questions
@app.route("/help", methods=["GET", "POST"])
def help_page():
    staff = bool(session.get("lecturer"))
    if request.method == "POST":
        if staff:
            if request.form.get("action") == "delete":
                faq.delete(request.form.get("id", ""))
            elif request.form.get("action") == "add":
                f = request.form
                if not faq.add(f.get("q_en", ""), f.get("a_en", ""), f.get("q_ar", ""), f.get("a_ar", "")):
                    flash_t("faq_need_both")
        return redirect(url_for("help_page"))
    return render_template("help.html", faq_items=faq.items(lang()), staff=staff, method=session.get("method", "tfidf"))


# ------------------------------------------------------------------ AI models (hidden; main admin + a password)
@app.route("/models/unlock", methods=["POST"])
@lecturer_required
def models_unlock():
    if not is_main():
        return redirect(url_for("profile"))
    if modelspw.verify(request.form.get("pw", "")):
        session["models_ok"] = True
        return redirect(url_for("evaluation"))
    flash_t("mdl_wrong")
    return redirect(url_for("profile"))


@app.route("/models/lock", methods=["POST"])
@lecturer_required
def models_lock():
    session.pop("models_ok", None)
    return redirect(url_for("profile"))


@app.route("/models/evaluate", methods=["POST"])
@lecturer_required
def models_evaluate():
    if is_main() and session.get("models_ok"):
        flash_t("mdl_eval_done" if autoeval.safe_run(course_code()) else "mdl_eval_fail")
    return redirect(url_for("evaluation"))


@app.route("/models/notebook", methods=["POST"])
@lecturer_required
def models_notebook():
    """Import the results of a Google Colab notebook (zip or json) and, when it brings figure text, rebuild the index."""
    if not (is_main() and session.get("models_ok") and can_manage(course_code())):
        return redirect(url_for("admin"))
    code = course_code()
    f = request.files.get("file")
    res = nbresults.import_results(code, f.filename, f.read()) if f and f.filename else None
    if not res:
        flash_t("nbr_bad")
        return redirect(url_for("evaluation"))
    if res["figures"]:
        try:
            rebuild_course(code)
        except Exception:                                    # noqa: BLE001 - the results are saved even if the rebuild fails
            flash_t("nbr_rebuild_fail")
    autoeval.safe_run(code)
    flash_t("nbr_imported", n=len(res["kinds"]), f=res["figures"])
    return redirect(url_for("evaluation"))


@app.route("/models/password", methods=["POST"])
@lecturer_required
def models_password():
    if is_main() and session.get("models_ok"):
        err = modelspw.change(request.form.get("old", ""), request.form.get("new", ""))
        flash_t(err or "mdl_pw_changed", n=modelspw.MIN_LEN)
    return redirect(url_for("evaluation"))


def rebuild_course(code):
    """Read the lecture PDFs again and rebuild the search index of one course. Returns (slides, lectures)."""
    full = any(c["full"] for c in config.list_courses() if c["code"] == code)
    if not full:
        from core.autocourse import regenerate
        rep = regenerate(code)
        load_state(code)
        return rep["slides"], rep["lectures"]
    from core.passages import build_passages
    clf = (STATE.get(code) or load_state(code))["clf"]
    df = build_passages(predict_topic=lambda text: clf.predict(text)[0], verbose=False, course=code)
    build_index(df, course=code)
    load_state(code)
    return len(df), int(df.lecture.nunique())


@app.route("/evaluation")
@lecturer_required
def evaluation():
    if not is_main() or not can_manage(course_code()):          # main admin only, and only after the models password
        return redirect(url_for("admin"))
    if not session.get("models_ok"):
        return redirect(url_for("profile"))
    visit("evaluation")
    P = config.course_paths(course_code())
    path = P.reports / "metrics.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    ae, nb = autoeval.load(course_code()), nbresults.load(course_code())
    short = slides = 0
    if P.passages.exists():
        import pandas as pd
        txt = pd.read_csv(P.passages)["text"].astype(str)
        slides, short = len(txt), int((txt.str.len() < nbresults.SHORT_SLIDE).sum())
    return render_template("evaluation.html", r=report, rep_url=P.reports_url, ae=ae, nb=nb,
                           advice=nbresults.advise(ae, nb, short, slides), colab={k: nbresults.colab_url(k) for k in nbresults.NOTEBOOKS},
                           auto=not any(c["full"] for c in config.list_courses() if c["code"] == course_code()))


# ------------------------------------------------------------------ Lecturer: login, dashboard, admin
_FAILS = {}                                         # typed username/e-mail -> (count, first_time)
MAX_TRIES, LOCK_SECONDS = 5, 900


def _key():
    return (request.form.get("username", "") or "admin").strip().lower()[:80]


def _locked(key):
    import time
    n, t0 = _FAILS.get(key, (0, 0))
    if n >= MAX_TRIES and time.time() - t0 < LOCK_SECONDS:
        return True
    if n >= MAX_TRIES:
        _FAILS.pop(key, None)
    return False


@app.route("/lecturer", methods=["GET", "POST"])
def lecturer_login():
    if request.method == "POST":
        r = handle_login(None)
        if r:
            return r
    return render_template("lecturer_login.html")


@app.route("/overview")
@lecturer_required
def staff_home():
    """Home page of the admin (site-wide numbers) and of a doctor (his courses and students)."""
    import datetime as _dt
    visit("overview")
    master = is_master()
    courses = [c for c in config.list_courses() if can_manage(c["code"])]
    for c in courses:
        check_risk(c["code"])
    ar = lang() == "ar"
    title = {c["code"]: (c["name_ar"] or c["name_en"]) if ar else c["name_en"] for c in config.list_courses()}
    rows = students_for_admin()
    per_course = Counter(c[0] for r in rows for c in r["courses"])
    by_course = [{"code": c["code"], "title": title[c["code"]], "n": per_course.get(c["code"], 0)} for c in courses]
    mine = {c["code"] for c in courses}
    visits = read_sheet("Visits") if master else [v for v in read_sheet("Visits") if v.get("course") in mine]
    days = [str(v.get("time", ""))[:10] for v in visits]
    td = _dt.date.today()
    start = td - _dt.timedelta(days=(td.weekday() + 2) % 7)          # week starts on Saturday
    cnt = Counter(days)
    wk = [{"day": (start + _dt.timedelta(days=i)).day, "n": cnt.get((start + _dt.timedelta(days=i)).isoformat(), 0),
           "today": start + _dt.timedelta(days=i) == td} for i in range(7)]
    wmax = max([w["n"] for w in wk] + [1])
    for w in wk:
        w["h"] = round(100 * w["n"] / wmax)
    exams = [e for e in read_sheet("Exams") if master or e.get("course") in mine]
    qs = [q for q in read_sheet("Questions") if master or q.get("course") in mine]
    docs = doctors.list_doctors("doctor")
    adm_list = doctors.list_doctors("admin") if is_main() else []
    stats = {"courses": len(courses), "students": len(rows), "visits": len(visits),
             "visitors": len({v.get("student_code") for v in visits if v.get("student_code")}),
             "doctors": len(docs), "admins": len(docs) + len(adm_list) + 1, "exams": len(exams), "asked": len(qs)}
    team = [{"name": d["name"], "courses": courses_of(d["id"]) or "–"} for d in docs] if master else []
    recent = sorted(rows, key=lambda r: str(r.get("created", "")), reverse=True)[:5]
    hour = _dt.datetime.now().hour
    greet = "gm" if hour < 12 else "ga" if hour < 18 else "ge"
    name = tr("role_admin", lang()) if master else session.get("admin_name") or tr("role_doctor", lang())
    return render_template("staff_home.html", stats=stats, week=wk, week_total=sum(w["n"] for w in wk), master=master,
                           by_course=by_course, team=team, admins_list=adm_list, main_admin=is_main(), recent=recent, greet=greet, name=name,
                           today=td.isoformat(), courses=courses, events=_calendar_events())


# ------------------------------------------------------------------ doctors / courses overview pages (admin + doctor home cards)
@app.route("/doctors")
@lecturer_required
def doctors_page():
    if not (is_main() or (is_subadmin() and has_perm("doctors"))):
        return redirect(url_for("staff_home"))
    allc = config.list_courses()
    owned = {}
    for c in allc:
        owned.setdefault(c["meta"].get("owner"), []).append(c["code"])
    per = Counter(c[0] for r in students_for_admin() for c in r["courses"])
    rows = []
    for d in doctors.list_doctors("doctor"):
        mine = owned.get(d["id"], [])
        rows.append({**d, "courses": mine, "students": sum(per.get(c, 0) for c in mine), "avatar": profiles.avatar_path("d:" + d["id"]) is not None,
                     "key": profiles.safe("d:" + d["id"])})
    return render_template("doctors.html", rows=rows, main={"name": session.get("admin_name") or tr("role_admin", lang()), "key": "d:" + doctors.MASTER})


# ------------------------------------------------------------------ extra admins (main admin only): name, username, password, permissions
PERM_LABEL = {"content": "adms_p_content", "exams": "adms_p_exams", "badges": "adms_p_badges", "data": "adms_p_data",
              "students": "adms_p_students", "chat": "adms_p_chat", "support": "adms_p_support", "doctors": "adms_p_doctors"}


@app.route("/admins", methods=["GET", "POST"])
@lecturer_required
def admins_page():
    if not is_main():
        flash_t("master_only")
        return redirect(url_for("staff_home"))
    if request.method == "POST":
        action = request.form.get("action", "")
        picked = [p for p in request.form.getlist("perms") if p in doctors.PERMS]
        if action == "add_admin":
            name = request.form.get("admin_name", "").strip()
            user = request.form.get("admin_user", "").strip()
            pw = request.form.get("admin_pw", "").strip()
            if not (name and user and pw):
                flash_t("adms_need_all")
            else:
                try:
                    did, _pw = doctors.add(name, "", user, pw, role="admin", perms=picked)
                    flash_t("adms_added", name=name, user=user)
                    sync_sheet()
                except ValueError as e:
                    flash_t(str(e), n=doctors.MIN_LEN)
        elif action == "set_perms":
            if doctors.set_perms(request.form.get("admin", ""), picked):
                flash_t("adms_saved")
        elif action == "reset_admin":
            new = request.form.get("new", "").strip()
            a = doctors.get(request.form.get("admin", ""))
            if a and a["role"] == "admin":
                if len(new) < doctors.MIN_LEN:
                    flash_t("pw_too_short", n=doctors.MIN_LEN)
                else:
                    doctors.set_password(a["id"], new)
                    flash_t("adms_pw_set", user=a["username"])
        elif action == "make_admin":                                      # a registered student becomes an admin
            st = students.get(request.form.get("student", ""))
            if st:
                did = doctors.add_linked(st, picked)
                notify.push(["s:" + st["code"], "d:" + did], "security", tr("adms_note_title", lang()), tr("adms_note_body", lang()), url_for("staff_home"))
                flash_t("adms_made", name=f"{st['first']} {st['last']}".strip())
        elif action == "delete_admin":
            a = doctors.get(request.form.get("admin", ""))
            if a and a["role"] == "admin":
                doctors.remove(a["id"])
                if a.get("student"):
                    notify.push(["s:" + a["student"]], "security", tr("adms_note_off_title", lang()), tr("adms_note_off_body", lang()), url_for("student_home"))
                flash_t("adms_deleted")
        q = request.form.get("q", "")
        kw = {"q": q} if q else {}
        if request.args.get("embed") or request.headers.get("Sec-Fetch-Dest") == "iframe":
            kw["embed"] = 1
        return redirect(url_for("admins_page", **kw))
    q = request.args.get("q", "").strip().lower()
    allst = sorted(students.list_students(), key=lambda x: str(x.get("created", "")), reverse=True)
    hits = [x for x in allst if not q or q in f"{x['first']} {x['last']} {x['username']} {x['email']} {x['code']}".lower()]
    people = [{**x, "admin": doctors.by_student(x["code"])} for x in hits[:10]]
    return render_template("admins.html", rows=doctors.list_doctors("admin"), perms=doctors.PERMS, labels=PERM_LABEL, pw_min=doctors.MIN_LEN,
                           people=people, q=request.args.get("q", ""), total_students=len(allst), found=len(hits))


@app.route("/all-courses")
@lecturer_required
def all_courses():
    per = Counter(c[0] for r in students_for_admin() for c in r["courses"])
    names = {d["id"]: d["name"] for d in doctors.list_doctors()}
    rows = []
    for c in config.list_courses():
        if not can_manage(c["code"]):
            continue
        try:
            nq = len(EX.load_bank(c["code"])["questions"])
        except Exception:
            nq = 0
        rows.append({"code": c["code"], "title": (c["name_ar"] or c["name_en"]) if lang() == "ar" else c["name_en"],
                     "doctor": names.get(c["meta"].get("owner"), ""), "lectures": c["lectures"], "slides": c["slides"],
                     "students": per.get(c["code"], 0), "questions": nq})
    return render_template("courses_overview.html", rows=rows, master=is_master())


# ------------------------------------------------------------------ profile (student, doctor, admin)
@app.route("/avatar/<key>")
def avatar(key):
    from flask import send_file, abort
    if not (session.get("lecturer") or student()):
        abort(404)
    p = profiles.avatar_path(key)
    if not p:
        abort(404)
    r = send_file(p, mimetype="image/jpeg")
    r.headers["Cache-Control"] = "private, max-age=3600"
    return r


@app.route("/profile", methods=["GET", "POST"])
def profile():
    key = user_key()
    if not key:
        return redirect(url_for("start", next=request.path))
    is_staff = key.startswith("d:")
    if request.method == "POST":
        action = request.form.get("action")
        if action == "photo":
            f = request.files.get("photo")
            err = profiles.save_avatar(key, f) if f and f.filename else "photo_missing"
            flash_t(err or "photo_saved")
        elif action == "photo_remove":
            profiles.remove_avatar(key)
            flash_t("photo_removed")
        elif action == "info":
            if is_staff:
                name, email = request.form.get("name", "").strip(), request.form.get("email", "").strip()
                if key == "d:" + doctors.MASTER:
                    profiles.update(key, name=name[:60], email=email[:120])
                else:
                    doctors.update_profile(admin_id(), name, email)
                    session["admin_name"] = (name or session.get("admin_name", ""))[:60]
                    sync_sheet()
                flash_t("profile_saved")
            else:
                err = students.update_profile(key[2:], request.form.get("first", ""), request.form.get("last", ""), request.form.get("email", ""))
                if not err:
                    session["student_name"] = request.form.get("first", "").strip()[:40]
                flash_t(err or "profile_saved")
        elif action == "password":
            new = request.form.get("new", "")
            if key == "d:" + doctors.MASTER:
                if new != request.form.get("confirm", ""):
                    flash_t("pw_mismatch")
                else:
                    err = adminpw.change(request.form.get("old", ""), new)
                    if not err:
                        notify.push([key], "security", tr("n_pw_title", lang()), tr("n_pw_body", lang()), url_for("profile"))
                    flash_t(err or "pw_changed", n=adminpw.MIN_LEN)
            elif new != request.form.get("confirm", ""):
                flash_t("pw_mismatch")
            else:
                err = (doctors.change_password(admin_id(), request.form.get("old", ""), new, config.LECTURER_PASSWORD) if is_staff
                       else students.change_password(key[2:], request.form.get("old", ""), new))
                if err:
                    flash_t(err, n=doctors.MIN_LEN)
                else:
                    if is_staff:
                        sync_sheet()
                    notify.push([key], "security", tr("n_pw_title", lang()), tr("n_pw_body", lang()), url_for("profile"))
                    flash_t("pw_changed")
        elif action == "delete_account":
            pw = request.form.get("pw", "")
            if key == "d:" + doctors.MASTER:
                flash_t("del_master")
            else:
                if is_staff:
                    d = doctors.get(admin_id())
                    ok = bool(d) and doctors.check(pw, doctors.username_of(d)) == d["id"]
                else:
                    ok = students.verify(key[2:], pw)
                if not ok:
                    flash_t("del_wrong_pw")
                else:
                    (accountdel.delete_doctor(admin_id()) if is_staff else accountdel.delete_student(key[2:]))
                    if is_staff:
                        sync_sheet()
                    keep = {k: session.get(k) for k in ("course", "lang", "theme") if session.get(k)}
                    session.clear()
                    session.update(keep)
                    flash_t("del_done")
                    return redirect(url_for("start"))
        return redirect(url_for("profile"))
    if is_staff:
        if key == "d:" + doctors.MASTER:
            info = {"name": profiles.get(key).get("name", "") or session.get("admin_name") or "Admin", "email": profiles.get(key).get("email", ""), "username": "admin", "code": ""}
        else:
            d = doctors.get(admin_id()) or {}
            info = {"name": d.get("name", ""), "email": d.get("email", ""), "username": d.get("username", ""), "code": ""}
    else:
        st = students.get(key[2:]) or {}
        info = {"first": st.get("first", ""), "last": st.get("last", ""), "email": st.get("email", ""), "username": st.get("username", ""), "code": st.get("code", "")}
    return render_template("profile.html", info=info, is_staff=is_staff, is_master_user=key == "d:" + doctors.MASTER)


# ------------------------------------------------------------------ notifications
@app.route("/notifications")
def notifications_page():
    key = user_key()
    if not key:
        return redirect(url_for("start", next=request.path))
    items = notify.for_user(key, 80)
    notify.mark_read(key)                       # opening the page = reading them (the "new" tags still show once)
    return render_template("notifications.html", items=items)


@app.route("/notifications/read", methods=["POST"])
def notifications_read():
    key = user_key()
    if key:
        try:
            nid = int(request.form.get("id", ""))
        except ValueError:
            nid = None
        notify.mark_read(key, nid)
    return redirect(request.form.get("next") or request.referrer or url_for("notifications_page"))


# ------------------------------------------------------------------ calendar (scheduled exams + exams taken)
def _calendar_events():
    key = user_key()
    ar = lang() == "ar"
    title_of = {c["code"]: (c["name_ar"] or c["name_en"]) if ar else c["name_en"] for c in config.list_courses()}
    names = {s["code"]: (s["first"] + " " + s["last"]).strip() for s in students.list_students()}
    ev = []
    if session.get("lecturer"):
        codes = [c["code"] for c in config.list_courses() if can_manage(c["code"])]
    else:
        codes = [c for c in (student_course_list() or []) if c in title_of]
    for it in SCH.for_courses(codes):
        d, t = it["when"].split("T")
        ev.append({"date": d, "time": t, "kind": "scheduled", "title": it["title"], "sub": it["note"], "course": title_of.get(it["course"], it["course"]),
                   "id": it["id"], "mine": session.get("lecturer") and can_manage(it["course"])})
    import datetime as _dt
    for c in codes:
        for a in EX.list_attempts(c, None if session.get("lecturer") else key[2:])[:300]:
            when = _dt.datetime.fromtimestamp(a["started"])
            who = "" if not session.get("lecturer") else names.get(a["student"], a["student"])
            res = (f"{'%g' % a['score']}/{a['max']} · {a['pct']}%") if a["status"] == "done" else tr("cal_in_progress", lang())
            ev.append({"date": when.strftime("%Y-%m-%d"), "time": when.strftime("%H:%M"), "kind": "attempt",
                       "title": (who + " · " if who else "") + tr("cal_practice_exam", lang()), "sub": res, "course": title_of.get(c, c),
                       "link": (url_for("exams_attempt", aid=a["id"]) if session.get("lecturer") else url_for("exams_result", aid=a["id"])) if a["status"] == "done" else ""})
    return ev


@app.route("/calendar", methods=["GET", "POST"])
def calendar_page():
    key = user_key()
    if not key:
        return redirect(url_for("start", next=request.path))
    managed = [c for c in config.list_courses() if can_manage(c["code"])] if session.get("lecturer") else []
    if request.method == "POST" and session.get("lecturer"):
        action = request.form.get("action")
        if action == "add":
            code = request.form.get("course", "")
            if not can_manage(code):
                flash_t("cal_bad_course")
            else:
                item = SCH.add(code, request.form.get("title", ""), request.form.get("when", ""), request.form.get("note", ""), admin_id() or "")
                if not item:
                    flash_t("cal_bad_date")
                else:
                    ctitle = next(((c["name_ar"] or c["name_en"]) if lang() == "ar" else c["name_en"] for c in managed if c["code"] == code), code)
                    to = [f"s:{s['code']}" for s in students.list_students() if code in s["courses"]] + ["d:" + doctors.MASTER, "d:" + (course_owner(code) or doctors.MASTER)]
                    notify.push(to, "exam", tr("n_exam_title", lang(), course=ctitle), tr("n_exam_body", lang(), title=item["title"], when=item["when"].replace("T", " ")), url_for("calendar_page"))
                    flash_t("cal_added")
        elif action == "delete":
            try:
                it = SCH.get(int(request.form.get("id", "")))
            except ValueError:
                it = None
            if it and can_manage(it["course"]):
                SCH.remove(it["id"])
                flash_t("cal_deleted")
        return redirect(url_for("calendar_page"))
    l = lang()
    return render_template("calendar.html", events=_calendar_events(), managed=[{"code": c["code"], "title": (c["name_ar"] or c["name_en"]) if l == "ar" else c["name_en"]} for c in managed],
                           staff=bool(session.get("lecturer")))


@app.route("/dashboard")
@lecturer_required
@perm_required("data")
def dashboard():
    if not can_manage(course_code()):
        return redirect(url_for("admin"))
    visit("dashboard")
    names = S()["names_ar"] if lang() == "ar" else S()["names"]
    cc = course_code()
    qs, ans, visits = [[r for r in read_sheet(s) if r.get("course") == cc] for s in ("Questions", "Answers", "Visits")]
    asked = Counter(q["topic"] for q in qs if q.get("topic") in names)
    score = defaultdict(list)
    for a in ans:
        if a["topic"] in names:
            score[a["topic"]].append(1 if str(a["correct"]) in ("1", "True") else 0)
    avg = {t: round(100 * sum(v) / len(v)) for t, v in score.items() if v}
    order = list(names)
    helpful = [q["helpful"] for q in qs if q.get("helpful") in ("yes", "no")]
    per_day = Counter(str(v["time"])[:10] for v in visits)
    not_found = [q for q in qs if q.get("found") == "no"][-10:][::-1]
    fu = followup.load()
    latest = [{**q, "fu": fu.get(str(q.get("id")))} for q in qs[-60:][::-1]]
    # mastery per student -> how many students are red / amber / green per topic
    codes = sorted({a["student_code"] for a in ans})
    colours = {t: Counter() for t in order}
    for c in codes:
        m = M.replay([a for a in ans if a["student_code"] == c], S()["qid_topic"])
        for t in order:
            if t in m:
                colours[t][M.colour(m[t])] += 1
    data = {
        "asked_labels": [names[t] for t, _ in asked.most_common()],
        "asked_values": [n for _, n in asked.most_common()],
        "score_labels": [names[t] for t in sorted(avg, key=avg.get)],
        "score_values": [avg[t] for t in sorted(avg, key=avg.get)],
        "days": sorted(per_day), "visits": [per_day[d] for d in sorted(per_day)],
        "colour_labels": [names[t] for t in order],
        "red": [colours[t]["red"] for t in order], "amber": [colours[t]["amber"] for t in order],
        "green": [colours[t]["green"] for t in order],
    }
    kpi = {"questions": len(qs), "students": len({q["student_code"] for q in qs} | set(codes)),
           "answers": len(ans), "helpful": round(100 * helpful.count("yes") / len(helpful)) if helpful else None,
           "not_found": sum(q.get("found") == "no" for q in qs),
           "answered": sum(1 for q in qs if str(q.get("id")) in fu), "open": sum(1 for q in qs if str(q.get("id")) not in fu)}
    lowest = [{"name": names[t], "avg": avg[t], "n": len(score[t])} for t in sorted(avg, key=avg.get)[:3]]
    top = [{"name": names[t], "n": n} for t, n in asked.most_common(3)]
    risk = course_risk(cc, qs, ans, visits)
    return render_template("dashboard.html", data=data, kpi=kpi, lowest=lowest, top=top, not_found=not_found, latest=latest,
                           unanswered=insights.unanswered(qs), risk=risk, inactive_days=insights.INACTIVE_DAYS)


def course_students(code):
    return [s for s in students.list_students() if code in (s.get("courses") or [])]


def course_risk(code, qs=None, ans=None, visits=None):
    """Registered students of a course who need attention (low level or inactive)."""
    if qs is None:
        qs, ans, visits = [[r for r in read_sheet(s) if r.get("course") == code] for s in ("Questions", "Answers", "Visits")]
    st = STATE.get(code) or load_state(code)
    return insights.at_risk(code, course_students(code), qs, ans, visits, M.replay, st["qid_topic"], len(st["topics"]))


def check_risk(code):
    """Once a day per course: tell the course owner (or the main admin) about students who newly need attention."""
    if insights.notified_today(code):
        return
    try:
        rows = course_risk(code)
        owner = course_owner(code)
        title = tr("risk_n_title", lang(), course=course_title(code))
        insights.notify_at_risk(code, rows, ["d:" + (owner or doctors.MASTER)], notify.push, title,
                                lambda new: ", ".join(r["name"] for r in new[:5]) + (" …" if len(new) > 5 else ""), url_for("dashboard") + "#risk")
    except Exception as e:                                   # noqa: BLE001 - a notice must never break a page
        print("at-risk check skipped:", type(e).__name__, e)


@app.route("/dashboard/remind", methods=["POST"])
@lecturer_required
@perm_required("data")
def dashboard_remind():
    code, who = course_code(), request.form.get("student", "")
    if can_manage(code) and any(s["code"] == who for s in course_students(code)):
        notify.push(["s:" + who], "study", tr("remind_title", lang(), course=course_title(code)), tr("remind_body", lang()), url_for("progress"))
        flash_t("remind_sent")
    return redirect(url_for("dashboard") + "#risk")


@app.route("/dashboard/followup", methods=["POST"])
@lecturer_required
@perm_required("data")
def dashboard_followup():
    if can_manage(course_code()):
        qid = request.form.get("id", "")
        if request.form.get("action") == "reopen":
            followup.reopen(qid)
        elif qid:
            followup.mark(qid, session.get("admin_name") or "Admin", request.form.get("note", ""))
    return redirect(url_for("dashboard") + "#followup")


@app.route("/dashboard/logs.xlsx")
@lecturer_required
@perm_required("data")
def download_logs():
    from flask import send_file
    ensure_workbook()
    if is_master():
        return send_file(config.LOGS_XLSX, as_attachment=True, download_name="logs.xlsx")
    import io
    mine = {c["code"] for c in visible_courses()}           # a doctor gets only the rows of his own courses
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        from core.logger import SHEETS
        for sheet, cols in SHEETS.items():
            rows = [r for r in read_sheet(sheet) if r.get("course") in mine]
            pd.DataFrame(rows, columns=cols).to_excel(xw, sheet_name=sheet, index=False)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="logs.xlsx")


def courses_of(doctor_id):
    return ", ".join(c["code"] for c in config.list_courses() if c["meta"].get("owner") == doctor_id)


def sync_sheet(wait=False):
    """Copy the doctors table to the admin's Google Sheet (in the background)."""
    sheet_sync.push(doctors.sheet_rows(courses_of), wait=wait)


def sheet_view():
    if not is_main():
        return None
    return {"rows": doctors.sheet_rows(courses_of), "enabled": sheet_sync.enabled(), "status": sheet_sync.STATUS,
            "google": sheet_sync.SHOW_GOOGLE or sheet_sync.enabled(), "email": sheet_sync.service_email(), "url": sheet_sync.sheet_url(), "header": sheet_sync.HEADER}


@app.route("/admin", methods=["GET", "POST"])
@lecturer_required
@perm_required("content")
def admin():
    if is_master() and request.method == "GET":                # complete the names of codes whose course is already uploaded
        have = {r["code"] for r in catalog.load()}
        catalog.sync([{"code": c["code"], "name_en": c["name_en"], "name_ar": c["name_ar"]} for c in config.list_courses() if c["code"] in have])
    code = course_code()
    P = config.course_paths(code)
    full = any(c["full"] for c in config.list_courses() if c["code"] == code)
    mine = can_manage(code)                                  # a doctor with no course yet can only add one
    if request.method == "POST":
        action = request.form.get("action")
        if action == "import_codes":                          # bring the uploaded courses into the list
            if is_master():
                flash_t("codes_imported", n=sync_codes_from_courses())
            return redirect(url_for("admin"))
        if action in ("upload_codes", "clear_codes"):        # the admin's list of course codes (Excel)
            if is_master():
                if action == "clear_codes":
                    catalog.save([])
                    flash_t("codes_cleared")
                else:
                    f = request.files.get("codes")
                    try:
                        rows = catalog.parse_xlsx(f.read()) if f and f.filename else []
                        if not rows:
                            raise ValueError("empty")
                        catalog.save(rows)
                        flash_t("codes_saved", n=len(rows))
                    except Exception:
                        flash_t("codes_bad")
            return redirect(url_for("admin"))
        if action == "change_password":                      # a doctor changes his own password
            if is_main() or not admin_id():
                flash_t("pw_master_note")
                return redirect(url_for("admin"))
            new = request.form.get("new", "")
            if new != request.form.get("confirm", ""):
                flash_t("pw_mismatch")
            else:
                err = doctors.change_password(admin_id(), request.form.get("old", ""), new, config.LECTURER_PASSWORD)
                if err:
                    flash_t(err, n=doctors.MIN_LEN)
                else:
                    sync_sheet()
                    flash_t("pw_changed")
            return redirect(url_for("admin"))
        if action in ("add_doctor", "reset_doctor", "delete_doctor", "set_owner", "sync_sheet"):
            if not is_main():
                flash_t("master_only")
                return redirect(url_for("admin"))
            if action == "add_doctor":
                name = request.form.get("doctor_name", "").strip()
                email = request.form.get("doctor_email", "").strip()
                if name:
                    try:
                        did, new_code = doctors.add(name, email, request.form.get("doctor_username", "").strip())
                    except ValueError as e:
                        flash_t(str(e), n=doctors.MIN_LEN)
                        return redirect(url_for("admin"))
                    flash_t("doctor_added", name=name, code=new_code)
                    flash(f"{tr('doctor_username', lang())}: {doctors.get(did)['username']}")
                    if email and mailer.send(email, "StudyMate - your doctor account",
                                             f"Hello {name},\n\nUsername: {doctors.get(did)['username']}\n"
                                             f"Password: {new_code}\n\nSign in at the site's login page and change the password from the Admin page."):
                        flash_t("doctor_mailed", email=email)
            elif action == "reset_doctor":
                new_code = doctors.reset(request.form.get("doctor", ""))
                if new_code:
                    flash_t("doctor_reset", code=new_code)
                    d = doctors.get(request.form.get("doctor", ""))
                    if d and d["email"] and mailer.send(d["email"], "StudyMate - new password",
                                                        f"Your new password: {new_code}\nUsername: {d['username']}"):
                        flash_t("doctor_mailed", email=d["email"])
            elif action == "delete_doctor":
                did = request.form.get("doctor", "")
                doctors.remove(did)
                for c in config.list_courses():              # his courses go back to the main admin
                    if c["meta"].get("owner") == did:
                        meta = dict(c["meta"]); meta.pop("owner", None)
                        (config.BASE_DIR / "data" / c["code"] / "course.json").write_text(
                            json.dumps(meta, ensure_ascii=False), encoding="utf-8")
                flash_t("doctor_deleted")
            elif action == "set_owner":
                did = request.form.get("owner", "")
                info = config.course_paths(code).info
                meta = json.loads(info.read_text(encoding="utf-8"))
                if did and doctors.get(did):
                    meta["owner"] = did
                else:
                    meta.pop("owner", None)
                info.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
                flash_t("owner_set")
            if action == "sync_sheet":
                if not sheet_sync.enabled():
                    flash_t("sheet_not_connected")
                else:
                    sync_sheet(wait=True)
                    flash_t("sheet_synced" if sheet_sync.STATUS.get("ok") else "sheet_failed", err=sheet_sync.STATUS.get("error", ""))
            else:
                sync_sheet()
            return redirect(url_for("admin"))
        if action != "add_course" and not (mine and code):
            flash_t("not_your_course")
            return redirect(url_for("admin"))
        if action == "add_course":
            from core.autocourse import build_course, clean_code
            if not is_master() and len([c for c in config.list_courses() if c["meta"].get("owner") == admin_id()]) >= config.MAX_COURSES_PER_DOCTOR:
                flash_t("too_many_courses", n=config.MAX_COURSES_PER_DOCTOR)
                return redirect(url_for("admin"))
            files = [(f.filename, f.read()) for f in request.files.getlist("pdfs") if f.filename.lower().endswith(".pdf")]
            raw_code = request.form.get("code", "")
            if raw_code == "__other__" and is_master():
                raw_code = request.form.get("code_custom", "")
            listed = catalog.lookup(clean_code(raw_code))
            if catalog.load() and not listed and not (is_master() and request.form.get("code") == "__other__"):
                flash_t("code_not_listed")                      # a doctor can only use the codes the admin listed
                return redirect(url_for("admin"))
            try:
                owner = admin_id() if not is_master() else (request.form.get("owner") or None)
                rep = build_course(raw_code, request.form.get("name_en", "").strip() or (listed or {}).get("name_en", ""),
                                   request.form.get("name_ar", "").strip() or (listed or {}).get("name_ar", ""), files, owner=owner)
                load_state(rep["code"])
                session["course"] = rep["code"]
                session.pop("practice", None)
                if catalog.load():                               # a codes list is in use: the new course shows up in it at once
                    sync_codes_from_courses()
                sync_sheet()
                flash_t("course_created", name=request.form.get("name_en") or (listed or {}).get("name_en") or rep["code"], n=rep["slides"],
                        m=rep["lectures"], q=rep["questions"])
            except FileExistsError:
                flash_t("course_exists")
            except ValueError:
                flash_t("course_bad")
            except RuntimeError:
                flash_t("course_failed")
            return redirect(url_for("admin"))
        if action == "delete_course":
            if request.form.get("confirm", "").strip().upper() != code:
                flash_t("bad_confirm")
            else:
                remove_course_files(code)
                if request.form.get("purge_logs") and is_main():
                    from core.logger import delete_course_rows
                    flash_t("logs_purged", n=delete_course_rows(code))
                session["course"] = config.default_course()
                sync_sheet()
                flash_t("course_deleted", code=code)
            return redirect(url_for("admin"))
        if action == "delete_lecture":
            from core.passages import lecture_number
            nums = [n for n in request.form.getlist("lecture") if n]
            allpdfs = list(P.lectures.glob("*.pdf"))
            pdfs = [f for f in allpdfs if str(lecture_number(f.name)) in nums]
            if not pdfs:
                flash_t("no_such_lecture")
                return redirect(url_for("admin"))
            if len(allpdfs) <= len(pdfs):                      # every lecture selected = remove the whole course
                remove_course_files(code)
                session["course"] = config.default_course()
                sync_sheet()
                flash_t("course_deleted", code=code)
                return redirect(url_for("admin"))
            for f in pdfs:
                for c in (P.data / "ocr_cache").glob(f"{f.stem}__p*.txt"):
                    c.unlink()
                f.unlink()
            gone = sorted({str(lecture_number(f.name)) for f in pdfs})
            if not full:                       # added course: drop the lectures' topics and questions too
                tp, bk = pd.read_csv(P.topics), pd.read_csv(P.bank)
                tp[~tp.topic.isin([f"lec{n}" for n in gone])].to_csv(P.topics, index=False, encoding="utf-8")
                bk[~bk.lecture.astype(str).isin(gone)].to_csv(P.bank, index=False, encoding="utf-8-sig")
                from core.autocourse import regenerate
                regenerate(code)
            else:
                from core.passages import build_passages
                clf = S()["clf"]
                df = build_passages(predict_topic=lambda text: clf.predict(text)[0], verbose=False, course=code)
                build_index(df, course=code)
            load_state(code)
            flash_t("lecture_deleted", n=", ".join(gone))
            return redirect(url_for("admin"))
        if action == "upload":
            from core.autocourse import save_lecture
            files = [f for f in request.files.getlist("pdf") if f.filename.lower().endswith(".pdf")]
            if not files:
                flash_t("choose_pdf")
                return redirect(url_for("admin"))
            num = request.form.get("lecture_number", "").strip()
            title = re.sub(r"[^A-Za-z0-9 _-]", "", request.form.get("title", "")).strip()
            single = len(files) == 1                  # number and title typed in the form only apply to one file
            saved = []
            for f in files:
                n = save_lecture(code, f.filename, f.read(), number=int(num) if single and num.isdigit() else None,
                                 title=title if single and title else None)
                saved.append(n)
            flash_t("saved_n", n=len(saved), nums=", ".join(str(n) for n in sorted(saved)))
        if action in ("upload", "rebuild", "retrain") and not full:
            from core.autocourse import regenerate
            try:
                rep = regenerate(code)
                load_state(code)
                autoeval.safe_run(code)
                flash_t("index_rebuilt", n=rep["slides"], m=rep["lectures"])
            except RuntimeError:
                flash_t("course_failed")
        elif action in ("upload", "rebuild"):
            from core.passages import build_passages
            clf = S()["clf"]
            df = build_passages(predict_topic=lambda text: clf.predict(text)[0], verbose=False, course=code)
            build_index(df, course=code)
            load_state(code)
            autoeval.safe_run(code)
            flash_t("index_rebuilt", n=len(df), m=df.lecture.nunique())
        elif action == "retrain":
            import scripts.train as T
            import scripts.evaluate as E
            T.train(verbose=False)
            build_index()
            E.main()
            load_state(code)
            autoeval.safe_run(code)
            flash_t("retrained")
        return redirect(url_for("admin"))
    visit("admin")
    if not mine or not code:                                 # doctor without a course (or no course at all): only the "add a course" card
        return render_template("admin.html", no_course=True, lectures=[], total=0, full=False, code="", can_delete_course=False,
                               bank=0, threshold="", model="", lecture_dir="", doctors=doctors.list_doctors("doctor") if is_master() else [], owner=None, is_owner_view=False,
                               sheet=sheet_view(), pw_min=doctors.MIN_LEN, catalog=catalog.load(), used_codes=course_codes(),
                               doctor_courses={d["id"]: sum(c["meta"].get("owner") == d["id"] for c in config.list_courses()) for d in doctors.list_doctors("doctor")} if is_master() else {})
    names = S()["names_ar"] if lang() == "ar" else S()["names"]
    passages = pd.read_csv(P.passages)
    lectures = (passages.groupby(["lecture", "lecture_title"]).agg(passages=("passage_id", "count"),
                topics=("topic", lambda s: ", ".join(names.get(t, t) for t in sorted(set(s)))))
                .reset_index().to_dict("records"))
    return render_template("admin.html", vids=videos.items(code), lectures=lectures, total=len(passages), full=full, code=code,
                           can_delete_course=True, no_course=False, catalog=catalog.load(), used_codes=course_codes(),
                           doctors=doctors.list_doctors("doctor") if is_master() else [], owner=course_owner(code),
                           doctor_courses={d["id"]: sum(c["meta"].get("owner") == d["id"] for c in config.list_courses()) for d in doctors.list_doctors("doctor")} if is_master() else {},
                           bank=len(S()["bank"]), threshold=S()["engine"].threshold,
                           model=KIND_NAME.get(S()["clf"].kind, S()["clf"].kind), lecture_dir=str(P.lectures.relative_to(config.BASE_DIR)),
                           sheet=sheet_view(), pw_min=doctors.MIN_LEN)


def _table_response(rows, header, name, fmt):
    import io
    from flask import send_file, Response
    df = pd.DataFrame(rows, columns=header)
    if fmt == "csv":
        return Response("\ufeff" + df.to_csv(index=False), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={name}.csv"})
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{name}.xlsx")


@app.route("/admin/doctors.<fmt>")
@lecturer_required
def export_doctors(fmt):
    if not is_main() or fmt not in ("xlsx", "csv"):
        return redirect(url_for("admin"))
    return _table_response(doctors.sheet_rows(courses_of), sheet_sync.HEADER, "doctors", fmt)


@app.route("/admin/students.<fmt>")
@lecturer_required
def export_students(fmt):
    return redirect(url_for("students_export", fmt=fmt))


# ------------------------------------------------------------------ Materials (students can keep the lectures)
@app.route("/materials")
@student_required
def materials():
    visit("materials")
    from core.passages import lecture_number
    files = sorted(config.course_paths(course_code()).lectures.glob("*.pdf"), key=lambda f: (lecture_number(f.name) or 0, f.name))
    return render_template("materials.html", files=[{"name": f.name, "mb": round(f.stat().st_size / 1048576, 1)} for f in files])


@app.route("/materials/<path:name>")
@student_required
def material_file(name):
    from flask import send_from_directory
    folder = config.course_paths(course_code()).lectures
    return send_from_directory(folder, name, as_attachment=True)


@app.route("/materials.zip")
@student_required
def materials_zip():
    import io, zipfile
    from flask import send_file
    folder = config.course_paths(course_code()).lectures
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for f in sorted(folder.glob("*.pdf")):
            z.write(f, f.name)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{course_code()}_lectures.zip")


# ------------------------------------------------------------------ Study Studio (study tools built from the slides)
_STUDIO_CACHE = {}


def studio_kit(lecture, seed=0, n=8):
    """The Studio tools for one lecture (or all). Cached until the course's slides change."""
    P = config.course_paths(course_code())
    if not P.passages.exists():
        return None, None
    key = (course_code(), P.passages.stat().st_mtime, lecture or 0, int(seed), int(n), lang())
    if key not in _STUDIO_CACHE:
        if len(_STUDIO_CACHE) > 60:
            _STUDIO_CACHE.clear()
        passages = pd.read_csv(P.passages).fillna("")
        gl = pd.read_csv(P.glossary) if P.glossary.exists() else None
        _STUDIO_CACHE[key] = (STU.lectures_of(passages), STU.build(passages, S()["topics"], gl, lecture=lecture, lang=lang(), seed=seed, n_summary=n, course_title=course_title()))
    return _STUDIO_CACHE[key]


def _studio_args():
    lec = request.args.get("lecture", "all")
    lecture = int(lec) if lec.isdigit() else None
    seed = request.args.get("seed", "0")
    n = request.args.get("n", "8")
    return lecture, int(seed) if seed.isdigit() else 0, min(14, max(3, int(n))) if n.isdigit() else 8


@app.route("/studio")
@student_required
def studio():
    visit("studio")
    lecture, seed, n = _studio_args()
    lectures, kit = studio_kit(lecture, seed, n)
    try:
        import pptx  # noqa: F401
        pptx_ok = True
    except Exception:
        pptx_ok = False
    tool = request.args.get("tool", "quiz")
    return render_template("studio.html", lectures=lectures, kit=kit, lecture=lecture, seed=seed, n=n, pptx_ok=pptx_ok,
                           tool=tool if tool in ("quiz", "mind", "videos") else "quiz", vids=videos.items(course_code()))


@app.route("/videos/<fid>")
@student_required
def video_file(fid):
    from flask import send_from_directory
    folder, name = videos.file_of(course_code(), fid)
    if not folder:
        return ("", 404)
    return send_from_directory(folder, name, conditional=True)


@app.route("/admin/videos", methods=["POST"])
@lecturer_required
@perm_required("content")
def admin_videos():
    code = course_code()
    if not can_manage(code):
        return redirect(url_for("admin"))
    f, by = request.form, session.get("admin_name") or "Admin"
    act = f.get("action")
    if act == "link":
        flash_t("vid_added" if videos.add_link(code, f.get("title", ""), f.get("url", ""), f.get("lecture", ""), by) else "vid_bad_link")
    elif act == "upload":
        up = request.files.get("video")
        if up and up.filename:
            err = videos.add_recorded(code, f.get("title", ""), up, up.filename, f.get("lecture", ""), by)
            flash_t("vid_bad_type" if err else "vid_added")
    elif act == "delete":
        videos.delete(code, f.get("kind", ""), f.get("id", ""))
        flash_t("vid_deleted")
    return redirect(url_for("admin"))


@app.route("/studio/terms.xlsx")
@student_required
def studio_xlsx():
    import io, tempfile
    from flask import send_file
    lecture, seed, n = _studio_args()
    _, kit = studio_kit(lecture, seed, n)
    if not kit:
        return redirect(url_for("studio"))
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
        STU.table_xlsx(kit["terms"], f.name)
        buf = io.BytesIO(open(f.name, "rb").read())
    return send_file(buf, as_attachment=True, download_name=f"{course_code()}_terms{'_L' + str(lecture) if lecture else ''}.xlsx")


@app.route("/studio/slides.pptx")
@student_required
def studio_pptx():
    import io, tempfile
    from flask import send_file
    lecture, seed, n = _studio_args()
    _, kit = studio_kit(lecture, seed, n)
    try:
        import pptx  # noqa: F401
    except Exception:
        flash_t("st_pptx_missing")
        return redirect(url_for("studio", tool="slides", lecture=lecture or "all"))
    if not kit:
        return redirect(url_for("studio"))
    with tempfile.NamedTemporaryFile(suffix=".pptx") as f:
        STU.slides_pptx(kit, course_title(), f.name)
        buf = io.BytesIO(open(f.name, "rb").read())
    return send_file(buf, as_attachment=True, download_name=f"{course_code()}_revision{'_L' + str(lecture) if lecture else ''}.pptx")


# ------------------------------------------------------------------ the student's courses
@app.route("/my-courses", methods=["GET", "POST"])
@student_required
def my_courses():
    me = student()
    guest = me.startswith("GUEST-")
    st = None if guest else students.get(me)
    have = [] if guest else (st["courses"] if st else [])
    if request.method == "POST":
        picked = [c for c in request.form.getlist("course") if c in course_codes()]
        if not picked and not guest and have:                 # a student may remove every course
            students.set_courses(me, [])
            session.pop("practice", None)
            flash_t("courses_removed_all")
            return redirect(url_for("my_courses"))
        if not picked:
            flash_t("courses_pick_one")
        else:
            if not guest:
                students.set_courses(me, picked)
                st0 = students.get(me) or {}
                for c in config.list_courses():
                    if c["code"] in picked and c["code"] not in have:
                        notify.push(["d:" + doctors.MASTER, "d:" + (c["meta"].get("owner") or doctors.MASTER)], "student",
                                    tr("n_student_title", lang(), course=c["name_en"]),
                                    tr("n_student_body", lang(), name=(st0.get("first", "") + " " + st0.get("last", "")).strip(), user=st0.get("username", "")),
                                    url_for("students_page"))
            session["course"] = picked[0] if session.get("course") not in picked else session["course"]
            session.pop("practice", None)
            flash_t("courses_saved")
            return redirect(url_for("student_home"))
    l = lang()
    cards = []
    for c in config.list_courses():
        owner = doctors.get(c["meta"].get("owner")) if c["meta"].get("owner") else None
        cards.append({"code": c["code"], "title": c["name_ar"] if l == "ar" and c["name_ar"] else c["name_en"],
                      "doctor": owner["name"] if owner else "", "lectures": c["lectures"], "slides": c["slides"],
                      "checked": c["code"] in have or (guest and c["code"] == session.get("course"))})
    return render_template("my_courses.html", cards=cards, first=not have and not guest, first_visit=not have and not guest, guest=guest)


# ------------------------------------------------------------------ Students (doctor sees only his own courses)
def students_for_admin():
    """[{code, first, last, username, email, courses: [(code, title, doctor)], created}] visible to this admin / doctor."""
    allowed = {c["code"] for c in config.list_courses() if can_manage(c["code"])}
    info = {c["code"]: (c["name_ar"] or c["name_en"] if lang() == "ar" else c["name_en"],
                        (doctors.get(c["meta"].get("owner")) or {}).get("name", "")) for c in config.list_courses()}
    rows = []
    for s in students.list_students():
        mine = [(c, *info[c]) for c in s["courses"] if c in allowed and c in info]
        if mine:
            rows.append({**s, "courses": mine})
    return rows


# ------------------------------------------------------------------ Badges: admin / doctor
def badge_audience():
    """The students this admin sees: all of them for the main admin, only the students of his own courses for a doctor."""
    if is_master():
        return students.list_students()
    return [dict(s) for s in students_for_admin()]


def _name_of(st):
    return f"{st['first']} {st['last']}".strip()


def _auto_badges_by_student(codes):
    """{student code: [earned auto badges]}, from the logs (read once for everybody)."""
    from collections import defaultdict
    grouped = {n: defaultdict(list) for n in ("Questions", "Answers", "Exams")}
    for n in grouped:
        for r in read_sheet(n):
            grouped[n][r.get("student_code")].append(r)
    topics_of = {}
    for c in config.list_courses():
        try:
            topics_of[c["code"]] = list(load_topics(c["code"]).topic)
        except Exception:
            pass
    return {c: [b for b in badges.compute(grouped["Questions"][c], grouped["Answers"][c], grouped["Exams"][c], topics_of, config.GREEN_FROM, lang()) if b["earned"]]
            for c in codes}


@app.route("/badges-admin", methods=["GET", "POST"])
@lecturer_required
@perm_required("badges")
def badges_admin():
    me_key = custom_badges.MASTER if is_master() else admin_id()
    aud = badge_audience()
    aud_codes = {s["code"] for s in aud}
    mine = lambda: [b for b in custom_badges.defs() if is_master() or b["owner"] == me_key]
    if request.method == "POST":
        act = request.form.get("action")
        link = url_for("badges_page")
        if act == "create_badge":
            b = custom_badges.create(request.form.get("name"), request.form.get("icon"), request.form.get("desc"), me_key)
            if b:
                # tell every student the badge can reach how to get it
                notify.push(["s:" + c for c in aud_codes], "badge", f"🏅 {b['name']} · " + tr("bg_available", "en") + " / " + tr("bg_available", "ar"),
                            (b["desc"] or ""), link)
                flash_t("bg_created", name=b["name"], n=len(aud_codes))
            else:
                flash_t("bg_need_name")
        elif act == "award_badge":
            b = custom_badges.get(request.form.get("badge", ""))
            if not b or not (is_master() or b["owner"] == me_key):
                flash_t("bg_not_yours")
            else:
                picked = aud_codes if request.form.get("all_students") else {c for c in request.form.getlist("students") if c in aud_codes}
                note = request.form.get("note", "")
                new = custom_badges.award(b["id"], sorted(picked), me_key, note)
                notify.push(["s:" + c for c in new], "badge", f"🏅 {b['name']} · " + tr("bg_got_it", "en") + " / " + tr("bg_got_it", "ar"),
                            (note.strip() or b["desc"] or ""), link)
                flash_t("bg_awarded", name=b["name"], n=len(new))
        elif act == "revoke_badge":
            b = custom_badges.get(request.form.get("badge", ""))
            if b and (is_master() or b["owner"] == me_key) and request.form.get("student") in aud_codes:
                custom_badges.revoke(b["id"], request.form.get("student"))
        elif act == "delete_badge":
            if custom_badges.delete(request.form.get("badge", ""), me_key, is_master()):
                flash_t("bg_deleted")
        return redirect(url_for("badges_admin"))
    visit("badges_admin")
    auto = _auto_badges_by_student(aud_codes)
    names = {s["code"]: _name_of(s) for s in aud}
    awards = [a for a in custom_badges.awards() if a["student"] in aud_codes]
    defs_all = {b["id"]: b for b in custom_badges.defs()}
    rows = []
    for s in sorted(aud, key=lambda x: x["code"]):
        cust = [defs_all[a["badge"]] for a in awards if a["student"] == s["code"] and a["badge"] in defs_all]
        rows.append({"code": s["code"], "name": names[s["code"]], "auto": auto.get(s["code"], []), "custom": cust,
                     "total": len(auto.get(s["code"], [])) + len(cust)})
    pop = {}
    for lst in auto.values():
        for b in lst:
            pop.setdefault(b["id"], {"icon": b["icon"], "name": b["name"], "n": 0})["n"] += 1
    popular = sorted(pop.values(), key=lambda x: -x["n"])[:8]
    cards = []
    for b in mine():
        got = [a for a in awards if a["badge"] == b["id"]]
        cards.append({**b, "n": len(got), "owner_name": tr("role_admin", lang()) if b["owner"] == custom_badges.MASTER else (doctors.get(b["owner"]) or {}).get("name", b["owner"]),
                      "got": [{"code": a["student"], "name": names.get(a["student"], a["student"])} for a in got]})
    return render_template("badges_admin.html", rows=rows, cards=cards, popular=popular, students=[{"code": s["code"], "name": names[s["code"]]} for s in sorted(aud, key=lambda x: x["code"])],
                           total_earned=sum(r["total"] for r in rows), master=is_master())


# ------------------------------------------------------------------ Chat (direct messages on the site)
def person(key):
    """{key, name, username, role, avatar} for a user key; None when that account no longer exists."""
    if not key or ":" not in key:
        return None
    kind, ident = key.split(":", 1)
    av = lambda: (url_for("avatar", key=profiles.safe(key)) + "?v=" + str(int(profiles.avatar_path(key).stat().st_mtime))) if profiles.avatar_path(key) else None
    if kind == "s":
        st = students.get(ident)
        return {"key": key, "name": f"{st['first']} {st['last']}".strip(), "username": st["username"], "role": tr("role_student", lang()), "avatar": av()} if st else None
    if ident == doctors.MASTER:
        return {"key": key, "name": profiles.get(profiles.safe(key)).get("name") or tr("role_admin", lang()), "username": "admin", "role": tr("role_admin", lang()), "avatar": av()}
    d = doctors.get(ident)
    return {"key": key, "name": d["name"], "username": doctors.username_of(d), "role": tr("role_doctor", lang()), "avatar": av()} if d else None


def find_person(username):
    """A student, doctor or the admin by username (never by e-mail)."""
    u = (username or "").strip().lstrip("@").lower()
    if not u:
        return None
    if u == "admin":
        return person("d:" + doctors.MASTER)
    for st in students.list_students():
        if st["username"].lower() == u:
            return person("s:" + st["code"])
    for d in doctors.list_doctors():
        if doctors.username_of(d).lower() == u:
            return person("d:" + d["id"])
    return None


def _msg_json(m, me, seen=0):
    out = {"id": m["id"], "mine": m["from"] == me, "text": m["text"], "time": m["time"], "seen": m["id"] <= seen}
    f = m.get("file")
    if f:
        out["file"] = {"name": f["fname"], "size": f["size"], "img": f.get("img", False), "url": url_for("chat_file", fid=f["fid"])}
    return out


@app.route("/chat", methods=["GET", "POST"])
@perm_required("chat")
def chat_page():
    me = user_key()
    if not me:
        return redirect(url_for("start", next=request.path))
    if request.method == "POST":                                  # start a conversation by username
        p = find_person(request.form.get("username"))
        if not p or p["key"] == me:
            flash_t("chat_not_found")
            return redirect(url_for("chat_page"))
        return redirect(url_for("chat_page", **{"with": p["key"]}))
    visit("chat")
    threads = []
    for t in chat.threads_for(me):
        p = person(t["with"])
        if p:
            threads.append({**p, "last": (t["last"]["text"] or "📎 " + t["last"].get("file", {}).get("fname", ""))[:60], "time": t["last"]["time"], "unread": t["unread"]})
    cur = person(request.args.get("with"))
    if request.args.get("with") and not cur:
        flash_t("chat_not_found")
    if cur and cur["key"] == me:
        cur = None
    msgs = []
    if cur:
        chat.mark_read(me, cur["key"])
        seen = chat.seen_upto(me, cur["key"])
        msgs = [_msg_json(m, me, seen) for m in chat.messages(me, cur["key"])]
    return render_template("chat.html", threads=threads, cur=cur, msgs=msgs)


@app.route("/chat/send", methods=["POST"])
@perm_required("chat")
def chat_send():
    me = user_key()
    to = request.form.get("with", "")
    if not me or not person(to):
        return jsonify(ok=False, error="user"), 400
    unread_before = next((t["unread"] for t in chat.threads_for(to) if t["with"] == me), 0)
    saved = None
    up = request.files.get("file")
    if up and up.filename:
        saved, ferr = chat.save_file(up)
        if ferr:
            return jsonify(ok=False, error=ferr), 400
    msg, err = chat.send(me, to, request.form.get("text", ""), saved)
    if err:
        return jsonify(ok=False, error=err), 429 if err == "rate" else 400
    if unread_before == 0:                                         # one notification until he opens the conversation
        mine = person(me)
        notify.push([to], "chat", tr("chat_new_title", lang(), name=mine["name"]), tr("chat_new_body", lang()), url_for("chat_page", **{"with": me}))
    return jsonify(ok=True, msg=_msg_json(msg, me))


@app.route("/chat/file/<fid>")
@perm_required("chat")
def chat_file(fid):
    me = user_key()
    m = chat.file_allowed(me, fid) if me else None
    if not m or "/" in fid or ".." in fid:
        abort(404)
    f = m["file"]
    path = chat.FILES() / fid
    if not path.is_file():
        abort(404)
    resp = send_file(path, as_attachment=not f.get("img"), download_name=f["fname"])
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.route("/chat/close", methods=["POST"])
@perm_required("chat")
def chat_close():
    me = user_key()
    other_key = request.form.get("with", "")
    if me and other_key:
        chat.close(me, other_key)
        flash_t("chat_closed")
    return redirect(url_for("chat_page"))


@app.route("/chat/poll")
@perm_required("chat")
def chat_poll():
    me = user_key()
    if not me:
        return jsonify(ok=False), 401
    with_key = request.args.get("with", "")
    seen = chat.seen_upto(me, with_key)
    new = [_msg_json(m, me, seen) for m in chat.messages(me, with_key, int(request.args.get("after", 0) or 0))] if person(with_key) else []
    if new:
        chat.mark_read(me, with_key)
    return jsonify(ok=True, msgs=new, unread=chat.unread_total(me), seen=seen)


@app.route("/students")
@lecturer_required
@perm_required("students")
def students_page():
    return render_template("students.html", rows=students_for_admin(), master=is_master())


@app.route("/students.<fmt>")
@lecturer_required
@perm_required("students")
def students_export(fmt):
    if fmt not in ("xlsx", "csv"):
        return redirect(url_for("students_page"))
    rows = [[r["code"], r["first"], r["last"], r["username"], r["email"], c[0], c[2], r["created"]]
            for r in students_for_admin() for c in r["courses"]]
    header = ["student_code", "first_name", "last_name", "username", "email", "course", "doctor", "registered"]
    if not is_master():                                    # a doctor never gets the other doctors' names
        header, rows = header[:-2] + header[-1:], [r[:6] + r[7:] for r in rows]
    return _table_response(rows, header, "students", fmt)


# ------------------------------------------------------------------ Arabic translation of answers (on demand)
_TR_CACHE = {}


@app.route("/translate", methods=["POST"])
def translate():
    if not (student() or session.get("lecturer")):
        return jsonify(ok=False), 401
    text = ((request.get_json(silent=True) or {}).get("text") or "").strip()[:4000]
    if not text:
        return jsonify(ok=False)
    if text not in _TR_CACHE:
        try:
            from deep_translator import GoogleTranslator
            out = GoogleTranslator(source="en", target="ar").translate(text)
            if not out:
                return jsonify(ok=False)
            if len(_TR_CACHE) > 3000:
                _TR_CACHE.clear()
            _TR_CACHE[text] = out
        except Exception as e:
            return jsonify(ok=False, error=type(e).__name__)
    return jsonify(ok=True, text=_TR_CACHE[text])


# ------------------------------------------------------------------ Exams (student)
@app.route("/exams")
@student_required
def exams():
    visit("exams")
    code = course_code()
    pool = EX.eligible(code)
    n = len(pool)
    mine = [a for a in EX.list_attempts(code, student()) if a["status"] == "done"]
    rows = [{**a, "c": EX.counts(a), "when": datetime_str(a["started"])} for a in mine]
    stats = {"n": len(mine), "best": max((a["pct"] for a in mine), default=None),
             "avg": round(sum(a["pct"] for a in mine) / len(mine)) if mine else None,
             "last": mine[0]["pct"] if mine else None}
    return render_template("exams.html", n=n, quick=min(10, n), choices=EX.count_choices(n), avg=round(EX.avg_minutes(code), 2),
                           active=EX.active_attempt(code, student()), attempts=rows, stats=stats, exam_lang=lang())


@app.route("/exams/start", methods=["POST"])
@student_required
def exams_start():
    code = course_code()
    if EX.active_attempt(code, student()):
        return redirect(url_for("exams_take"))
    pool = EX.eligible(code)
    if not pool:
        flash_t("exam_none")
        return redirect(url_for("exams"))
    try:
        count = int(request.form.get("count") or request.form.get("custom") or 10)
    except ValueError:
        count = 10
    EX.new_attempt(code, student(), lang(), count)
    return redirect(url_for("exams_take"))


@app.route("/exams/take")
@student_required
def exams_take():
    att = EX.active_attempt(course_code(), student())
    if not att:
        return redirect(url_for("exams"))
    import time as _t
    return render_template("exam_take.html", att=att, qs=EX.view_questions(att, lang()),
                           remaining=max(0, int(att["deadline"] - _t.time())))


@app.route("/exams/save", methods=["POST"])
@student_required
def exams_save():
    att = EX.active_attempt(course_code(), student())
    if not att:
        return jsonify(ok=False)
    data = request.get_json(silent=True) or {}
    att["answers"].update({k: str(v)[:4000] for k, v in (data.get("answers") or {}).items() if k in att["qids"]})
    EX.save_attempt(att)
    return jsonify(ok=True)


@app.route("/exams/submit", methods=["POST"])
@student_required
def exams_submit():
    att = EX.active_attempt(course_code(), student())
    if not att:
        return redirect(url_for("exams"))
    import time as _t
    sent = {k[2:]: v[:4000] for k, v in request.form.items() if k.startswith("q_")} if _t.time() <= att["deadline"] + 60 else {}
    att = EX.finish(att, sent)
    me0 = students.get(student()) or {}
    cc = course_code()
    notify.push(["d:" + (course_owner(cc) or doctors.MASTER)], "exam", tr("n_done_title", lang(), course=cc),
                tr("n_done_body", lang(), name=(me0.get("first", "") + " " + me0.get("last", "")).strip() or student(), score="%g" % att["score"], max=att["max"], pct=att["pct"]))   # no link: the doctor sees the message only, not the student's answers
    log("Exams", {"student_code": student(), "attempt_id": att["id"], "n_questions": att["max"], "correct": att["score"],
                  "score_pct": att["pct"], "duration_sec": att["duration"], "lang": att["lang"],
                  "wrong": ",".join(d["id"] for d in att["details"] if d["score"] < 1)})
    award()
    return redirect(url_for("exams_result", aid=att["id"]))


@app.route("/exams/result/<aid>")
@student_required
def exams_result(aid):
    att = EX.load_attempt(course_code(), aid)
    if not att or att["student"] != student() or att["status"] != "done":
        return redirect(url_for("exams"))
    return render_template("exam_result.html", att=EX.localized(att, lang()), c=EX.counts(att), doctor_view=False)


# ------------------------------------------------------------------ Exams (doctor)
@app.route("/exams/manage", methods=["GET", "POST"])
@lecturer_required
@perm_required("exams")
def exams_manage():
    code = course_code()
    if not can_manage(code):
        return redirect(url_for("admin"))
    if request.method == "POST":
        action = request.form.get("action")
        if action in ("upload_q", "upload_qa"):
            files = [f for f in request.files.getlist("files") if f.filename]
            tot = {"added": 0, "updated": 0}
            for f in files:
                try:
                    items, extra = EX.parse_file(f.filename, f.read())
                except Exception:
                    items, extra = [], ""
                if not items and isinstance(extra, dict) and action == "upload_qa":      # a file with only the answer key
                    flash_t("exam_key_ok", name=f.filename, n=EX.apply_key(code, extra))
                    continue
                if not items:
                    flash_t("exam_file_empty", name=f.filename)
                    continue
                if request.form.get("qtype") == "tf":                 # "every question without options is true / false"
                    items = [EX.to_tf(it) if it["type"] == "essay" else it for it in items]
                r = EX.add_items(code, items, with_answers=action == "upload_qa")
                tot["added"] += r["added"]; tot["updated"] += r["updated"]
                flash_t("exam_file_ok", name=f.filename, n=len(items), a=r["added"], u=r["updated"])
                kinds = [("tf" if len(it["options"]) == 2 and it["type"] == "mcq" else it["type"]) for it in items]
                flash_t("exam_detected", mcq=kinds.count("mcq"), tf=kinds.count("tf"), essay=kinds.count("essay"))
            if not files:
                flash_t("choose_pdf")
        elif action == "redetect":
            n = EX.reclassify(code)
            flash_t("exam_redetected", n=n) if n else flash_t("exam_redetect_none")
        elif action == "settings":
            try:
                EX.save_settings(code, request.form.get("min_mcq", 1), request.form.get("min_essay"),
                                 request.form.get("sim_full"), request.form.get("sim_half"), request.form.get("min_tf"))
                flash_t("exam_settings_saved")
            except ValueError:
                pass
        elif action == "clear":
            if request.form.get("confirm", "").strip().upper() == code:
                EX.clear_bank(code)
                flash_t("exam_bank_cleared")
            else:
                flash_t("bad_confirm")
        return redirect(url_for("exams_manage", tab=request.form.get("tab") or None))
    bank = EX.load_bank(code)
    rows = []
    for k in sorted(bank["questions"], key=int)[:60]:
        q = bank["questions"][k]
        side, _ = EX._pick_lang(q, lang())
        rows.append({"n": k, "type": EX.kind(q), "q": side["q"][:140], "en": "en" in q, "ar": "ar" in q, "graded": EX.is_graded(q)})
    attempts = EX.list_attempts(code)
    done = [a for a in attempts if a["status"] == "done"]
    stats = {"n": len(attempts), "done": len(done), "avg": round(sum(a["pct"] for a in done) / len(done)) if done else 0}
    tab = request.args.get("tab", "questions")
    return render_template("exam_manage.html", sm=EX.summary(code), rows=rows, code=code, attempts=attempts, shown=len(rows),
                           stats=stats, tab=tab if tab in ("questions", "settings", "results") else "questions")


@app.route("/exams/template.xlsx")
@lecturer_required
@perm_required("exams")
def exams_template():
    from flask import Response
    return Response(EX.template_xlsx(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=exam_template.xlsx"})


@app.route("/exams/attempt/<aid>", methods=["GET", "POST"])
@lecturer_required
@perm_required("exams")
def exams_attempt(aid):
    code = course_code()
    att = EX.load_attempt(code, aid)
    if not can_manage(code) or not att or att["status"] != "done":
        return redirect(url_for("exams_manage"))
    if request.method == "POST":
        try:
            sc = float(request.form.get("score", ""))
            if sc in (0.0, 0.5, 1.0):
                EX.override(att, request.form.get("qid", ""), sc)
                flash_t("exam_mark_saved")
        except ValueError:
            pass
        return redirect(url_for("exams_attempt", aid=aid))
    return render_template("exam_result.html", att=EX.localized(att, lang()), c=EX.counts(att), doctor_view=True)


@app.route("/exams/attempts.<fmt>")
@lecturer_required
@perm_required("exams")
def exams_attempts_export(fmt):
    code = course_code()
    if not can_manage(code) or fmt not in ("xlsx", "csv"):
        return redirect(url_for("exams_manage"))
    rows = [[a["student"], datetime_str(a["started"]), a["lang"], a["max"], a["score"], a["pct"], a["duration"]]
            for a in EX.list_attempts(code) if a["status"] == "done"]
    return _table_response(rows, ["student_code", "started", "lang", "questions", "score", "percent", "seconds"], f"exam_{code}", fmt)


@app.template_filter("datetime")
def _dt_filter(ts):
    return datetime_str(ts)


def datetime_str(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


@app.route("/lecturer/logout")
def lecturer_logout():
    for k in ("lecturer", "admin_id", "admin_name"):
        session.pop(k, None)
    return redirect(url_for("start"))


load_state()

# ------------------------------------------------------------------ support messages
@app.route("/support", methods=["POST"])
def support_send():
    f = request.form
    me = (session.get("student_code") or session.get("admin_name") or "")
    rec = support.add(f.get("name"), f.get("contact"), f.get("message"), ident=f.get("ident") or me,
                      ip=request.remote_addr or "?")
    if rec:
        notify.push(["d:" + doctors.MASTER], "support", tr("n_support", lang()), (rec["message"][:120]), url_for("support_inbox"))
    return jsonify(ok=bool(rec))


def _find_account(*idents):
    """The student or doctor these identifiers (e-mail, username or student code) point to: (kind, record) or None."""
    for raw in idents:
        key = (raw or "").strip().lstrip("@").lower()
        if not key:
            continue
        for st in students.list_students():
            if key in (st["email"].lower(), st["code"].lower(), (st.get("username") or "").lower()):
                return "student", st
        for d in doctors.list_doctors():
            if key in ((d.get("email") or "").lower(), d["username"].lower()):
                return "doctor", d
    return None


@app.route("/support-inbox", methods=["GET", "POST"])
@lecturer_required
def support_inbox():
    if not (is_main() or (is_subadmin() and has_perm("support"))):
        return redirect(url_for("staff_home"))
    reset = None
    if request.method == "POST":
        if request.form.get("action") == "reset":
            found = _find_account(request.form.get("who", ""), request.form.get("who2", ""))
            if found:
                kind, acc = found
                pw = passgen.generate()
                (students.set_password(acc["code"], pw) if kind == "student" else doctors.set_password(acc["id"], pw))
                for k in (acc.get("email", ""), acc.get("username", ""), acc.get("code", "")):
                    _FAILS.pop((k or "").lower(), None)         # a locked account is open again
                name = acc.get("first") or acc.get("name") or ""
                reset = {"ok": True, "kind": kind, "name": name, "user": acc.get("email") or acc.get("username"), "pw": pw}
            else:
                reset = {"ok": False}
        else:
            support.set_status(request.form.get("id", ""), request.form.get("status", "done"))
            return redirect(url_for("support_inbox"))
    items = support.all_messages()
    for m in items:
        m["acct"] = _find_account(m.get("ident"), m.get("contact")) is not None
    r = render_template("support_inbox.html", items=items, reset=reset)
    return (r, 200, {"Cache-Control": "no-store"}) if reset else r


@app.route("/course-codes-template.xlsx")
@lecturer_required
def course_codes_template():
    from flask import Response
    if not is_master():
        return redirect(url_for("admin"))
    return Response(catalog.template_xlsx(catalog.load() or None), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=course_codes.xlsx"})


@app.route("/generate-password")
def generate_password():
    r = jsonify(password=passgen.generate())
    r.headers["Cache-Control"] = "no-store"
    return r



if __name__ == "__main__":
    import os
    # locally: http://127.0.0.1:5000 ; on a server (Hugging Face) HOST/PORT come from the environment
    app.run(debug=False, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)))

