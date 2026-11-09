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

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB PDFs

STATE = {}


def load_state():
    """Load models + data into memory (also called after the admin rebuilds the index)."""
    try:
        STATE["engine"] = SearchEngine.load()
        STATE["clf"] = TopicClassifier.load()
    except Exception as e:  # models missing or saved with another scikit-learn version -> rebuild them
        print(f"Could not load the saved models ({type(e).__name__}). Rebuilding them, please wait ...")
        import scripts.train as T
        import scripts.evaluate as E
        if not config.PASSAGES_CSV.exists():
            from core.passages import build_passages
            build_passages()
        T.train()
        build_index()
        E.main()
        STATE["engine"] = SearchEngine.load()
        STATE["clf"] = TopicClassifier.load()
    STATE["topics"] = load_topics()
    STATE["names"] = dict(zip(STATE["topics"].topic, STATE["topics"].name))
    qb = pd.read_csv(config.QUESTION_BANK_CSV).fillna("")
    STATE["bank"] = qb
    STATE["qid_topic"] = dict(zip(qb.q_id, qb.topic))
    ensure_workbook()


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
    log_to_excel("Visits", {"student_code": student() or ("lecturer" if session.get("lecturer") else ""),
                            "page": page})


def my_mastery(code=None):
    code = code or student()
    rows = [a for a in read_sheet("Answers") if a.get("student_code") == code]
    return M.replay(rows, STATE["qid_topic"])


def topic_panel(mastery):
    items = []
    for _, t in STATE["topics"].iterrows():
        lvl = mastery.get(t.topic, 0.0)
        items.append({"topic": t.topic, "name": t["name"], "level": lvl, "pct": round(lvl * 100),
                      "colour": M.colour(lvl), "started": t.topic in mastery})
    nxt, why = study_next(mastery, STATE["topics"])
    return items, ({"topic": nxt, "name": STATE["names"].get(nxt), "why": why} if nxt else {"why": why})


def current_theme():
    t = request.args.get("theme")
    if t in config.THEMES:
        session["theme"] = t
    return session.get("theme", config.THEME)


@app.context_processor
def inject():
    return {"theme": current_theme(), "course": config.COURSE_NAME, "student_code": student(), "is_lecturer": session.get("lecturer"),
            "names": STATE.get("names", {})}


# ------------------------------------------------------------------ student login (code only, no names)
@app.route("/start", methods=["GET", "POST"])
def start():
    if request.method == "POST":
        code = re.sub(r"[^A-Za-z0-9_-]", "", request.form.get("code", "")).upper()[:20]
        if not code:
            flash("Please enter your student code (for example S001).")
        else:
            session["student_code"] = code
            session.pop("practice", None)
            return redirect(request.args.get("next") or url_for("ask"))
    return render_template("start.html")


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
        clf, eng = STATE["clf"], STATE["engine"]
        topic, conf = clf.predict(question)
        found, hits = eng.search(question, method=method)
        for h in hits:
            h["html"] = Markup(highlight(h["text"], question))
        log_id = log_to_excel("Questions", {
            "student_code": student(), "question": question, "topic": topic if found else "",
            "confidence": round(conf, 3), "first_slide": hits[0]["passage_id"] if hits else "",
            "found": "yes" if found else "no", "method": method, "helpful": "",
        })
        result = {"found": found, "hits": hits, "topic": topic, "topic_name": STATE["names"].get(topic, topic),
                  "confidence": round(conf * 100), "log_id": log_id}
    else:
        visit("ask")
    items, nxt = topic_panel(my_mastery())
    return render_template("ask.html", question=question, method=method, result=result, items=items, nxt=nxt)


@app.route("/helpful/<int:log_id>/<answer>", methods=["POST"])
@student_required
def helpful(log_id, answer):
    answer = "yes" if answer == "yes" else "no"
    log_to_excel("Questions", {"helpful": answer}, update_id=log_id)
    log_to_excel("Feedback", {"student_code": student(), "question_log_id": log_id, "helpful": answer,
                              "comment": request.form.get("comment", "")[:300]})
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    flash("Thanks for the feedback!")
    return redirect(url_for("ask"))


