# Data Card – StudyMate (Course Study Assistant, Project 1E)

**Course:** Artificial Intelligence (CSC 412), Benha University – Faculty of Engineering
**Real partner:** the course lecturer (permission to use the slides; reviews topics, question bank and answers)

## 1. Sources
| File | What it is | Source |
|---|---|---|
| `lectures/*.pdf` | 7 lecture PDFs (260 slides) | Course lecturer, used with permission |
| `passages.csv` | 200 passages, one per slide (60 empty / picture-only / title slides dropped) | Extracted with **pypdf** by `scripts/build_passages.py` |
| `topics.csv`, `topic_map.csv` | 12 topics, their prerequisites, and which slides belong to each topic | Written by the team from the lecture agenda |
| `question_bank.csv` | 72 practice questions (6 per topic) with hint 1, clearer hint 2, answer, key ideas, lecture + slide | Written by the team from the slides |
| `questions_labeled.csv` | **466 student-style questions**, 37–40 per topic, labelled with their topic | Written by the team (first draft prepared with an AI assistant, then reviewed against the slides) |
| `search_test.csv` | 94 questions, each with the correct slide(s) (30 original + 64 added) | Written by the team, deliberately in different words from the slides |
| `offtopic_test.csv` | 50 questions that are not in the course and must return "Not found" (tuned on the even rows, reported on the odd rows) | Written by the team |
| `question_variants.csv` | 94 short student phrasings, each attached to one slide (added to the search index only, never to a test set) | Written by the team |
| `arabic_glossary.csv` | 76 Arabic → English course terms (bonus: Arabic questions) | Written by the team |

## 2. Size and labels
- **Topics (12):** Introduction to AI · Intelligent Agents · Environment Properties · Problem Formulation · BFS & Uniform-Cost Search · DFS, DLS & IDS · Heuristics & Greedy Search · A* Search · Minimax · Alpha-Beta Pruning · Probability & Bayes Networks · Probabilistic Inference
- Labelled questions are balanced: 37–40 per topic (372 train / 94 test, stratified 80/20, seed 42).
- Passages per topic range from 8 (Environment Properties) to 26 (Probabilistic Inference).

## 3. How it was collected and labelled
1. Slides were extracted with pypdf, one passage per slide. Cleaning: removed footers ("LECTURE 3", "LEC 5"), converted symbol-font letters (α, β, ε) to words, split words the PDF glued together ("Bayesnetwork" → "Bayes network"), dropped slides with fewer than 6 words.
2. Topics were defined from the lecture agenda; every slide range was mapped to one topic in `topic_map.csv`.
3. **Labelling rule:** a question gets the topic of the slide that answers it. If two topics fit, the more specific one wins (e.g. "is h admissible for A*?" → A* Search, not Heuristics).
4. Student-style questions include informal wording, very short questions and real spelling mistakes ("breath first search", "huristic", "alfa beta") so the model is tested on how students really type.
5. The search test and off-topic sets are kept **separate**: they are never used to train the classifier. Two near-miss off-topic questions about neural networks were replaced because Lecture 1 (slides 9–10) actually mentions neural networks.

## 4. Privacy
- The slides contain no personal data. The lecturers' names on the title slides are not indexed.
- Students register with first/last name, e-mail and a numeric university code; passwords are stored only as hashes. The logs use the student code, never the name. `logs.xlsx` stores the code, the question, the topic, the first slide, whether it helped, and practice results (question ID, correct, hints used).
- `logs.xlsx` stays on the computer running the app and is not shared.

## 5. Known limitations
- Picture-only slides (worked examples on images, e.g. greedy/A* examples) have no text and cannot be found.
- The labelled questions were written by the team, not collected from real students; a real-student collection (e.g. Google Form) would make the test more realistic.
- TF-IDF matches words, not meaning: heavily paraphrased questions ("fool a human judge" → Turing test) can be missed. The student phrasings in `question_variants.csv` reduce this (Top-1 75.5% → 80.9% on the same 94 questions).
