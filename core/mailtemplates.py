"""E-mail template: "login details" (design 3 of the StudyMate e-mail templates).
password_email(...) -> (subject, plain text, html). Table layout + inline styles so it looks the same in Gmail / Outlook."""
from html import escape

T = {
    "ar": {"subject": "StudyMate - بيانات الدخول الجديدة", "dir": "rtl", "align": "right",
           "h": "بيانات الدخول إلى حسابك", "hello": "مرحباً {name}،",
           "intro": "تم إنشاء كلمة مرور جديدة لحسابك بناءً على طلبك. تقدر تدخل بالبيانات التالية:",
           "login": "البريد الإلكتروني / اسم المستخدم", "pw": "كلمة المرور المؤقتة", "role": "الدور",
           "warn": "لأمان حسابك، غيّر كلمة المرور المؤقتة بعد أول تسجيل دخول من صفحة <b>الملف الشخصي</b>. كلمة المرور القديمة لم تعد تعمل.",
           "btn": "تسجيل الدخول", "ignore": "لو ماطلبتش ده، تواصل مع الدعم من الموقع فوراً.",
           "foot": "StudyMate · مساعد المذاكرة الذكي<br>رسالة تلقائية، من فضلك لا ترد عليها.",
           "roles": {"student": "طالب", "doctor": "دكتور"}},
    "en": {"subject": "StudyMate - your new sign-in details", "dir": "ltr", "align": "left",
           "h": "Your account sign-in details", "hello": "Hello {name},",
           "intro": "A new password was created for your account at your request. You can sign in with:",
           "login": "E-mail / username", "pw": "Temporary password", "role": "Role",
           "warn": "For your account's safety, change this temporary password after you sign in, on the <b>Profile</b> page. Your old password no longer works.",
           "btn": "Sign in", "ignore": "If you did not ask for this, contact support from the site right away.",
           "foot": "StudyMate · your smart study assistant<br>Automatic message, please do not reply.",
           "roles": {"student": "Student", "doctor": "Doctor"}},
}


def password_email(name, login, password, role, login_url, lang="en"):
    t = T["ar" if lang == "ar" else "en"]
    role_t = t["roles"].get(role, role)
    e = escape
    rows = "".join(
        f'<tr><td style="padding:12px 16px;font-size:14px;color:#475569;border-bottom:1px solid #e2e8f0;width:38%;text-align:{t["align"]}">{k}</td>'
        f'<td dir="ltr" style="padding:12px 16px;font-size:16px;font-weight:700;color:#0f172a;border-bottom:1px solid #e2e8f0;text-align:left;font-family:Consolas,monospace">{e(v)}</td></tr>'
        for k, v in ((t["login"], login), (t["pw"], password), (t["role"], role_t)))
    html = f'''<!doctype html><html lang="{lang}" dir="{t["dir"]}"><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f4f1ea;font-family:Cairo,Tahoma,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ea"><tr><td align="center" style="padding:32px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
<tr><td style="background:#ffffff;border-radius:16px;padding:0">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:28px 40px 0;font-size:20px;font-weight:700;color:#0f172a;text-align:{t["align"]}">&#128214; StudyMate</td></tr>
 <tr><td style="padding:24px 40px 40px;text-align:{t["align"]}">
  <h1 style="margin:0 0 16px;font-size:26px;color:#0f172a">{t["h"]}</h1>
  <p style="margin:0 0 16px;font-size:16px;line-height:1.8;color:#334155">{t["hello"].format(name=e(name))}<br>{t["intro"]}</p>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;background:#f8fafc;border-collapse:collapse"><tbody>{rows}</tbody></table>
  <div style="background:#fef3c7;border-radius:10px;padding:14px 16px;margin:16px 0;font-size:14px;line-height:1.8;color:#78350f">{t["warn"]}</div>
  <p style="text-align:center;margin:18px 0"><a href="{e(login_url)}" style="display:inline-block;background:#0f766e;color:#ffffff;text-decoration:none;font-weight:700;font-size:16px;padding:14px 36px;border-radius:10px">{t["btn"]}</a></p>
  <p style="margin:0;font-size:13px;line-height:1.7;color:#475569">{t["ignore"]}</p>
 </td></tr></table>
</td></tr>
<tr><td style="padding:16px;text-align:center;font-size:13px;color:#475569;line-height:1.7">{t["foot"]}</td></tr>
</table></td></tr></table></body></html>'''
    plain = (f"{t['hello'].format(name=name)}\n{t['intro']}\n\n{t['login']}: {login}\n{t['pw']}: {password}\n{t['role']}: {role_t}\n\n"
             f"{login_url}\n")
    return t["subject"], plain, html
