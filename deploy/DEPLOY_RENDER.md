# Put StudyMate online for free (GitHub + Render)

1. Create a GitHub repo `StudyMate` (Public) and upload everything from the unzipped folder (drag the folders themselves).
2. On https://render.com sign in with GitHub -> New + -> Web Service -> pick `StudyMate`.
3. Runtime Python, Build `pip install -r requirements.txt`, Start `gunicorn app:app --workers 1 --threads 4 --timeout 120`, Instance Free.
4. Environment: PYTHON_VERSION=3.11.9, LECTURER_PASSWORD=<your password>, SECRET_KEY=<any long text>.
5. Create Web Service, wait ~5 min -> link `https://studymate-xxxx.onrender.com`.
Free instance sleeps after 15 min idle (first visit ~50 s). logs.xlsx resets on redeploy: download it from the Dashboard first.
