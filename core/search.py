"""Passage search: TF-IDF + cosine similarity (main) and BM25 (bonus)."""
import re
import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config
from core.text import normalize_question, ARABIC_RE

try:
    from rank_bm25 import BM25Okapi
except Exception:  # bonus only
    BM25Okapi = None

INDEX_FILE = config.MODELS_DIR / "search_index.joblib"            # default course (kept for scripts)
THRESHOLD_FILE = config.MODELS_DIR / "search_threshold.joblib"


def index_file(course=None):
    return config.course_paths(course).models / "search_index.joblib"


def threshold_file(course=None):
    return config.course_paths(course).models / "search_threshold.joblib"

# small stop list for highlighting / BM25 tokens
STOP = set("""a an the is are was were be been of in on at to for from by with and or not what which who whom
how why when where does do did can could should would will shall this that these those it its as if then than
so such into about between vs versus me my i you your we our they their give tell explain define meaning mean
please difference example examples work works working best good use used using get make made way ways thing
things time times home last first new need needs want like know show find right now hi hello thanks doctor
question quick simple words lecture slide means mean""".split())

# generic English words that must not create a match on their own
EXTRA_STOP = sorted(STOP | {"world", "fix", "program", "real", "life", "people", "day", "close", "open"})


# ---------------- Arabic bonus: translate course terms with a glossary ----------------
_glossary = None


def _load_glossary():
    global _glossary
    if _glossary is None:
        _glossary = []
        pairs = []
        for f in sorted((config.BASE_DIR / "data").glob("*/arabic_glossary.csv")):   # every course adds its terms
            g = pd.read_csv(f)
            pairs += list(zip(g.arabic, g.english))
        # longest phrases first so "البحث بالعرض" wins over "البحث"
        _glossary = sorted(pairs, key=lambda x: -len(x[0]))
    return _glossary


def translate_arabic(q: str) -> str:
    """Replace known Arabic course terms with English ones (keeps English words as they are)."""
    if not ARABIC_RE.search(q or ""):
        return q
    out = q
    for ar, en in _load_glossary():
        out = out.replace(ar, f" {en} ")
    out = ARABIC_RE.sub(" ", out)          # drop Arabic words we do not know
    return re.sub(r"\s+", " ", out).strip()


def prepare_query(q: str) -> str:
    return normalize_question(translate_arabic(q))


def tokenize(text: str):
    return [t for t in normalize_question(text).split() if t not in STOP and len(t) > 1]


