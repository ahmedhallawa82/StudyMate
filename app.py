"""StudyMate - Course Study Assistant (AI Lab Project 1E).

Run:  python app.py      then open http://127.0.0.1:5000
"""
import json
import random
import re
from collections import Counter, defaultdict
from functools import wraps

import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
from markupsafe import Markup
from werkzeug.utils import secure_filename

import config
from core import doctors, sheet_sync, students, mailer, notify, profiles, support, passgen
from core import schedule as SCH
from core import exams as EX
from core import mastery as M
from core.classifier import TopicClassifier, KIND_NAME
from core.logger import log_to_excel, read_sheet, ensure_workbook
from core.search import SearchEngine, build_index, highlight
from core.topics import load_topics, study_next
from core.i18n import tr

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
from datetime import timedelta
app.permanent_session_lifetime = timedelta(days=30)      # "remember me"
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB PDFs

STATE = {}          # course code -> loaded models and data


def load_state(code=None):
    """Load models + data of one course into memory (also called after the admin rebuilds the index)."""
    code = code or config.DEFAULT_COURSE
    P = config.course_paths(code)
    st = {}
    try:
        st["engine"] = SearchEngine.load(code)
        st["clf"] = TopicClassifier.load(course=code)
    except Exception as e:  # models missing or saved with another scikit-learn version -> rebuild them
        print(f"Could not load the saved models of {code} ({type(e).__name__}). Rebuilding them, please wait ...")
        if code == config.DEFAULT_COURSE:
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
    return c if c in course_codes() else config.DEFAULT_COURSE


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


def is_master():
    return admin_id() == doctors.MASTER


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


def visit(page):
    if session.get("lecturer"):                        # admin pages are not student visits
        return
    from core.logger import log_async
    log_async("Visits", {"student_code": student() or ("lecturer" if session.get("lecturer") else ""), "page": page, "course": course_code()})


def my_mastery(code=None):
    code = code or student()
    rows = [a for a in read_sheet("Answers") if a.get("student_code") == code and a.get("course") == course_code()]
    return M.replay(rows, S()["qid_topic"])


def topic_panel(mastery):
    items, l = [], lang()
    for _, t in S()["topics"].iterrows():
        lvl = mastery.get(t.topic, 0.0)
        items.append({"topic": t.topic, "name": t["name_ar"] if l == "ar" else t["name"], "level": lvl,
                      "pct": round(lvl * 100), "colour": M.colour(lvl), "started": t.topic in mastery})
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
        return {"me_key": None, "me_avatar": None, "me_name": "", "me_role": "", "notifs": [], "unread": 0}
    pkey = profiles.safe(key)
    if key.startswith("s:"):
        st = students.get(key[2:]) or {}
        name, role = (st.get("first", "") + " " + st.get("last", "")).strip() or key[2:], tr("role_student", lang())
    elif key == "d:" + doctors.MASTER:
        name, role = profiles.get(pkey).get("name") or tr("role_admin", lang()), tr("role_admin", lang())
    else:
        name, role = session.get("admin_name", ""), tr("role_doctor", lang())
    return {"me_key": key, "me_avatar": url_for("avatar", key=pkey) + "?v=" + str(int(profiles.avatar_path(key).stat().st_mtime)) if profiles.avatar_path(key) else None,
            "me_name": name, "me_role": role, "notifs": notify.for_user(key, 6), "unread": notify.unread_count(key)}


@app.context_processor
def inject():
    l = lang()
    args = request.args.to_dict()
    args["lang"] = "en" if l == "ar" else "ar"
    from urllib.parse import urlencode
    return {"lang_url": request.path + "?" + urlencode(args), "theme": current_theme(), "course": course_title(), "course_code": course_code(), "student_code": student(), "student_name": session.get("student_name", ""),
            "is_lecturer": session.get("lecturer"), "names": S()["names_ar" if l == "ar" else "names"],
            "lang": l, "dir": "rtl" if l == "ar" else "ltr", "t": lambda key, **kw: tr(key, l, **kw),
            "courses": [{**c, "title": c["name_ar"] if l == "ar" and c["name_ar"] else c["name_en"]}
                        for c in visible_courses() if session.get("lecturer") or student_course_list() is None
                        or c["code"] in student_course_list()],
            "admin_role": ("master" if is_master() else "doctor") if session.get("lecturer") else None,
            "admin_name": session.get("admin_name", ""), "login_alert": getattr(g, "login_alert", None), "support_open": support.open_count() if session.get("lecturer") and is_master() else 0, **_me_context()}


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
        if hmac.compare_digest(pw, config.LECTURER_PASSWORD):
            return "admin", doctors.MASTER, ""
    if "@" not in ident:                                   # doctors sign in with their username (or the password alone)
        did = doctors.check(pw, username=ident or None)
        if did:
            return "doctor", did, doctors.get(did)["name"]
    if ident:
        st = students.check(ident, pw)
        if st:
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
    sent = False
    if request.method == "POST":
        st, pw = students.reset_password(request.form.get("email", ""))
        if st:
            body = (f"Hello {st['first']},\n\nYour new StudyMate password is: {pw}\n"
                    f"Sign in with your e-mail and this password, it is better to change it afterwards.")
            mailer.send(st["email"], "StudyMate - new password", body)
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


