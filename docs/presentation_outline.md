# 10-minute presentation – StudyMate (Project 1E)

| Time | Slide / action | What to say or show |
|---|---|---|
| 0:00–1:00 | **Problem** | Before exams students don't know which topics they understand or in which order to study. General chatbots answer confidently but not from *our* slides. |
| 1:00–2:00 | **Solution + partner** | A tutor for one course (AI). Answers only from the slides with lecture + slide number, detects the topic, practice with hints, progress colours, study next. Partner: the course lecturer. |
| 2:00–3:00 | **Data** | 7 lectures → 200 passages (pypdf). 12 topics. 72-question bank, 360 labelled student questions, 30 search tests, 10 off-topic. Show the data card. |
| 3:00–6:30 | **Live demo** | 1) Log in as S001. 2) Ask "What is an admissible heuristic?" → Lecture 4 · Slide 25. **Open the original PDF at slide 25 next to it – compare the assistant's answer with the slide (required).** 3) Ask "who won the world cup" → Not found. 4) Ask in Arabic «ايه هو البحث بالعرض». 5) Practice: hint → clearer hint → answer → mastery changes colour. 6) My progress + Study next with the reason. 7) Lecturer dashboard. 8) Admin: upload a PDF. |
| 6:30–8:30 | **Evaluation** | Topic accuracy LR 88.9% vs NB 86.1%, confusion matrix, 2–3 errors and why. Search top-1 70%, top-3 77%. Off-topic 10/10 with the threshold plot. Robustness: typos keep 88.9%. |
| 8:30–9:30 | **Lecturer feedback + limits** | What the lecturer said in the real user test. Limits: picture-only slides, paraphrases, questions written by the team. |
| 9:30–10:00 | **Summary + bonus** | BM25, Arabic questions, automatic tests. Next: LLM that rephrases only from the retrieved slides, deployment on PythonAnywhere. |

Tip: rehearse the demo twice; keep `python app.py` running and the PDF open before you start.
