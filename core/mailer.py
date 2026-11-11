"""Optional e-mail sending (SMTP). Set these environment variables on the server to turn it on:
SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM (defaults to SMTP_USER).
For Gmail use an App Password. Without them nothing is sent and the site tells the admin to pass the password by hand."""
import os
import smtplib
import threading
from email.message import EmailMessage


def enabled():
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def _send(to, subject, body):
    try:
        msg = EmailMessage()
        msg["From"] = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]
        msg["To"], msg["Subject"] = to, subject
        msg.set_content(body)
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587)), timeout=20) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    except Exception as e:                      # never break the site because of e-mail
        print("mail failed:", type(e).__name__, e)


def send(to, subject, body):
    """Send in the background. Returns False when SMTP is not configured."""
    if not enabled() or not to:
        return False
    threading.Thread(target=_send, args=(to, subject, body), daemon=True).start()
    return True
