# Deploying StudyMate

## A) PythonAnywhere (what the live demo uses)
1. Bash console: `git clone https://github.com/pikachu8240/StudyMate.git && cd StudyMate`
2. `mkvirtualenv --python=/usr/bin/python3.10 venv && pip install -r requirements.txt`
3. Web tab → *Add a new web app* → Manual configuration → Python 3.10. Source code / working dir `/home/<user>/StudyMate`, virtualenv `/home/<user>/.virtualenvs/venv`.
4. WSGI file:
```python
import sys, os
sys.path.insert(0, "/home/<user>/StudyMate")
os.environ["LECTURER_PASSWORD"] = "<a long password>"
os.environ["SECRET_KEY"] = "<random 32+ characters>"
os.environ["STUDYMATE_MODELS_PASSWORD"] = "<another password>"
from app import app as application
```
5. Reload. Free accounts: press **Run until 1 month from today** on the Web tab every month.
6. **Update later:** `cd ~/StudyMate && git pull`, then Reload. (Because the repo stopped tracking `logs.xlsx`, the first pull needs:
`cp logs.xlsx ~/logs_backup.xlsx; git checkout -- logs.xlsx; git pull; cp ~/logs_backup.xlsx logs.xlsx`.)

## B) Any Linux server / VPS
```bash
git clone https://github.com/pikachu8240/StudyMate.git && cd StudyMate
python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt
export LECTURER_PASSWORD=...  SECRET_KEY=...
gunicorn -w 2 -b 0.0.0.0:8000 app:app        # put nginx + HTTPS (Let's Encrypt) in front
```
Keep `data/`, `models/` and `logs.xlsx` on a persistent disk and back them up (they hold accounts, logs, uploaded videos).

## C) Render
`render.yaml` is included (see `deploy/DEPLOY_RENDER.md`). Free instances sleep and lose the disk on restart — attach a disk.

## D) Docker (any cloud)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
ENV PORT=8000 HOST=0.0.0.0
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "app:app"]
```

## Optional neural search
`pip install -r requirements-optional.txt` — the first search downloads a ~130 MB model from huggingface.co, so the host needs outbound access to it.
