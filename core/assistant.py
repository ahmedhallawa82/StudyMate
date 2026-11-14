"""Chat assistant, layer 1: an intent router. No AI service, no cost, no internet.

The person writes what they need ("I need exams", "عايز امتحانات", "3ayez emtehan"); the router finds the page that
does it and answers with a short sentence plus a button that opens the page. Anything it does not know is sent to the
real search over the lecture slides (/ask), so a content question still gets a real answer.

Layer 2 (a free LLM such as Groq / Gemini) would plug in at `fallback()`; nothing else has to change.

This module knows nothing about Flask: it returns endpoint names and the route turns them into links."""
import difflib
import re

_AR_MARKS = re.compile(r"[ً-ْٰـ]")                 # harakat + tatweel
_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
_PREFIX = ("وال", "بال", "كال", "فال", "لل", "ال")


def norm(text: str) -> str:
    t = _AR_MARKS.sub("", (text or "").lower()).translate(_AR_MAP)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _strip_prefix(w: str) -> str:
    for p in _PREFIX:
        if w.startswith(p) and len(w) - len(p) >= 3:
            return w[len(p):]
    return w


def is_arabic(text: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", text or ""))


# gate: None = everybody of that side; a permission key (content, exams, data, ...) or "main" (main admin only)
# kw: English, Arabic and "Franco" (Arabic written in Latin letters) words / phrases
INTENTS = [
    # ------------------------------------------------------------------ students
    dict(id="ask", who="student", endpoint="ask", icon="ask",
         label=("Ask the slides", "اسأل المحاضرات"),
         kw="ask question search slides lecture explain what is define meaning find in lectures ابحث اسال سؤال اسالك اشرح شرح معني يعني ايه محاضره سلايد es2al eshra7 ma3na",
         ans=("Type your question in Ask and I show the slides that answer it, with the page highlighted.",
              "اكتب سؤالك في «اسأل» وهيطلعلك السلايدات اللي فيها الإجابة، والجزء المطلوب متعلّم عليه.")),
    dict(id="practice", who="student", endpoint="practice", icon="pencil",
         label=("Practice", "تدريب"),
         kw="practice train training drill quiz mcq questions to solve test me تدريب تمرين اتدرب ادرب اختبرني كويز اسئله حل تمارين tadreeb tadrib etdarab",
         ans=("Practice gives you questions one by one with hints. Your level in each topic updates after every answer.",
              "التدريب بيديك أسئلة واحد ورا التاني مع تلميحات، ومستواك في كل موضوع بيتحدّث بعد كل إجابة.")),
    dict(id="exams", who="student", endpoint="exams", icon="exam",
         label=("Exams", "الامتحانات"),
         kw="exam exams midterm final mock timed test امتحان امتحانات امتحاني ميدترم فاينال اختبار ورقه emtehan imtehan emtehanat exam",
         ans=("Your exams are here: the ones your doctor opened for you, and your earlier results.",
              "امتحاناتك هنا: اللي الدكتور فتحها لك، ونتايجك القديمة.")),
    dict(id="progress", who="student", endpoint="progress", icon="chart",
         label=("My progress", "تقدّمي"),
         kw="progress level mastery weak strong weak topics how am i doing my score my level تقدمي تقدم مستواي مستوايا نقاط ضعف ضعيف قوي درجاتي نتيجتي mostawaya ta2adomi",
         ans=("Progress shows every topic as red, amber or green, so you see where you are weak.",
              "صفحة التقدّم بتعرض كل موضوع أحمر أو أصفر أو أخضر، فتشوف إنت ضعيف فين.")),
    dict(id="plan", who="student", endpoint="plan_page", icon="calendar",
         label=("Study plan", "خطة المذاكرة"),
         kw="plan study plan what should i study next study next revise revision schedule my week خطه خطة مذاكره اذاكر ايه هذاكر ايه اذاكر مراجعه جدول khota mozakra azaker eh",
         ans=("The plan is built from your weak topics, so you study what helps you most first.",
              "الخطة متبنية على المواضيع الضعيفة عندك، فتذاكر الأهم الأول.")),
    dict(id="badges", who="student", endpoint="badges_page", icon="badge",
         label=("Badges", "الشارات"),
         kw="badge badges achievements trophy rewards points streak شاره شارات انجاز انجازات اوسمه جوايز نقاط sharat engazat",
         ans=("Badges are earned from what you do on the site: asking, practising, passing exams.",
              "الشارات بتتكسب من اللي بتعمله في الموقع: أسئلة، تدريب، نجاح في الامتحانات.")),
    dict(id="saved", who="student", endpoint="saved_page", icon="star",
         label=("Saved questions", "المحفوظات"),
         kw="saved bookmarks bookmark starred favourites favorites my questions محفوظ محفوظات المحفوظه مفضله المفضله نجمه",
         ans=("Questions you starred are kept here, so you can come back to them before the exam.",
              "الأسئلة اللي حطيت عليها نجمة محفوظة هنا، ترجعلها قبل الامتحان.")),
    dict(id="calendar", who="student", endpoint="calendar_page", icon="cal",
         label=("Calendar", "التقويم"),
         kw="calendar deadline deadlines due date dates events when is the exam تقويم مواعيد ميعاد موعد تاريخ احداث امتى الامتحان taqweem mawa3id",
         ans=("The calendar shows your doctors' dates and the exam days.",
              "التقويم بيعرض مواعيد الدكاترة وأيام الامتحانات.")),
    dict(id="materials", who="student", endpoint="materials", icon="folder",
         label=("Course files", "ملفات المادة"),
         kw="materials material download pdf lecture files slides files notes handouts course files ملفات مواد المواد تحميل نزل حمل ملازم محاضرات pdf malazem tahmeel",
         ans=("All the course files are here, and you can download them one by one or as one zip.",
              "كل ملفات المادة هنا، وتقدر تحمّلها واحد واحد أو كلها في ملف zip.")),
    dict(id="studio", who="student", endpoint="studio", icon="studio",
         label=("Study Studio", "استوديو المذاكرة"),
         kw="studio flashcards flash cards summary summaries videos terms glossary استوديو فلاش كارد بطاقات ملخص ملخصات فيديو فيديوهات مصطلحات",
         ans=("The Studio has flashcards, summaries, key terms and the course videos.",
              "الاستوديو فيه بطاقات مراجعة وملخصات ومصطلحات وفيديوهات المادة.")),
    dict(id="chat", who="both", endpoint="chat_page", icon="chat", gate="chat",
         label=("Chat", "المحادثات"),
         kw="chat message messages talk to doctor talk to student contact doctor رساله رسايل شات محادثه محادثات كلم دكتور اكلم دكتور مراسله",
         ans=("Chat lets you write to your doctor or another student after they accept the request.",
              "المحادثات بتخليك تكلم دكتورك أو زميلك بعد ما يوافق على الطلب.")),
    dict(id="notifications", who="both", endpoint="notifications_page", icon="bell",
         label=("Notifications", "الإشعارات"),
         kw="notification notifications alerts news updates اشعار اشعارات تنبيه تنبيهات اخبار جديد",
         ans=("All your notifications are in one list.", "كل إشعاراتك في قايمة واحدة.")),
    dict(id="profile", who="both", endpoint="profile", icon="user",
         label=("My profile", "حسابي"),
         kw="profile account avatar picture photo change password my name email بروفايل حسابي حساب صوره صورتي كلمه السر كلمة السر باسورد اسمي ايميلي",
         ans=("In your profile you can change your picture, name and password.",
              "من حسابك تقدر تغيّر صورتك واسمك وكلمة السر.")),
    dict(id="my_courses", who="student", endpoint="my_courses", icon="folder",
         label=("My courses", "موادي"),
         kw="courses my courses change course switch course add course another course مواد موادي كورس كورسات غير الماده ماده تانيه ضيف ماده",
         ans=("Choose which courses you study here; the whole site follows the course you pick.",
              "اختار هنا المواد اللي بتذاكرها، والموقع كله بيمشي على المادة اللي تختارها.")),
    # ------------------------------------------------------------------ admin side
    dict(id="dashboard", who="staff", endpoint="dashboard", icon="dash", gate="data",
         label=("Dashboard", "لوحة المحاضر"),
         kw="dashboard statistics stats analytics performance students questions at risk charts لوحه داشبورد احصائيات احصاءات اداء الطلاب متعثرين رسومات",
         ans=("The Dashboard shows what students ask, where they are weak and who is at risk.",
              "اللوحة بتعرض الطلاب بيسألوا في إيه، وضعفانين فين، ومين متعثر.")),
    dict(id="report", who="staff", endpoint="report_page", icon="doc", gate="data",
         label=("Weekly report", "التقرير الأسبوعي"),
         kw="report weekly report summary pdf print تقرير تقرير اسبوعي ملخص طباعه",
         ans=("The weekly report sums up the week for each course.", "التقرير الأسبوعي بيلخّص الأسبوع لكل مادة.")),
    dict(id="content", who="staff", endpoint="admin", icon="upload", gate="content",
         label=("Course content", "محتوى المادة"),
         kw="upload add lecture add course new course pdf slides content videos questions bank رفع ارفع محاضره محاضرات اضافه ضيف ماده مادة جديده محتوي فيديو بنك اسئله",
         ans=("Course content is where you add a course, upload lectures and manage videos and questions.",
              "محتوى المادة هو المكان اللي تضيف منه مادة، وترفع المحاضرات، وتدير الفيديوهات والأسئلة.")),
    dict(id="exams_manage", who="staff", endpoint="exams_manage", icon="exam", gate="exams",
         label=("Manage exams", "إدارة الامتحانات"),
         kw="create exam manage exams exam results attempts grades امتحان امتحانات انشاء امتحان اعمل امتحان نتايج امتحان درجات محاولات",
         ans=("Here you create exams, open them for students and read the attempts.",
              "هنا بتعمل الامتحانات وتفتحها للطلاب وتقرا المحاولات.")),
    dict(id="students_list", who="staff", endpoint="students_page", icon="users", gate="students",
         label=("Students", "الطلاب"),
         kw="students student list registered delete student find student طلاب الطلاب طالب قايمه الطلاب مسجلين امسح طالب دور علي طالب",
         ans=("The students list shows who registered and lets you remove an account.",
              "قايمة الطلاب بتعرض مين سجّل، وتقدر تمسح حساب.")),
    dict(id="doctors", who="staff", endpoint="doctors_page", icon="users", gate="doctors",
         label=("Doctors", "الدكاترة"),
         kw="doctors doctor accounts add doctor approve doctor requests دكاتره الدكاتره دكتور حساب دكتور ضيف دكتور طلبات دكاتره",
         ans=("Doctors' accounts and sign-up requests are managed here.", "حسابات الدكاترة وطلبات التسجيل بتتدار من هنا.")),
    dict(id="admins", who="staff", endpoint="admins_page", icon="shield", gate="main",
         label=("Admins", "الأدمنز"),
         kw="admins admin sub admin permissions roles ادمن ادمنز صلاحيات صلاحيه",
         ans=("The main admin gives sub-admins their permissions here.", "الأدمن الرئيسي بيدّي الأدمنز الصلاحيات من هنا.")),
    dict(id="announce", who="staff", endpoint="announcements_page", icon="bell", gate="announce",
         label=("Announcements", "الإعلانات"),
         kw="announcement announcements announce notify all students broadcast اعلان اعلانات اعلن بلغ الطلاب",
         ans=("Write an announcement and every student of the course gets a notification.",
              "اكتب إعلان وكل طلاب المادة بيوصلهم إشعار.")),
    dict(id="badges_admin", who="staff", endpoint="badges_admin", icon="badge", gate="badges",
         label=("Badges (admin)", "إدارة الشارات"),
         kw="badges custom badge give badge award شارات شاره اديله شاره اعمل شاره",
         ans=("Create your own badges and give them to students here.", "اعمل شاراتك الخاصة وادّيها للطلاب من هنا.")),
    dict(id="support_inbox", who="staff", endpoint="support_inbox", icon="lifebuoy", gate="support",
         label=("Support inbox", "صندوق الدعم"),
         kw="support inbox messages problems complaints tickets دعم صندوق الدعم مشاكل شكاوي رسايل الدعم",
         ans=("Messages students and doctors sent to support are here.", "رسايل الطلاب والدكاترة للدعم موجودة هنا.")),
    dict(id="visitors", who="staff", endpoint="visitors_page", icon="monitor", gate="main",
         label=("Site visitors", "زوار الموقع"),
         kw="visitors visitor visited visit visits traffic devices countries where from ip زوار زيارات الزوار جهاز اجهزه بلد منين ايبي",
         ans=("Visitors shows devices, countries and the busiest hours.", "صفحة الزوار بتعرض الأجهزة والدول وأكتر الساعات زحمة.")),
    dict(id="audit", who="staff", endpoint="audit_page", icon="list", gate="main",
         label=("Activity log", "سجل النشاط"),
         kw="audit log activity log who did what history سجل النشاط سجل مين عمل ايه تاريخ العمليات",
         ans=("The activity log lists what each admin and doctor did.", "سجل النشاط بيعرض اللي عمله كل أدمن ودكتور.")),
    dict(id="vault", who="staff", endpoint="vault_page", icon="lock", gate="main",
         label=("Vault", "الخزنة"),
         kw="vault users accounts passwords export all users excel خزنه الخزنه مستخدمين حسابات كلمات السر تصدير",
         ans=("The Vault is the main admin's page for every account.", "الخزنة صفحة الأدمن الرئيسي لكل الحسابات.")),
    # ------------------------------------------------------------------ both
    dict(id="support", who="both", endpoint=None, click="#supportBtn", icon="lifebuoy",
         label=("Contact support", "كلّم الدعم"),
         kw="problem bug error not working broken contact support complain report issue help me مشكله مشكلة عطل خطا لا يعمل مش شغال بلغ دعم شكوي ابلغ mosh sha3'al moshkela",
         ans=("Sorry about that. Press the button and write what happened; the admin gets it directly.",
              "آسف على كده. دوس الزرار واكتب اللي حصل وهيوصل للأدمن مباشرة.")),
    dict(id="help", who="both", endpoint="help_page", icon="help",
         label=("Help", "المساعدة"),
         kw="help how to use guide tutorial how does it work what can i do how do i مساعده ازاي استخدم دليل شرح الموقع بيعمل ايه اعمل ايه ازاي mosa3da azay",
         ans=("The Help page explains every part of the site in a few lines.", "صفحة المساعدة بتشرح كل جزء في الموقع في سطور.")),
    dict(id="mode", who="both", endpoint=None, icon="sun",
         label=("", ""),
         kw="dark mode light mode night theme colours colors language arabic english الوضع الليلي دارك مظلم فاتح الوان ثيم لغه عربي انجليزي",
         ans=("The top bar has the light/dark button and the language menu (English / العربية).",
              "في الشريط اللي فوق زرار الوضع الفاتح/الداكن وقايمة اللغة (English / العربية).")),
]

SMALL = [
    dict(id="greet", kw="hi hello hey good morning good evening salam مرحبا اهلا هلا السلام عليكم صباح الخير مساء الخير ازيك ازيكم هاي",
         ans=("Hi! Tell me what you need, for example “exams”, “my progress” or “what should I study next”.",
              "أهلاً! قولي محتاج إيه، مثلاً «امتحانات» أو «مستواي» أو «أذاكر إيه».")),
    dict(id="thanks", kw="thanks thank you thx great perfect شكرا شكرًا تسلم تسلمي ممتاز جميل متشكر",
         ans=("You're welcome! Ask me anything else.", "العفو! اسألني في أي حاجة تانية.")),
    dict(id="who", kw="who are you what can you do your name what are you انت مين انت ايه بتعمل اسمك بتعمل ايه تقدر تعمل ايه",
         ans=("I'm the StudyMate assistant. I take you to the right page and send your course questions to the lecture search.",
              "أنا مساعد StudyMate. بوديك للصفحة المناسبة، وبوصّل أسئلة المادة لبحث المحاضرات.")),
]


def _prep(table):
    for it in table:
        words = norm(it["kw"]).split(" ")
        # multi-word phrases are written as runs in `kw`; matching is per word (with prefix + typo tolerance),
        # so a long keyword list works as a bag of words
        it["_w"] = [w for w in dict.fromkeys(words) if w]
        it["_stem"] = {_strip_prefix(w) for w in it["_w"]}


_prep(INTENTS)
_prep(SMALL)

_NOISE = set(norm("i me my want need would like to the a an of for in on at please can you could show take go open "
                  "3ayez 3ayz 3awez 3ayza عايز عايزه عاوز محتاج محتاجه ممكن لو سمحت فين اروح افتح وريني هات ورّيني في من علي الي يا انا انت").split(" "))


def _score(tokens, it):
    """How many of the person's words are words of this intent (typos and 'ال' prefixes tolerated)."""
    s = 0.0
    for tk in tokens:
        st = _strip_prefix(tk)
        if tk in it["_w"]:
            s += 2
        elif st in it["_stem"]:
            s += 2 if len(st) > 2 else 1
        elif len(st) >= 5:
            m = difflib.get_close_matches(st, it["_stem"], n=1, cutoff=0.78)
            if m:
                s += 1.5
    return s


def _gate_ok(it, side, allowed):
    if it["who"] != "both" and it["who"] != side:
        return False
    g = it.get("gate")
    return True if not g else bool(allowed(g))


def reply(text, side, allowed=lambda g: True, nxt=None, lang=None):
    """Answer one message.

    side:    "student" or "staff"
    allowed: function(gate) -> bool; says whether this person may open pages with that gate
    nxt:     name of the topic the student should study next (optional, makes the plan answer personal)
    lang:    site language; the answer follows the language the person typed in when that is Arabic or English
    Returns {"answer", "actions": [{"label", "endpoint", "args", "click"}], "intent", "matched"}."""
    text = (text or "").strip()[:300]
    lg = "ar" if is_arabic(text) else (lang if lang in ("en", "ar") and not re.search(r"[a-zA-Z]{3}", text) else "en")
    i = 1 if lg == "ar" else 0
    tokens = [t for t in norm(text).split(" ") if t and t not in _NOISE]
    if not tokens:
        return _small("greet", lg)

    ranked = sorted(((_score(tokens, it), it) for it in INTENTS if _gate_ok(it, side, allowed)),
                    key=lambda x: -x[0])
    small = max(((_score(tokens, it), it) for it in SMALL), key=lambda x: x[0])
    best, top = ranked[0] if ranked else (0, None)

    if small[0] >= max(2, 1.2 * len(tokens)) and small[0] >= best and len(tokens) <= 4:
        return _small(small[1]["id"], lg)

    # a question about the lecture content that happens to contain one weak page word ("what is a heuristic search") goes to the search
    looks_like_question = side == "student" and (len(tokens) >= 4 or "?" in text or "؟" in text)
    if top is None or best < 2 or (looks_like_question and best < 4):
        return fallback(text, side, lg)

    actions = [_action(top, i)]
    if top["id"] == "ask":                                          # carry the question to the search
        actions[0]["args"] = {"q": text}
    ans = top["ans"][i]
    nxt = nxt() if callable(nxt) and top["id"] == "plan" else (nxt if not callable(nxt) else None)
    if top["id"] == "plan" and nxt:
        ans += (" Next for you: " + nxt + ".") if lg == "en" else (" الجاي ليك: " + nxt + ".")
    for sc, it in ranked[1:3]:                                    # a close second page is offered too
        if sc >= 3 and sc >= best - 1:
            actions.append(_action(it, i))
    return {"answer": ans, "actions": [a for a in actions if a["label"]], "intent": top["id"], "matched": True}


def _action(it, i):
    return {"label": it["label"][i], "endpoint": it.get("endpoint"), "args": {}, "click": it.get("click")}


def _small(key, lg):
    it = next(x for x in SMALL if x["id"] == key)
    return {"answer": it["ans"][1 if lg == "ar" else 0], "actions": [], "intent": key, "matched": True}


def fallback(text, side, lg):
    """Nothing matched. Layer 2 (a free LLM) would answer here; layer 1 sends a student's question to the slide search."""
    if side == "student":
        return {"answer": ("I did not find a page for that, but the lecture search may have the answer."
                           if lg == "en" else "ملقيتش صفحة مناسبة، بس ممكن بحث المحاضرات يكون فيه الإجابة."),
                "actions": [{"label": ("Search the slides" if lg == "en" else "ابحث في المحاضرات"), "endpoint": "ask",
                             "args": {"q": text}, "click": None}],
                "intent": "ask_fallback", "matched": False}
    return {"answer": ("I did not understand that. Try a page name, like “dashboard”, “exams” or “students”."
                       if lg == "en" else "مفهمتش المقصود. جرّب اسم صفحة زي «لوحة المحاضر» أو «امتحانات» أو «الطلاب»."),
            "actions": [{"label": ("Help" if lg == "en" else "المساعدة"), "endpoint": "help_page", "args": {}, "click": None}],
            "intent": "none", "matched": False}


def chips(side, lg):
    """Starter suggestions shown when the panel opens."""
    if side == "student":
        return [("What should I study next?", "أذاكر إيه؟"), ("My exams", "امتحاناتي"), ("My progress", "مستواي"),
                ("Course files", "ملفات المادة")]
    return [("Dashboard", "لوحة المحاضر"), ("Create an exam", "اعمل امتحان"), ("Upload a lecture", "ارفع محاضرة"),
            ("Students", "الطلاب")]
