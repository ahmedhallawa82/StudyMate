"""E-mail sending. Three ways, the first one configured wins (set the variables on the server):
1) Brevo HTTPS API (works on the free PythonAnywhere plan):  BREVO_API_KEY, MAIL_FROM (a sender verified in Brevo)
2) Resend HTTPS API:                                           RESEND_API_KEY, MAIL_FROM
3) SMTP (paid hosting / your own computer):                    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM
Without any of them nothing is sent and the site tells the person to ask the admin for a new password.
Messages carry a plain-text part and an optional HTML part (see core/mailtemplates.py)."""
import json
import os
import smtplib
import threading
import urllib.request
from email.message import EmailMessage


def provider():
    if os.environ.get("BREVO_API_KEY") and os.environ.get("MAIL_FROM"):
        return "brevo"
    if os.environ.get("RESEND_API_KEY") and os.environ.get("MAIL_FROM"):
        return "resend"
    if os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        return "smtp"
    return ""


def enabled():
    return bool(provider())


def _post(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "StudyMate", **headers})
    urllib.request.urlopen(req, timeout=20).read()


def _send(to, subject, text, html):
    """Send now. True when the provider accepted the message."""
    try:
        p = provider()
        sender = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER")
        if p == "brevo":
            _post("https://api.brevo.com/v3/smtp/email", {"api-key": os.environ["BREVO_API_KEY"]},
                  {"sender": {"name": "StudyMate", "email": sender}, "to": [{"email": to}], "subject": subject,
                   "textContent": text, **({"htmlContent": html} if html else {})})
            return True
        elif p == "resend":
            _post("https://api.resend.com/emails", {"Authorization": "Bearer " + os.environ["RESEND_API_KEY"]},
                  {"from": f"StudyMate <{sender}>", "to": [to], "subject": subject, "text": text, **({"html": html} if html else {})})
            return True
        else:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = sender, to, subject
            msg.set_content(text)
            if html:
                msg.add_alternative(html, subtype="html")
            with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587)), timeout=20) as s:
                s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                s.send_message(msg)
        return True
    except Exception as e:                      # never break the site because of e-mail
        print("mail failed:", type(e).__name__, e)
        return False


def send(to, subject, text, html=None):
    """Send in the background. Returns False when no provider is configured."""
    if not enabled() or not to:
        return False
    threading.Thread(target=_send, args=(to, subject, text, html), daemon=True).start()
    return True


def send_now(to, subject, text, html=None):
    """Send and wait (max 20 s). True only if the provider accepted the message (used before a password is changed)."""
    if not enabled() or not to:
        return False
    return bool(_send(to, subject, text, html))
