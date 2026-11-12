# Hand-over guide

## 1. For the doctor / TA (project submission)
Give **one ZIP of the latest `main`** (GitHub → *Code ▸ Download ZIP*) plus:
* the Colab links / the two notebooks (`notebooks/`) and their downloaded results,
* the project PDF report and `docs/presentation_outline.md` (10-minute presentation),
* the live link <https://ahmedhallawa.pythonanywhere.com> and a doctor test account.

The ZIP already contains everything needed to run the project: code, the 7 AI lectures, trained models, data card, test sets, README, tests.
It does **not** contain students, passwords or logs (they are never committed).

## 2. Never hand over
`data/students.json`, `data/doctors.json`, `data/admin_auth.json`, `data/models_auth.json`, `logs.xlsx`, `secrets/` (Google key), `.env`, the real values of `LECTURER_PASSWORD` / `SECRET_KEY`, uploaded videos.

## 3. Can someone use the repo?
Yes: `pip install -r requirements.txt && python app.py`. The repository contains no personal data, e-mails or API keys.
Things to know: the code has *development defaults* for `LECTURER_PASSWORD` and `SECRET_KEY` — whoever deploys must set their own;
`core/sheet_sync.py` has a default Google Sheet id (not a secret, but useless without the service-account key — set `GOOGLE_SHEET_ID` to your own).

## 4. Rebuilding the system from nothing
Needs: this repo (or ZIP), Python 3.10+, `pip install -r requirements.txt`, the environment variables in the README, the course PDFs (already in `data/`).
Everything else (accounts, logs, courses uploaded later) is created by the running site.

## 5. Giving / selling it to an organisation
Give: the repo ZIP, `docs/DEPLOY.md`, README, the notebooks, a licence of your choice (the repo has none yet → all rights reserved by default).
They run it with: their own server (Linux/Docker, `gunicorn app:app` behind HTTPS), their own passwords and e-mail provider, their own courses uploaded by their doctors from the Admin page.
They should: change the default passwords, back up `data/` and `logs.xlsx`, and for more than a few hundred users move the Excel log to a database.

## 6. Private repository
* The website keeps running (the code is already copied on PythonAnywhere).
* `git pull` on PythonAnywhere **stops working** until you give it credentials: create a GitHub *Personal Access Token* (read-only, "Contents") and run
  `git remote set-url origin https://<TOKEN>@github.com/pikachu8240/StudyMate.git`, or add a *deploy key* (SSH).
* The **"Open in Colab" links and the `git clone` inside the notebooks stop working** for other people (Colab needs a public repo or a token).
* The doctor/TA can no longer open the link — add him as a collaborator or send the ZIP.
* Don't make it private before the submission is graded, unless you send the ZIP.
