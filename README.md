# StudyMate – Course Study Assistant (AI Lab · Project 1E)

A study assistant for **one course** (Artificial Intelligence). It answers only from the lecture slides and always shows the lecture and slide number, detects the topic of each question, gives practice questions with hints, tracks each student's level per topic and suggests what to study next. If a question is not in the course it answers **"Not found in the course"** instead of inventing an answer.

## Run it (Windows, VS Code)
```bash
cd "1E Course Study Assistant"
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py                    # open http://127.0.0.1:5000
```
The trained models are already included, so `python app.py` works right away.
To rebuild everything from the PDFs:
```bash
python scripts/build_passages.py   # 1) PDFs -> data/AI/passages.csv (pypdf)
python scripts/train.py            # 2) topic classifiers (NB + LR) + search index
python scripts/evaluate.py         # 3) metrics, confusion matrix, threshold, robustness -> static/reports/
python -m pytest -q                # 4) 17 automatic tests
```
Lecturer pages (Dashboard, Admin) password: `lecturer123` by default. Set your own with the environment variable `LECTURER_PASSWORD`.

## New in this version
- **Arabic / English interface** – the button in the header switches the whole interface (right-to-left in Arabic). Slides and practice questions stay in the course language.
- **Dark mode** – the button next to it switches light / dark; the first visit follows the device setting.
- **Several courses** – pick the course on the start page or from the header menu. Every course has its own slides, topics, practice questions, progress and dashboard.
  Admin → *Add a new course*: upload the lecture PDFs (`lecture 1 Intro.pdf` …) and StudyMate builds the index, one topic per lecture, a classifier and fill-in-the-blank practice questions automatically.
  The first course (Artificial Intelligence) is the fully evaluated one (question bank, 360 labelled questions, search test, off-topic test).

## Pages
| Page | What it does |
|---|---|
| **Ask** | Question box → detected topic + confidence, the 3 closest passages with "Lecture X · Slide Y" and highlighted words, or "Not found in the course". TF-IDF or BM25. "Was this helpful?" Yes/No. Side panel: my topics (coloured dots) + "Study next" with the reason. Arabic questions work too. |
| **Practice** | One question at a time → Show hint → Show a clearer hint → Check / Show the answer → "I got it right / wrong". Sets of 5 per topic. |
| **My progress** | Every topic in red / amber / green with its %, plus "Study next" and why (based on topic prerequisites). |
| **Evaluation** | Accuracy, precision, recall, F1 per class, confusion matrices (NB and LR), error analysis, search top-1/top-3, off-topic test, robustness tests. |
| **Dashboard** (lecturer) | Most asked topics, topics with the lowest scores, students per colour, visits per day, latest "Not found" questions – read live from `logs.xlsx`. |
| **Admin** (lecturer) | Upload a new lecture PDF and rebuild the index; retrain + re-evaluate. |

## Models
- **Search:** TF-IDF (word 1–2 grams) + cosine similarity; bonus: BM25 (`rank_bm25`). "Not found" when the best similarity is below a tuned threshold **or** too few question words exist in the slides.
- **Topic classifier:** question → one of 12 topics. Multinomial Naive Bayes vs Logistic Regression on word + character n-grams (character n-grams handle typos). The best (LR) is used by the app.
- **Mastery update:** `level = level + 0.35 × (result − level)`; result = 1 (correct, no hint), 0.7 (1 hint), 0.4 (2 hints), 0 (wrong). Red < 40% ≤ amber < 70% ≤ green.

## Results (from `python scripts/evaluate.py`)
| | |
|---|---|
| Topic accuracy – Logistic Regression | **88.9%** (macro F1 0.889, 72 test questions) |
| Topic accuracy – Naive Bayes | 86.1% (macro F1 0.858) |
| Search top-1 / top-3 hit rate (TF-IDF) | **70% / 77%** (30 test questions) |
| Search top-1 / top-3 hit rate (BM25) | 67% / 77% |
| Off-topic questions → "Not found" | **10 / 10** |
| Arabic questions (bonus) → right topic | 10 / 10 |

## Excel database – `logs.xlsx`
Created automatically. Every write goes through one function, `log_to_excel()` in `core/logger.py`.
- **Questions:** id, time, student_code, question, topic, confidence, first_slide, found, method, helpful
- **Answers:** id, time, student_code, question_id, topic, correct, hints_used, mastery_after
- **Visits:** id, time, student_code, page
- **Feedback:** id, time, student_code, question_log_id, helpful, comment

## Project structure
```
app.py                 Flask app (all pages)
config.py              paths and settings
core/                  text cleaning, passages (pypdf), search, classifier, mastery, topics, logger, i18n (AR/EN), autocourse
scripts/               build_passages.py, train.py, evaluate.py
data/AI/               lectures/*.pdf, passages.csv, topics.csv, topic_map.csv, question_bank.csv,
                       questions_labeled.csv, search_test.csv, offtopic_test.csv, arabic_glossary.csv, data_card.md
models/                saved models (joblib)
static/reports/        metrics.json, confusion matrices, threshold plot (used by the Evaluation page)
templates/, static/    HTML (Jinja2), CSS, Chart.js
tests/                 pytest tests (17)
notebooks/             StudyMate_Colab_Test.ipynb – run and test the project on Google Colab
docs/                  presentation outline + delivery checklist
```

## Interface themes
Five colour themes are included: `teal`, `midnight`, `notebook`, `indigo` (default), `benha`. Change `THEME` in `config.py`,
or preview any page with `?theme=midnight` in the address bar.

## Online version (bonus: deployment)
`render.yaml` + `deploy/DEPLOY_RENDER.md`: run the real Flask app free on Render from GitHub (Hugging Face Docker files are also in `deploy/huggingface/`).

## Bonus items included
Deployment (GitHub + free hosting) · BM25 search · Arabic questions (glossary translation) · Arabic interface · dark mode · multi-course · automatic tests · Colab notebook · 5 themes.
