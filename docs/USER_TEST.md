# Real user test (5 students) — protocol and results sheet

The numbers on the "AI models" page come from test sets that we wrote ourselves. This test checks the site with real
students, because the project brief requires it.

## Before the session
1. Make 5 student accounts (or let the 5 students register with their university code).
2. Pick the course (AI) and don't give the students any example questions.

## The session (about 15 minutes per student)
1. Ask each student to write **10 real questions** about the lectures, in their own words (Arabic or English, typos are fine),
   plus **2 questions from outside the course**.
2. After each answer, the student presses 👍 or 👎 (the site saves it in the Questions sheet → `helpful`).
3. Write down anything they found confusing in the interface (one line each).

## After the session
* **Admin → Weekly report → the course**: "Questions the slides could not answer" lists the questions that got *Not found*.
* `logs.xlsx` → sheet *Questions*: filter by the 5 students, then fill in the table below.
* Every question that failed goes to `data/AI/question_variants.csv` (with the slide that answers it) **after** the test,
  so it is not used to grade the test itself. Then run `python scripts/train.py && python scripts/evaluate.py`.

## Results sheet

| Student | Questions | Right slide in top 3 | 👍 | 👎 | Wrongly "Not found" | Off-topic correctly refused (of 2) | UI notes |
|---|---|---|---|---|---|---|---|
| S1 | 10 | | | | | | |
| S2 | 10 | | | | | | |
| S3 | 10 | | | | | | |
| S4 | 10 | | | | | | |
| S5 | 10 | | | | | | |
| **Total** | 50 | __ / 50 | | | | __ / 10 | |

Report the total line as "real-user top-3 accuracy" next to the test-set numbers. It is usually lower, and that is the honest
number.