class SearchEngine:
    """Holds the passages and both indexes."""

    def __init__(self, passages: pd.DataFrame):
        self.passages = passages.reset_index(drop=True)
        extra = self.passages["index_extra"] if "index_extra" in self.passages else ""
        docs = (self.passages["text"] + " " + self.passages["topic_name"] + " " + extra).map(normalize_question)
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                          stop_words=sorted(ENGLISH_STOP_WORDS | set(EXTRA_STOP)),
                                          min_df=1, max_df=0.6)
        self.matrix = self.vectorizer.fit_transform(docs)
        self.bm25 = BM25Okapi([tokenize(d) for d in docs]) if BM25Okapi else None
        self.vocab = {t for d in docs for t in tokenize(d) if t.isalpha() and len(t) > 2}
        self.threshold = config.DEFAULT_NOT_FOUND_THRESHOLD
        self.min_coverage = 0.5
        self.topic_weight = 0.0   # re-ranking boost from the topic classifier (tuned in evaluate.py)
        self._build_lsa()

    # ---------------- semantic (LSA) ----------------
    def _build_lsa(self, dims: int = 100):
        """Latent semantic space: SVD of the TF-IDF matrix. Words that appear in the same slides end up close,
        so a question can match a slide that uses related (not identical) words."""
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import normalize
        n = min(dims, min(self.matrix.shape) - 1)
        self.svd, self.doc_lsa = None, None
        if n >= 2:
            self.svd = TruncatedSVD(n_components=n, random_state=0).fit(self.matrix)
            self.doc_lsa = normalize(self.svd.transform(self.matrix))

    def _lsa(self, q: str) -> np.ndarray:
        if getattr(self, "svd", None) is None:          # engine saved before this feature: build once
            self._build_lsa()
        if self.svd is None:
            return self._tfidf(q)
        from sklearn.preprocessing import normalize
        v = normalize(self.svd.transform(self.vectorizer.transform([q])))
        return np.clip(self.doc_lsa @ v.ravel(), 0, None)

    # ---------------- neural (optional, free) ----------------
    def _neural(self, q: str) -> np.ndarray:
        """Cosine similarity of sentence embeddings blended with TF-IDF; falls back to Hybrid when no model is installed."""
        from core import neural
        if getattr(self, "_nemb", None) is None:
            self._nemb = neural.embed((self.passages["text"] + " " + self.passages["topic_name"]).tolist())
        qv = neural.embed([q]) if self._nemb is not None else None
        if qv is None:
            return 0.5 * self._tfidf(q) + 0.5 * self._lsa(q)
        return 0.7 * np.clip(self._nemb @ qv[0], 0, None) + 0.3 * self._tfidf(q)

    def __getstate__(self):
        d = dict(self.__dict__); d.pop("_nemb", None)       # embeddings are rebuilt on demand, not stored in the index
        return d

    # ---------------- scoring ----------------
    def scores(self, question: str, method: str = "tfidf") -> np.ndarray:
        q = prepare_query(question)
        if method == "neural":
            return self._neural(q)
        if method == "lsa":
            return self._lsa(q)
        if method == "hybrid":                           # exact words (TF-IDF) + related words (LSA)
            return 0.5 * self._tfidf(q) + 0.5 * self._lsa(q)
        if method == "bm25" and self.bm25 is not None:
            s = np.asarray(self.bm25.get_scores(tokenize(q)), dtype=float)
            return s / (s.max() + 1e-9) * self._tfidf(q).max() if s.max() > 0 else s  # same scale as cosine
        return self._tfidf(q)

    def _tfidf(self, q: str) -> np.ndarray:
        return cosine_similarity(self.vectorizer.transform([q]), self.matrix).ravel()

    def coverage(self, question: str) -> float:
        """Share of the question's content words that exist in the course slides (typos allowed)."""
        import difflib
        toks = [t for t in tokenize(prepare_query(question)) if t.isalpha() and len(t) > 2]
        if not toks:
            return 0.0
        vocab = list(self.vocab)
        known = sum(1 for t in toks if t in self.vocab or difflib.get_close_matches(t, vocab, n=1, cutoff=0.82))
        return known / len(toks)

    def is_in_course(self, question: str, method: str = "tfidf"):
        best = self.best_score(question, "tfidf")   # the Not-found gate always uses TF-IDF (tuned threshold)
        return best >= self.threshold and self.coverage(question) >= self.min_coverage, best

    def ranked_scores(self, question: str, method: str = "tfidf", topic_probs: dict = None) -> np.ndarray:
        """Similarity, re-ranked with the classifier: score * (1 + w * P(topic of the passage))."""
        s = self.scores(question, method)
        if topic_probs and self.topic_weight:
            p = self.passages["topic"].map(topic_probs).fillna(0.0).to_numpy()
            s = s * (1 + self.topic_weight * p)
        return s

    def search(self, question: str, k: int = config.TOP_K, method: str = "tfidf", topic_probs: dict = None):
        """Return (found, results). found=False means 'Not found in the course'."""
        ok, _ = self.is_in_course(question, method)
        if not ok:
            return False, []
        s = self.ranked_scores(question, method, topic_probs)
        idx = np.argsort(-s)[:k]
        results = []
        for i in idx:
            if s[i] <= 0:
                continue
            row = self.passages.iloc[i]
            results.append({
                "passage_id": row.passage_id, "lecture": int(row.lecture), "slide": int(row.slide),
                "lecture_title": row.get("lecture_title", ""), "topic": row.topic,
                "text": row.text, "score": round(float(s[i]), 3),
                "display": row.get("display", "") if isinstance(row.get("display", ""), str) else "",
            })
        return True, results

    def best_score(self, question: str, method: str = "tfidf") -> float:
        s = self.scores(question, method)
        return float(s.max()) if len(s) else 0.0

    # ---------------- persistence ----------------
    def save(self, course=None):
        f = index_file(course)
        f.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, f)

    @staticmethod
    def load(course=None):
        eng = joblib.load(index_file(course))
        if threshold_file(course).exists():
            eng.threshold, eng.min_coverage, eng.topic_weight = _read_threshold(course)
        return eng


def _read_threshold(course=None):
    t = joblib.load(threshold_file(course))
    if isinstance(t, dict):
        return t["similarity"], t["coverage"], t.get("topic_weight", 0.0)
    return t, 0.5, 0.0


def build_index(passages: pd.DataFrame = None, topic_names: dict = None, course=None) -> SearchEngine:
    P = config.course_paths(course)
    if passages is None:
        passages = pd.read_csv(P.passages)
    if topic_names is None:
        from core.topics import topic_names as _tn
        topic_names = _tn(course)
    passages = passages.copy()
    passages["topic_name"] = passages["topic"].map(topic_names).fillna("")
    # document expansion: the question-bank questions/answers written for a slide are added to that
    # slide's index text (not to what the student sees), so student wording finds the slide more easily
    passages["index_extra"] = ""
    if P.bank.exists():
        qb = pd.read_csv(P.bank)
        qb["pid"] = [f"L{int(l):02d}S{int(s):02d}" for l, s in zip(qb.lecture, qb.slide)]
        add = qb.groupby("pid").apply(lambda g: " ".join(g.question + " " + g.answer)).to_dict()
        passages["index_extra"] = passages["passage_id"].map(add).fillna("")
    eng = SearchEngine(passages)
    if threshold_file(course).exists():
        eng.threshold, eng.min_coverage, eng.topic_weight = _read_threshold(course)
    eng.save(course)
    return eng


def highlight(text: str, question: str) -> str:
    """Wrap question words found in the passage with <mark> (HTML-escaped)."""
    from markupsafe import escape
    words = {w for w in tokenize(prepare_query(question)) if len(w) > 2}
    safe = str(escape(text))
    if not words:
        return safe
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\w*",
                         flags=re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", safe)
