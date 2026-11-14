"""Readable names for the activity-log codes: code -> (icon, tone, English, Arabic).

tone groups the colour of the chip: add (green), remove (red), safety (amber), view (blue), edit (grey).
"""

LABELS = {
    "admin_added": ("shield", "add", "Admin added", "إضافة أدمن"),
    "admin_removed": ("shield", "remove", "Admin removed", "حذف أدمن"),
    "admin_password_reset": ("key", "safety", "Admin password reset", "تغيير كلمة سر أدمن"),
    "perms_changed": ("sliders", "edit", "Permissions changed", "تعديل الصلاحيات"),
    "student_made_admin": ("shield", "add", "Student made admin", "طالب بقى أدمن"),
    "student_deleted": ("trash", "remove", "Student deleted", "حذف طالب"),
    "doctor_added": ("teacher", "add", "Doctor added", "إضافة دكتور"),
    "doctor_approved": ("check", "add", "Doctor request approved", "قبول طلب دكتور"),
    "doctor_rejected": ("x", "remove", "Doctor request rejected", "رفض طلب دكتور"),
    "doctor_removed": ("teacher", "remove", "Doctor removed", "حذف دكتور"),
    "doctor_password_reset": ("key", "safety", "Doctor password reset", "تغيير كلمة سر دكتور"),
    "course_deleted": ("book", "remove", "Course deleted", "حذف مادة"),
    "course_owner_set": ("book", "edit", "Course doctor set", "تحديد دكتور المادة"),
    "lecture_uploaded": ("upload", "add", "Lecture uploaded", "رفع محاضرة"),
    "exam_bank_uploaded": ("exam", "add", "Exam questions uploaded", "رفع بنك أسئلة"),
    "announcement": ("mega", "add", "Announcement sent", "إرسال إعلان"),
    "announcement_deleted": ("mega", "remove", "Announcement deleted", "حذف إعلان"),
    "not_found_threshold": ("sliders", "edit", "Not-found threshold changed", "تعديل حد \"مش موجود\""),
    "vault_opened": ("unlock", "view", "Data vault opened", "فتح خزنة البيانات"),
    "vault_viewed": ("eye", "view", "Person viewed in the vault", "عرض شخص في الخزنة"),
    "vault_export_user": ("download", "view", "One person exported", "تصدير بيانات شخص"),
    "vault_export_all": ("download", "view", "Everyone exported", "تصدير كل المستخدمين"),
    "vault_wrong_password": ("alert", "safety", "Wrong vault password", "كلمة سر خزنة غلط"),
    "vault_password_changed": ("key", "safety", "Vault password changed", "تغيير كلمة سر الخزنة"),
    "vault_password_reset": ("key", "safety", "Password reset from the vault", "إعادة كلمة سر من الخزنة"),
    "wipe_code_set": ("key", "safety", "Security code set", "تعيين كود الأمان"),
    "wipe_scheduled": ("alert", "remove", "Deletion scheduled", "جدولة حذف"),
    "wipe_cancelled": ("refresh", "add", "Deletion cancelled", "إلغاء الحذف"),
    "wipe_wrong_code": ("alert", "safety", "Wrong security code", "كود أمان غلط"),
    "site_reopened": ("unlock", "add", "Site reopened", "إعادة فتح الموقع"),
}


def label(code, lang="en"):
    """(icon, tone, text) for an activity code; unknown codes are made readable."""
    ic, tone, en, ar = LABELS.get(code, ("list", "edit", (code or "").replace("_", " ").capitalize(), (code or "").replace("_", " ")))
    return ic, tone, (ar if lang == "ar" else en)