# ------------------------------------------------------------------ Practice
def next_question(topic, done):
    bank = STATE["bank"]
    pool = bank[bank.topic == topic] if topic else bank
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
    if request.method == "GET" and (p is None or topic is not None and topic != p.get("topic")):
        if topic is None:
            topic, _ = study_next(my_mastery(), STATE["topics"])
        p = {"topic": topic, "done": [], "count": 0, "goal": 5}
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
            q_topic = STATE["qid_topic"][p["q_id"]]
            old = my_mastery().get(q_topic, 0.0)
            new = M.update(old, correct, p["hints"])
            log_to_excel("Answers", {"student_code": student(), "question_id": p["q_id"], "topic": q_topic,
                                     "correct": int(correct), "hints_used": p["hints"], "mastery_after": new})
            p["done"].append(p["q_id"])
            p["count"] += 1
            p["last"] = {"correct": correct, "old": round(old * 100), "new": round(new * 100),
                         "colour": M.colour(new)}
            p.update({"q_id": next_question(p["topic"], p["done"]), "hints": 0, "stage": "ask", "answer": ""})
        session["practice"] = p
        return redirect(url_for("practice"))

    q = STATE["bank"].set_index("q_id").loc[p["q_id"]]
    match = keyword_match(p.get("answer", ""), q.keywords) if p["stage"] == "check" else None
    topics = STATE["topics"][["topic", "name"]].to_dict("records")
    last = p.pop("last", None)
    session["practice"] = p
    return render_template("practice.html", p=p, q=q, match=match, topics=topics, last=last,
                           topic_name=STATE["names"].get(p["topic"], "All topics"))


# ------------------------------------------------------------------ Progress
@app.route("/progress")
@student_required
def progress():
    visit("progress")
    m = my_mastery()
    items, nxt = topic_panel(m)
    answers = [a for a in read_sheet("Answers") if a.get("student_code") == student()]
    stats = {"answered": len(answers), "correct": sum(str(a["correct"]) in ("1", "True") for a in answers),
             "green": sum(i["colour"] == "green" for i in items), "total": len(items)}
    return render_template("progress.html", items=items, nxt=nxt, stats=stats)


# ------------------------------------------------------------------ Evaluation
@app.route("/evaluation")
def evaluation():
    visit("evaluation")
    path = config.REPORTS_DIR / "metrics.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return render_template("evaluation.html", r=report)


# ------------------------------------------------------------------ Lecturer: login, dashboard, admin
@app.route("/lecturer", methods=["GET", "POST"])
def lecturer_login():
    if request.method == "POST":
        if request.form.get("password") == config.LECTURER_PASSWORD:
            session["lecturer"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Wrong password.")
    return render_template("lecturer_login.html")


@app.route("/dashboard")
@lecturer_required
def dashboard():
    visit("dashboard")
    names = STATE["names"]
    qs, ans, visits = read_sheet("Questions"), read_sheet("Answers"), read_sheet("Visits")
    asked = Counter(q["topic"] for q in qs if q.get("topic"))
    score = defaultdict(list)
    for a in ans:
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
        m = M.replay([a for a in ans if a["student_code"] == c], STATE["qid_topic"])
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
    if request.method == "POST":
        action = request.form.get("action")
        if action == "upload":
            f = request.files.get("pdf")
            if not f or not f.filename.lower().endswith(".pdf"):
                flash("Please choose a PDF file.")
                return redirect(url_for("admin"))
            num = request.form.get("lecture_number", "").strip()
            title = re.sub(r"[^A-Za-z0-9 _-]", "", request.form.get("title", "")).strip() or "New lecture"
            if not num.isdigit():
                m = re.search(r"lecture\s*[_-]?\s*(\d+)", f.filename, re.I)
                num = m.group(1) if m else ""
            if not num.isdigit():
                flash("Please give the lecture number.")
                return redirect(url_for("admin"))
            name = secure_filename(f"lecture {int(num)} {title}.pdf").replace("_", " ")
            for old in config.LECTURES_DIR.glob(f"lecture {int(num)} *.pdf"):
                old.unlink()   # replacing an existing lecture
            f.save(config.LECTURES_DIR / name)
            flash(f"Saved {name}.")
        if action in ("upload", "rebuild"):
            from core.passages import build_passages
            clf = STATE["clf"]
            df = build_passages(predict_topic=lambda text: clf.predict(text)[0], verbose=False)
            build_index(df)
            load_state()
            flash(f"Index rebuilt: {len(df)} passages from {df.lecture.nunique()} lectures.")
        if action == "retrain":
            import scripts.train as T
            import scripts.evaluate as E
            T.train(verbose=False)
            build_index()
            E.main()
            load_state()
            flash("Classifier retrained and evaluation updated.")
        return redirect(url_for("admin"))
    visit("admin")
    passages = pd.read_csv(config.PASSAGES_CSV)
    lectures = (passages.groupby(["lecture", "lecture_title"]).agg(passages=("passage_id", "count"),
                topics=("topic", lambda s: ", ".join(STATE["names"].get(t, t) for t in sorted(set(s)))))
                .reset_index().to_dict("records"))
    return render_template("admin.html", lectures=lectures, total=len(passages),
                           bank=len(STATE["bank"]), threshold=STATE["engine"].threshold,
                           model=KIND_NAME.get(STATE["clf"].kind, STATE["clf"].kind))


@app.route("/lecturer/logout")
def lecturer_logout():
    session.pop("lecturer", None)
    return redirect(url_for("ask") if student() else url_for("start"))


load_state()

if __name__ == "__main__":
    import os
    # locally: http://127.0.0.1:5000 ; on a server (Hugging Face) HOST/PORT come from the environment
    app.run(debug=False, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)))
