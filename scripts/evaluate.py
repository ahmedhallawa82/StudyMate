"""Step 3: evaluate everything and write static/reports/ (read by the Evaluation page).

- topic classifier: accuracy, precision / recall / F1 per class, confusion matrix, error analysis
- search: top-1 and top-3 hit rate (TF-IDF and BM25) on the 30-question search test
- "Not found": tunes the similarity threshold so the 10 off-topic questions return "Not found"
- robustness: typos, lower/upper case, very short questions, extra words, Arabic questions

Run from the project folder:  python scripts/evaluate.py
"""
import sys
import json
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

import config
from core.classifier import TopicClassifier, KIND_NAME
from core.search import SearchEngine, THRESHOLD_FILE
from core.topics import topic_names

rng = random.Random(config.RANDOM_STATE)

# Arabic / mixed questions for the robustness test (bonus: Arabic support), with the expected topic
ARABIC_TESTS = [
    ("ايه هو البحث بالعرض", "bfs_ucs"),
    ("ما هو البحث بالعمق", "dfs_ids"),
    ("يعني ايه دالة استدلالية مقبولة", "astar"),
    ("ما هي خوارزمية مينيماكس", "minimax"),
    ("ايه هو التقليم الفا بيتا", "alpha_beta"),
    ("ما هي شبكة بايز", "probability_bayes"),
    ("ايه الفرق بين البيئة الحتمية والعشوائية", "environments"),
    ("ما هو اختبار تورنج", "intro_ai"),
    ("ما هو الوكيل العقلاني", "agents"),
    ("ايه هو حذف المتغيرات", "inference"),
]


# ---------------------------------------------------------------- perturbations
def typo(q):
    words = q.split()
    for _ in range(max(1, len(words) // 3)):
        i = rng.randrange(len(words))
        w = words[i]
        if len(w) > 3:
            j = rng.randrange(1, len(w) - 1)
            op = rng.choice(["drop", "swap", "double"])
            if op == "drop":
                w = w[:j] + w[j + 1:]
            elif op == "swap":
                w = w[:j - 1] + w[j] + w[j - 1] + w[j + 1:]
            else:
                w = w[:j] + w[j] + w[j:]
        words[i] = w
    return " ".join(words)


def short(q):
    from core.search import tokenize
    toks = tokenize(q)
    return " ".join(toks[:2]) if toks else q


PERTURB = {
    "original": lambda q: q,
    "typos": typo,
    "UPPER CASE": lambda q: q.upper(),
    "very short (2 key words)": short,
    "extra words": lambda q: f"hi doctor, quick question please: {q} ?? thanks",
}


def save_confusion(y_true, y_pred, labels, names, path, title):
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(9, 7.5))
    ax.imshow(cm, cmap="Greens")
    ax.set_xticks(range(len(labels)), [names[l] for l in labels], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)), [names[l] for l in labels], fontsize=8)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                ax.text(j, i, cm[i, j], ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=9)
    ax.set_xlabel("Predicted topic")
    ax.set_ylabel("True topic")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def hit_rates(engine, test, method, clf=None):
    top1 = top3 = 0
    rows = []
    for _, r in test.iterrows():
        accepted = set(str(r.accepted).split(";"))
        s = engine.ranked_scores(r.question, method, clf.probs(r.question) if clf else None)
        idx = np.argsort(-s)[:3]
        ids = [engine.passages.iloc[i].passage_id for i in idx]
        h1, h3 = ids[0] in accepted, any(i in accepted for i in ids)
        top1 += h1
        top3 += h3
        rows.append({"question": r.question, "correct": str(r.accepted), "top3": ", ".join(ids),
                     "top1_hit": bool(h1), "top3_hit": bool(h3), "best_score": round(float(s.max()), 3)})
    n = len(test)
    return top1 / n, top3 / n, rows