@app.route("/")
def home():
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


@app.route("/home")
@student_required
def student_home():
    visit("home")
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
             "streak": _streak(days)}
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
@app.route("/ask", methods=["GET", "POST"])
@student_required
def ask():
    result = None
    question = request.values.get("q", "").strip()
    method = request.values.get("method", "tfidf")
    method = method if method in ("tfidf", "bm25", "lsa", "hybrid") else "tfidf"
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
        log_id = log("Questions", {
            "student_code": student(), "question": question, "topic": topic if found else "",
            "confidence": round(conf, 3), "first_slide": hits[0]["passage_id"] if hits else "",
            "found": "yes" if found else "no", "method": method, "helpful": "",
        })
        result = {"found": found, "hits": hits, "topic": topic, "topic_name": topic_name(topic),
                  "confidence": round(conf * 100), "log_id": log_id}
    else:
        visit("ask")
    items, nxt = topic_panel(my_mastery())
    return render_template("ask.html", question=question, method=method, result=result, items=items, nxt=nxt,
                           examples=examples())


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
    if request.method == "GET" and (p is None or topic is not None and topic != p.get("topic")):
        if topic is None:
            topic, _ = study_next(my_mastery(), S()["topics"], lang())
        p = {"topic": topic, "done": [], "count": 0, "goal": 5, "course": course_code()}
        p.update({"q_id": next_question(topic, []), "hints": 0, "stage": "ask", "answer": ""})
        session["practice"] = p
        visit("practice")

    if request.method == "POST":
        action = request.form.get("action")
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
            p["done"].append(p["q_id"])
            p["count"] += 1
            p["last"] = {"correct": correct, "old": round(old * 100), "new": round(new * 100),
                         "colour": M.colour(new)}
            p.update({"q_id": next_question(p["topic"], p["done"]), "hints": 0, "stage": "ask", "answer": ""})
        session["practice"] = p
        return redirect(url_for("practice"))

    q = S()["bank"].set_index("q_id").loc[p["q_id"]]
    match = keyword_match(p.get("answer", ""), q.keywords) if p["stage"] == "check" else None
    topics = [{"topic": r.topic, "name": r.name_ar if lang() == "ar" else r["name"]} for _, r in S()["topics"].iterrows()]
    last = p.pop("last", None)
    session["practice"] = p
    return render_template("practice.html", p=p, q=q, match=match, topics=topics, last=last,
                           topic_name=topic_name(p["topic"], tr("all_topics", lang())))


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
    return render_template("progress.html", items=items, nxt=nxt, stats=stats)


# ------------------------------------------------------------------ Evaluation
@app.route("/evaluation")
@lecturer_required
def evaluation():
    if not can_manage(course_code()):
        return redirect(url_for("admin"))
    visit("evaluation")
    P = config.course_paths(course_code())
    path = P.reports / "metrics.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return render_template("evaluation.html", r=report, rep_url=P.reports_url,
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
    docs = doctors.list_doctors()
    stats = {"courses": len(courses), "students": len(rows), "visits": len(visits),
             "visitors": len({v.get("student_code") for v in visits if v.get("student_code")}),
             "doctors": len(docs), "exams": len(exams), "asked": len(qs)}
    team = [{"name": d["name"], "courses": courses_of(d["id"]) or "–"} for d in docs] if master else []
    recent = sorted(rows, key=lambda r: str(r.get("created", "")), reverse=True)[:5]
    hour = _dt.datetime.now().hour
    greet = "gm" if hour < 12 else "ga" if hour < 18 else "ge"
    name = tr("role_admin", lang()) if master else session.get("admin_name") or tr("role_doctor", lang())
    return render_template("staff_home.html", stats=stats, week=wk, week_total=sum(w["n"] for w in wk), master=master,
                           by_course=by_course, team=team, recent=recent, greet=greet, name=name,
                           today=td.isoformat(), courses=courses)


