"""StudyMate - Course Study Assistant (AI Lab Project 1E).

Run:  python app.py      then open http://127.0.0.1:5000
"""
import json
import random
import re
from collections import Counter, defaultdict
from functools import wraps

import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from markupsafe import Markup
from werkzeug.utils import secure_filename

import config
from core import mastery as M
from core.classifier import TopicClassifier, KIND_NAME
from core.logger import log_to_excel, read_sheet, ensure_workbook
from core.search import SearchEngine, build_index, highlight
from core.topics import load_topics, study_next
from core.i18n import tr

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
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


def course_code():
    c = session.get("course")
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
        if not student():
            return redirect(url_for("start", next=request.path))
        return view(*a, **kw)
    return wrapper


def lecturer_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("lecturer"):
            return redirect(url_for("lecturer_login", next=request.path))
        return view(*a, **kw)
    return wrapper


def visit(page):
    log("Visits", {"student_code": student() or ("lecturer" if session.get("lecturer") else ""), "page": page})


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


@app.context_processor
def inject():
    l = lang()
    args = request.args.to_dict()
    args["lang"] = "en" if l == "ar" else "ar"
    from urllib.parse import urlencode
    return {"lang_url": request.path + "?" + urlencode(args), "theme": current_theme(), "course": course_title(), "course_code": course_code(), "student_code": student(),
            "is_lecturer": session.get("lecturer"), "names": S()["names_ar" if l == "ar" else "names"],
            "lang": l, "dir": "rtl" if l == "ar" else "ltr", "t": lambda key, **kw: tr(key, l, **kw),
            "courses": [{**c, "title": c["name_ar"] if l == "ar" and c["name_ar"] else c["name_en"]}
                        for c in config.list_courses()]}


# ------------------------------------------------------------------ student login (code only, no names)
@app.route("/start", methods=["GET", "POST"])
def start():
    if request.method == "POST":
        code = re.sub(r"[^A-Za-z0-9_-]", "", request.form.get("code", "")).upper()[:20]
        if request.form.get("guest"):                  # guest: no code needed, a temporary one is made
            import secrets
            code = "GUEST-" + secrets.token_hex(2).upper()
        if not code:
            flash_t("enter_code")
        else:
            session["student_code"] = code
            chosen = request.form.get("course")
            if chosen in course_codes():
                session["course"] = chosen
            session.pop("practice", None)
            return redirect(request.args.get("next") or url_for("ask"))
    return render_template("start.html")


@app.route("/course/<code>")
def choose_course(code):
    if code in course_codes() and code != session.get("course"):
        session["course"] = code
        session.pop("practice", None)
    return redirect(request.args.get("next") or url_for("ask" if student() else "start"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("start"))


@app.route("/")
def home():
    return redirect(url_for("ask") if student() else url_for("start"))


# ------------------------------------------------------------------ Ask
@app.route("/ask", methods=["GET", "POST"])
@student_required
def ask():
    result = None
    question = request.values.get("q", "").strip()
    method = request.values.get("method", "tfidf")
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
    visit("evaluation")
    P = config.course_paths(course_code())
    path = P.reports / "metrics.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return render_template("evaluation.html", r=report, rep_url=P.reports_url,
                           auto=not any(c["full"] for c in config.list_courses() if c["code"] == course_code()))


# ------------------------------------------------------------------ Lecturer: login, dashboard, admin
@app.route("/lecturer", methods=["GET", "POST"])
def lecturer_login():
    if request.method == "POST":
        if request.form.get("password") == config.LECTURER_PASSWORD:
            session["lecturer"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash_t("wrong_password")
    return render_template("lecturer_login.html")


@app.route("/dashboard")
@lecturer_required
def dashboard():
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
    return send_file(config.LOGS_XLSX, as_attachment=True, download_name="logs.xlsx")


@app.route("/admin", methods=["GET", "POST"])
@lecturer_required
def admin():
    code = course_code()
    P = config.course_paths(code)
    full = any(c["full"] for c in config.list_courses() if c["code"] == code)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_course":
            from core.autocourse import build_course, clean_code
            files = [(f.filename, f.read()) for f in request.files.getlist("pdfs") if f.filename.lower().endswith(".pdf")]
            try:
                rep = build_course(request.form.get("code", ""), request.form.get("name_en", "").strip(),
                                   request.form.get("name_ar", "").strip(), files)
                load_state(rep["code"])
                session["course"] = rep["code"]
                session.pop("practice", None)
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
                flash_t("course_deleted", code=code)
            return redirect(url_for("admin"))
        if action == "delete_lecture":
            from core.passages import lecture_number
            num = request.form.get("lecture", "")
            pdfs = [f for f in P.lectures.glob("*.pdf") if str(lecture_number(f.name)) == num]
            if not pdfs:
                flash_t("no_such_lecture")
                return redirect(url_for("admin"))
            if len(list(P.lectures.glob("*.pdf"))) <= len(pdfs):
                flash_t("last_lecture")
                return redirect(url_for("admin"))
            for f in pdfs:
                for c in (P.data / "ocr_cache").glob(f"{f.stem}__p*.txt"):
                    c.unlink()
                f.unlink()
            if not full:                       # added course: drop the lecture's topic and questions too
                tp, bk = pd.read_csv(P.topics), pd.read_csv(P.bank)
                tp[tp.topic != f"lec{num}"].to_csv(P.topics, index=False, encoding="utf-8")
                bk[bk.lecture.astype(str) != num].to_csv(P.bank, index=False, encoding="utf-8-sig")
                from core.autocourse import regenerate
                regenerate(code)
            else:
                from core.passages import build_passages
                clf = S()["clf"]
                df = build_passages(predict_topic=lambda text: clf.predict(text)[0], verbose=False, course=code)
                build_index(df, course=code)
            load_state(code)
            flash_t("lecture_deleted", n=num)
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
    names = S()["names_ar"] if lang() == "ar" else S()["names"]
    passages = pd.read_csv(P.passages)
    lectures = (passages.groupby(["lecture", "lecture_title"]).agg(passages=("passage_id", "count"),
                topics=("topic", lambda s: ", ".join(names.get(t, t) for t in sorted(set(s)))))
                .reset_index().to_dict("records"))
    return render_template("admin.html", lectures=lectures, total=len(passages), full=full, code=code,
                           can_delete_course=code != config.DEFAULT_COURSE,
                           bank=len(S()["bank"]), threshold=S()["engine"].threshold,
                           model=KIND_NAME.get(S()["clf"].kind, S()["clf"].kind), lecture_dir=str(P.lectures.relative_to(config.BASE_DIR)))


@app.route("/lecturer/logout")
def lecturer_logout():
    session.pop("lecturer", None)
    return redirect(url_for("ask") if student() else url_for("start"))


load_state()

if __name__ == "__main__":
    import os
    # locally: http://127.0.0.1:5000 ; on a server (Hugging Face) HOST/PORT come from the environment
    app.run(debug=False, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)))