def tune_threshold(engine, real_questions, offtopic_questions):
    """Grid-search the two 'Not found' rules (best similarity and course-vocabulary coverage).
    Goal: reject every off-topic question while answering as many course questions as possible.
    Ties -> the most lenient similarity threshold in the middle of the safe range."""
    rs = np.array([engine.best_score(q) for q in real_questions])
    rc = np.array([engine.coverage(q) for q in real_questions])
    os_ = np.array([engine.best_score(q) for q in offtopic_questions])
    oc = np.array([engine.coverage(q) for q in offtopic_questions])
    best, best_key = (config.DEFAULT_NOT_FOUND_THRESHOLD, 0.5), None
    for t in np.round(np.arange(0.02, 0.30, 0.005), 3):
        for c in np.round(np.arange(0.3, 0.85, 0.05), 2):
            rejected = ((os_ < t) | (oc < c)).sum()
            answered = ((rs >= t) & (rc >= c)).sum()
            key = (rejected, answered, -c, -t)   # rejecting every off-topic question comes first
            if best_key is None or key > best_key:
                best, best_key = (float(t), float(c)), key
    return best, rs, os_, rc, oc


def main():
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    names = topic_names()
    labels = list(names.keys())
    df = pd.read_csv(config.LABELED_CSV).dropna()
    split = joblib.load(config.MODELS_DIR / "split.joblib")
    te = df.loc[split["test"]]
    best_kind = joblib.load(config.MODELS_DIR / "best_kind.joblib")
    report = {"best_model": KIND_NAME[best_kind], "n_test": len(te), "n_labelled": len(df),
              "topics": [{"topic": t, "name": names[t]} for t in labels], "models": {}}

    # ---------------- 1) topic classifier
    print("Topic classifier")
    for kind in ("nb", "logreg"):
        clf = TopicClassifier.load(kind)
        pred = clf.pipeline.predict(te.question)
        rep = classification_report(te.topic, pred, labels=labels, output_dict=True, zero_division=0)
        per_class = [{"topic": names[t], "precision": round(rep[t]["precision"], 3),
                      "recall": round(rep[t]["recall"], 3), "f1": round(rep[t]["f1-score"], 3),
                      "support": int(rep[t]["support"])} for t in labels]
        img = f"confusion_matrix_{kind}.png"
        save_confusion(te.topic, pred, labels, names, config.REPORTS_DIR / img,
                       f"Topic classifier - {KIND_NAME[kind]} (test set, n={len(te)})")
        errors = [{"question": q, "true": names[t], "predicted": names[p]}
                  for q, t, p in zip(te.question, te.topic, pred) if t != p]
        report["models"][kind] = {
            "name": KIND_NAME[kind], "accuracy": round(accuracy_score(te.topic, pred), 3),
            "macro_f1": round(f1_score(te.topic, pred, average="macro"), 3),
            "macro_precision": round(rep["macro avg"]["precision"], 3),
            "macro_recall": round(rep["macro avg"]["recall"], 3),
            "per_class": per_class, "confusion_matrix": img, "errors": errors,
        }
        print(f"  {KIND_NAME[kind]:<20} acc={report['models'][kind]['accuracy']:.3f} "
              f"macroF1={report['models'][kind]['macro_f1']:.3f}  errors={len(errors)}")

    # ---------------- 2) search + threshold
    print("Search")
    engine = SearchEngine.load()
    test = pd.read_csv(config.SEARCH_TEST_CSV)
    offtopic = pd.read_csv(config.OFFTOPIC_CSV)
    # tuning uses the search-test questions + the TRAINING student questions (not the classifier test set)
    real_q = list(test.question) + list(df.loc[split["train"]].question)
    (thr, cov), real_scores, off_scores, real_cov, off_cov = tune_threshold(engine, real_q, offtopic.question)
    joblib.dump({"similarity": thr, "coverage": cov}, THRESHOLD_FILE)
    engine.threshold, engine.min_coverage = thr, cov
    report["search"] = {"threshold": thr, "min_coverage": cov, "n_test": len(test), "methods": {}}
    for method, label in (("tfidf", "TF-IDF + cosine (default)"), ("bm25", "BM25 (bonus)"),
                          ("lsa", "Semantic LSA (bonus)"), ("hybrid", "Hybrid TF-IDF + LSA (bonus)")):
        if method == "bm25" and engine.bm25 is None:
            continue
        key = method
        t1, t3, rows = hit_rates(engine, test, method)
        report["search"]["methods"][key] = {"name": label, "top1": round(t1, 3), "top3": round(t3, 3),
                                            "rows": rows}
        print(f"  {label:<44} top-1={t1:.3f}  top-3={t3:.3f}")
    n_st = len(test)
    answered = (real_scores >= thr) & (real_cov >= cov)
    report["search"]["real_found"] = int(answered[:n_st].sum())
    report["search"]["student_questions_answered"] = round(float(answered[n_st:].mean()), 3)
    off_rej = (off_scores < thr) | (off_cov < cov)
    report["offtopic"] = {
        "threshold": thr, "min_coverage": cov,
        "rows": [{"question": q, "best_score": round(float(s), 3), "coverage": round(float(c), 2),
                  "result": "Not found" if r else "FOUND (wrong)"}
                 for q, s, c, r in zip(offtopic.question, off_scores, off_cov, off_rej)],
        "rejected": int(off_rej.sum()), "total": len(offtopic),
    }
    print(f"  similarity>={thr} and coverage>={cov}: off-topic rejected {report['offtopic']['rejected']}/{len(offtopic)}, "
          f"search-test answered {report['search']['real_found']}/{n_st}, "
          f"student questions answered {report['search']['student_questions_answered']:.1%}")
    real_scores, off_scores = real_scores[:n_st], off_scores

    # score histogram
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.hist(real_scores, bins=15, alpha=.75, label="course questions (search test)", color="#2f6f6a")
    ax.hist(off_scores, bins=8, alpha=.75, label="off-topic questions", color="#d9534f")
    ax.axvline(thr, color="black", ls="--", label=f"threshold = {thr}")
    ax.set_xlabel("best cosine similarity")
    ax.set_ylabel("questions")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(config.REPORTS_DIR / "threshold.png", dpi=130)
    plt.close(fig)

    # ---------------- 3) robustness
    print("Robustness")
    clf = TopicClassifier.load()
    rob = []
    for name, fn in PERTURB.items():
        qs = [fn(q) for q in te.question]
        acc = accuracy_score(te.topic, clf.pipeline.predict(qs))
        sq = [fn(q) for q in test.question]
        s_hits = 0
        for q, (_, r) in zip(sq, test.iterrows()):
            found, res = engine.search(q)
            s_hits += found and any(x["passage_id"] in str(r.accepted).split(";") for x in res)
        rob.append({"test": name, "example": qs[0], "classifier_accuracy": round(acc, 3),
                    "search_top3": round(s_hits / len(test), 3)})
        print(f"  {name:<26} classifier={acc:.3f}  search top-3 (with threshold)={s_hits / len(test):.3f}")
    ar_pred = [clf.predict(q)[0] for q, _ in ARABIC_TESTS]
    ar_acc = np.mean([p == t for p, (_, t) in zip(ar_pred, ARABIC_TESTS)])
    ar_found = np.mean([engine.search(q)[0] for q, _ in ARABIC_TESTS])
    rob.append({"test": "Arabic questions (bonus)", "example": ARABIC_TESTS[0][0],
                "classifier_accuracy": round(float(ar_acc), 3), "search_top3": None,
                "note": f"search answered {ar_found:.0%} of them (not 'Not found')"})
    print(f"  Arabic questions           classifier={ar_acc:.3f}  answered={ar_found:.0%}")
    report["robustness"] = rob
    report["arabic_examples"] = [{"question": q, "expected": names[t], "predicted": names[p]}
                                 for (q, t), p in zip(ARABIC_TESTS, ar_pred)]

    with open(config.REPORTS_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Saved {config.REPORTS_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