# ------------------------------------------------------------------ doctors / courses overview pages (admin + doctor home cards)
@app.route("/doctors")
@lecturer_required
def doctors_page():
    if not is_master():
        return redirect(url_for("staff_home"))
    allc = config.list_courses()
    owned = {}
    for c in allc:
        owned.setdefault(c["meta"].get("owner"), []).append(c["code"])
    per = Counter(c[0] for r in students_for_admin() for c in r["courses"])
    rows = []
    for d in doctors.list_doctors():
        mine = owned.get(d["id"], [])
        rows.append({**d, "courses": mine, "students": sum(per.get(c, 0) for c in mine), "avatar": profiles.avatar_path("d:" + d["id"]) is not None,
                     "key": profiles.safe("d:" + d["id"])})
    return render_template("doctors.html", rows=rows)


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
                flash_t("pw_master_note")
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
           "not_found": sum(q.get("found") == "no" for q in qs)}
    lowest = [{"name": names[t], "avg": avg[t], "n": len(score[t])} for t in sorted(avg, key=avg.get)[:3]]
    top = [{"name": names[t], "n": n} for t, n in asked.most_common(3)]
    return render_template("dashboard.html", data=data, kpi=kpi, lowest=lowest, top=top, not_found=not_found)


@app.route("/dashboard/logs.xlsx")
@lecturer_required
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
    if not is_master():
        return None
    return {"rows": doctors.sheet_rows(courses_of), "enabled": sheet_sync.enabled(), "status": sheet_sync.STATUS,
            "google": sheet_sync.SHOW_GOOGLE or sheet_sync.enabled(), "email": sheet_sync.service_email(), "url": sheet_sync.sheet_url(), "header": sheet_sync.HEADER}


