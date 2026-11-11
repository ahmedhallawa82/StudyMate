"""Delete a whole account: the person and everything that belongs to him, so nothing is left behind."""
import json

import config
from core import students, doctors, profiles, notify, chat, badges, custom_badges
from core import exams as EX
from core.logger import delete_student_rows


def delete_student(code):
    key = "s:" + code
    EX.purge_student(code)
    delete_student_rows(code)
    profiles.delete(key)
    notify.purge(key)
    chat.purge(key)
    badges.purge(code)
    custom_badges.purge_student(code)
    return students.delete(code)


def delete_doctor(did):
    """The doctor goes; his courses stay and go back to the main admin."""
    key = "d:" + did
    doctors.remove(did)
    for c in config.list_courses():
        if c["meta"].get("owner") == did:
            meta = dict(c["meta"])
            meta.pop("owner", None)
            (config.BASE_DIR / "data" / c["code"] / "course.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    custom_badges.purge_owner(did)
    profiles.delete(key)
    notify.purge(key)
    chat.purge(key)
    return True
