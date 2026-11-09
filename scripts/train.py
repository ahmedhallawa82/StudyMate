"""Step 2: train the topic classifiers (NB + LR) and build the search index.

Run from the project folder:  python scripts/train.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score

import config
from core.classifier import make_pipeline, TopicClassifier, KIND_NAME
from core.search import build_index

SPLIT_FILE = config.MODELS_DIR / "split.joblib"


def train(verbose=True):
    config.MODELS_DIR.mkdir(exist_ok=True)
    df = pd.read_csv(config.LABELED_CSV).dropna()
    train_idx, test_idx = train_test_split(df.index, test_size=0.2, stratify=df.topic,
                                           random_state=config.RANDOM_STATE)
    joblib.dump({"train": list(train_idx), "test": list(test_idx)}, SPLIT_FILE)
    tr, te = df.loc[train_idx], df.loc[test_idx]
    # extra training text (never used for testing): question-bank questions and the slide text itself,
    # each labelled with its topic. This teaches the model the course vocabulary.
    extra = [pd.read_csv(config.QUESTION_BANK_CSV)[["question", "topic"]]]
    if config.PASSAGES_CSV.exists():
        p = pd.read_csv(config.PASSAGES_CSV)
        p = p[p.topic.isin(df.topic.unique())]
        extra.append(p.rename(columns={"text": "question"})[["question", "topic"]])
    tr = pd.concat([tr] + extra, ignore_index=True)
    if verbose:
        print(f"  {len(df)} labelled questions, {df.topic.nunique()} topics -> "
              f"train {len(train_idx)} questions (+{len(tr) - len(train_idx)} bank/slide texts) / test {len(te)}")

    results = {}
    for kind in ("nb", "logreg"):
        pipe = make_pipeline(kind).fit(tr.question, tr.topic)
        pred = pipe.predict(te.question)
        results[kind] = (f1_score(te.topic, pred, average="macro"), accuracy_score(te.topic, pred), pipe)
        if verbose:
            print(f"  {KIND_NAME[kind]:<20} accuracy={results[kind][1]:.3f}  macro-F1={results[kind][0]:.3f}")

    best = max(results, key=lambda k: results[k][0])
    for kind, (_, _, pipe) in results.items():
        TopicClassifier(pipe, kind).save(best=(kind == best))
    joblib.dump(best, config.MODELS_DIR / "best_kind.joblib")
    if verbose:
        print(f"  best model: {KIND_NAME[best]} (saved as models/topic_classifier.joblib)")
    return best


if __name__ == "__main__":
    print("Training topic classifiers ...")
    train()
    print("Building search index ...")
    eng = build_index()
    print(f"  indexed {len(eng.passages)} passages")