@app.route("/admin", methods=["GET", "POST"])
@lecturer_required
def admin():
    code = course_code()
    P = config.course_paths(code)
    full = any(c["full"] for c in config.list_courses() if c["code"] == code)
    mine = can_manage(code)                                  # a doctor with no course yet can only add one
    if request.method == "POST":
        action = request.form.get("action")
        if action == "change_password":                      # a doctor changes his own password
            if is_master() or not admin_id():
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
            if not is_master():
                flash_t("master_only")
                return redirect(url_for("admin"))
            if action == "add_doctor":
                name = request.form.get("doctor_name", "").strip()
                email = request.form.get("doctor_email", "").strip()
                if name:
                    did, new_code = doctors.add(name, email)
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
        if action != "add_course" and not mine:
            flash_t("not_your_course")
            return redirect(url_for("admin"))
        if action == "add_course":
            from core.autocourse import build_course, clean_code
            if not is_master() and len([c for c in config.list_courses() if c["meta"].get("owner") == admin_id()]) >= config.MAX_COURSES_PER_DOCTOR:
                flash_t("too_many_courses", n=config.MAX_COURSES_PER_DOCTOR)
                return redirect(url_for("admin"))
            files = [(f.filename, f.read()) for f in request.files.getlist("pdfs") if f.filename.lower().endswith(".pdf")]
            try:
                owner = admin_id() if not is_master() else (request.form.get("owner") or None)
                rep = build_course(request.form.get("code", ""), request.form.get("name_en", "").strip(),
                                   request.form.get("name_ar", "").strip(), files, owner=owner)
                load_state(rep["code"])
                session["course"] = rep["code"]
                session.pop("practice", None)
                sync_sheet()
                flash_t("course_created", name=request.form.get("name_en") or rep["code"], n=rep["slides"],
                        m=rep["lectures"], q=rep["questions"])
            except FileExistsError:
                flash_t("course_exists")
            except ValueError:
                flash_t("course_bad")
            except RuntimeError:
                flash_t("course_failed")
            return redirect(url_for("admin"))
        if action == "delete_course":
            import shutil
            if code == config.DEFAULT_COURSE:
                flash_t("cannot_delete_default")
            elif request.form.get("confirm", "").strip().upper() != code:
                flash_t("bad_confirm")
            else:
                for d in (P.data, P.models, P.reports):
                    shutil.rmtree(d, ignore_errors=True)
                STATE.pop(code, None)
                session["course"] = config.DEFAULT_COURSE
                session.pop("practice", None)
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
            if len(allpdfs) <= len(pdfs):
                if code == config.DEFAULT_COURSE:         # the main course cannot be emptied
                    flash_t("last_lecture")
                    return redirect(url_for("admin"))
                import shutil                               # every lecture selected = remove the whole course content
                for d in (P.data, P.models, P.reports):
                    shutil.rmtree(d, ignore_errors=True)
                STATE.pop(code, None)
                session["course"] = config.DEFAULT_COURSE
                session.pop("practice", None)
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
                flash_t("index_rebuilt", n=rep["slides"], m=rep["lectures"])
            except RuntimeError:
                flash_t("course_failed")
        elif action in ("upload", "rebuild"):
            from core.passages import build_passages
            clf = S()["clf"]
            df = build_passages(predict_topic=lambda text: clf.predict(text)[0], verbose=False, course=code)
            build_index(df, course=code)
            load_state(code)
            flash_t("index_rebuilt", n=len(df), m=df.lecture.nunique())
        elif action == "retrain":
            import scripts.train as T
            import scripts.evaluate as E
            T.train(verbose=False)
            build_index()
            E.main()
            load_state(code)
            flash_t("retrained")
        return redirect(url_for("admin"))
    visit("admin")
    if not mine:                                             # doctor without a course: only the "add a course" card
        return render_template("admin.html", no_course=True, lectures=[], total=0, full=False, code="", can_delete_course=False,
                               bank=0, threshold="", model="", lecture_dir="", doctors=[], owner=None, is_owner_view=False,
                               sheet=None, pw_min=doctors.MIN_LEN)
    names = S()["names_ar"] if lang() == "ar" else S()["names"]
    passages = pd.read_csv(P.passages)
    lectures = (passages.groupby(["lecture", "lecture_title"]).agg(passages=("passage_id", "count"),
                topics=("topic", lambda s: ", ".join(names.get(t, t) for t in sorted(set(s)))))
                .reset_index().to_dict("records"))
    return render_template("admin.html", lectures=lectures, total=len(passages), full=full, code=code,
                           can_delete_course=code != config.DEFAULT_COURSE, no_course=False,
                           doctors=doctors.list_doctors() if is_master() else [], owner=course_owner(code),
                           doctor_courses={d["id"]: sum(c["meta"].get("owner") == d["id"] for c in config.list_courses()) for d in doctors.list_doctors()} if is_master() else {},
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
    if not is_master() or fmt not in ("xlsx", "csv"):
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


@app.route("/students")
@lecturer_required
def students_page():
    return render_template("students.html", rows=students_for_admin(), master=is_master())


@app.route("/students.<fmt>")
@lecturer_required
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
    return render_template("exams.html", n=n, choices=EX.count_choices(n), avg=round(EX.avg_minutes(code), 2),
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
                tr("n_done_body", lang(), name=(me0.get("first", "") + " " + me0.get("last", "")).strip() or student(), score="%g" % att["score"], max=att["max"], pct=att["pct"]),
                url_for("exams_attempt", aid=att["id"]))
    log("Exams", {"student_code": student(), "attempt_id": att["id"], "n_questions": att["max"], "correct": att["score"],
                  "score_pct": att["pct"], "duration_sec": att["duration"], "lang": att["lang"],
                  "wrong": ",".join(d["id"] for d in att["details"] if d["score"] < 1)})
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
                r = EX.add_items(code, items, with_answers=action == "upload_qa")
                tot["added"] += r["added"]; tot["updated"] += r["updated"]
                flash_t("exam_file_ok", name=f.filename, n=len(items), a=r["added"], u=r["updated"])
            if not files:
                flash_t("choose_pdf")
        elif action == "settings":
            try:
                EX.save_settings(code, request.form.get("min_mcq", 1), request.form.get("min_essay", 5),
                                 request.form.get("sim_full"), request.form.get("sim_half"))
                flash_t("exam_settings_saved")
            except ValueError:
                pass
        elif action == "clear":
            if request.form.get("confirm", "").strip().upper() == code:
                EX.clear_bank(code)
                flash_t("exam_bank_cleared")
            else:
                flash_t("bad_confirm")
        return redirect(url_for("exams_manage"))
    bank = EX.load_bank(code)
    rows = []
    for k in sorted(bank["questions"], key=int)[:60]:
        q = bank["questions"][k]
        side, _ = EX._pick_lang(q, lang())
        rows.append({"n": k, "type": q["type"], "q": side["q"][:140], "en": "en" in q, "ar": "ar" in q, "graded": EX.is_graded(q)})
    return render_template("exam_manage.html", sm=EX.summary(code), rows=rows, code=code,
                           attempts=EX.list_attempts(code), shown=len(rows))


@app.route("/exams/template.xlsx")
@lecturer_required
def exams_template():
    from flask import Response
    return Response(EX.template_xlsx(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=exam_template.xlsx"})


@app.route("/exams/attempt/<aid>", methods=["GET", "POST"])
@lecturer_required
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


@app.route("/support-inbox", methods=["GET", "POST"])
@lecturer_required
def support_inbox():
    if not is_master():
        return redirect(url_for("staff_home"))
    if request.method == "POST":
        support.set_status(request.form.get("id", ""), request.form.get("status", "done"))
        return redirect(url_for("support_inbox"))
    return render_template("support_inbox.html", items=support.all_messages())


@app.route("/generate-password")
def generate_password():
    r = jsonify(password=passgen.generate())
    r.headers["Cache-Control"] = "no-store"
    return r



if __name__ == "__main__":
    import os
    # locally: http://127.0.0.1:5000 ; on a server (Hugging Face) HOST/PORT come from the environment
    app.run(debug=False, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)))

