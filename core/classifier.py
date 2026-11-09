"""Topic classifier: question -> topic (Multinomial Naive Bayes or Logistic Regression)."""
import joblib
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LogisticRegression

import config
from core.text import normalize_question
from core.search import translate_arabic

MODEL_FILE = config.MODELS_DIR / "topic_classifier.joblib"      # the best model (used by the app)
KIND_FILE = {"nb": config.MODELS_DIR / "topic_classifier_nb.joblib",
             "logreg": config.MODELS_DIR / "topic_classifier_logreg.joblib"}
KIND_NAME = {"nb": "Naive Bayes", "logreg": "Logistic Regression"}


def preprocess(q: str) -> str:
    return normalize_question(translate_arabic(q))


def make_pipeline(kind: str = "logreg") -> Pipeline:
    # word n-grams catch terms ("uniform cost"), character n-grams survive typos ("serch", "huristic")
    features = FeatureUnion([
        ("word", TfidfVectorizer(preprocessor=preprocess, ngram_range=(1, 2), sublinear_tf=True)),
        ("char", TfidfVectorizer(preprocessor=preprocess, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)),
    ])
    if kind == "nb":
        model = MultinomialNB(alpha=0.1)
    else:
        model = LogisticRegression(C=10, max_iter=2000, random_state=config.RANDOM_STATE)
    return Pipeline([("features", features), ("model", model)])


class TopicClassifier:
    def __init__(self, pipeline: Pipeline, kind: str):
        self.pipeline, self.kind = pipeline, kind

    def predict(self, question: str):
        """Return (topic, confidence 0-1)."""
        proba = self.pipeline.predict_proba([question])[0]
        i = proba.argmax()
        return self.pipeline.classes_[i], float(proba[i])

    def probs(self, question: str) -> dict:
        proba = self.pipeline.predict_proba([question])[0]
        return dict(zip(self.pipeline.classes_, map(float, proba)))

    def save(self, best: bool = False):
        config.MODELS_DIR.mkdir(exist_ok=True)
        joblib.dump(self, KIND_FILE[self.kind])
        if best:
            joblib.dump(self, MODEL_FILE)

    @staticmethod
    def load(kind: str = None):
        path = KIND_FILE.get(kind, MODEL_FILE) if kind else MODEL_FILE
        return joblib.load(path if path.exists() else MODEL_FILE)
