# 10-minute presentation – StudyMate (Project 1E)

| Time | Slide / action | What to say or show |
|---|---|---|
| 0:00–1:00 | **Problem** | Before exams students don't know which topics they understand or in which order to study. General chatbots answer confidently but not from *our* slides. |
| 1:00–2:00 | **Solution + partner** | A tutor for one course (AI). Answers only from the slides with lecture + slide number, detects the topic, practice with hints, progress colours, study next. Partner: the course lecturer. |
| 2:00–3:00 | **Data** | 7 lectures → 200 passages (pypdf). 12 topics. 72-question bank, 466 labelled student questions, 94 search tests, 50 off-topic (+94 student phrasings for the index). Show the data card. |
| 3:00–6:30 | **Live demo** | 1) Log in as S001. 2) Ask "What is an admissible heuristic?" → Lecture 4 · Slide 25. **Open the original PDF at slide 25 next to it – compare the assistant's answer with the slide (required).** 3) Ask "who won the world cup" → Not found. 4) Ask in Arabic «ايه هو البحث بالعرض». 5) Practice: hint → clearer hint → answer → mastery changes colour. 6) My progress + Study next with the reason. 7) Admin → Data (dashboard). 8) Admin → Content: upload PDFs; show the second course and the course search. |
| 6:30–8:30 | **Evaluation** | Topic accuracy LR 91.5% vs NB 84.0% (5-fold CV 91.2% both), confusion matrix, 2–3 errors and why. Search TF-IDF top-1 80.9%, BM25 top-3 90.4% on 94 questions. Off-topic: the 10 required 10/10, extended 47/50 (22/25 held-out) with the threshold plot. Robustness: typos keep 89.4%. Improvement round: top-1 75.5% → 80.9%. |
| 8:30–9:30 | **Lecturer feedback + limits** | What the lecturer said in the real user test. Limits: picture-only slides, paraphrases, questions written by the team. |
| 9:30–10:00 | **Summary + bonus** | BM25, Arabic questions, automatic tests. Deployed on PythonAnywhere, Arabic interface, dark mode, two courses, doctor accounts. Next: LLM that rephrases only from the retrieved slides. |

Tip: rehearse the demo twice; keep `python app.py` running and the PDF open before you start.
