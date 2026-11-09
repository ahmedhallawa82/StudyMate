"""English / Arabic interface texts.  Course content (slides, practice questions) stays in the course language.

Use in templates:  {{ t('key') }}   {{ t('key', n=3) }}       in Python:  tr('key', lang)
"""
LANGS = ("en", "ar")

T = {
    # ---- layout
    "app_name": ("StudyMate", "ستادي ميت"),
    "nav_ask": ("Ask", "اسأل"),
    "nav_practice": ("Practice", "تدرّب"),
    "nav_progress": ("My progress", "تقدّمي"),
    "nav_eval": ("Evaluation", "التقييم"),
    "nav_dashboard": ("Dashboard", "لوحة المحاضر"),
    "nav_admin": ("Admin", "الإدارة"),
    "logout": ("log out", "خروج"),
    "lecturer_chip": ("lecturer", "محاضر"),
    "exit": ("exit", "خروج"),
    "footer": ("StudyMate answers only from the {course} lecture slides and always shows the lecture and slide number.",
               "ستادي ميت بيجاوب من شرايح محاضرات {course} فقط، وبيوريك رقم المحاضرة والشريحة دايمًا."),
    "mode_light": ("Light", "فاتح"), "mode_dark": ("Dark", "داكن"), "mode_auto": ("Auto", "تلقائي"),
    "toggle_mode": ("Change light / dark mode", "تغيير الوضع فاتح / داكن"),
    "toggle_lang": ("Switch language", "تغيير اللغة"),
    "lang_name": ("العربية", "English"),
    "course_label": ("Course", "المادة"),
    "lecture": ("Lecture", "المحاضرة"), "slide": ("Slide", "الشريحة"),
    "yes": ("Yes", "نعم"), "no": ("No", "لا"),
    # ---- start
    "welcome": ("Welcome to StudyMate", "أهلًا بيك في ستادي ميت"),
    "intro": ("A study assistant for the {course} course. It answers only from the lecture slides, gives practice "
              "questions with hints, and tracks your level per topic.",
              "مساعد مذاكرة لمادة {course}. بيجاوب من شرايح المحاضرات بس، وبيديك أسئلة تدريب مع تلميحات، "
              "وبيتابع مستواك في كل موضوع."),
    "choose_course": ("Choose your course", "اختار المادة"),
    "student_code": ("Your student code", "كود الطالب"),
    "code_ph": ("e.g. S001", "S001"),
    "privacy": ("Privacy: we store only this code, never your name. Your questions and practice answers are saved "
                "with the code so your progress can be shown.",
                "الخصوصية: بنسجّل الكود ده بس، ومش بنسجّل اسمك. أسئلتك وإجاباتك بتتحفظ مع الكود علشان نعرض تقدّمك."),
    "start_btn": ("Start studying", "ابدأ المذاكرة"),
    "enter_code": ("Please enter your student code (for example S001).", "اكتب كود الطالب (مثلًا S001)."),
    "course_full": ("Full course", "مادة كاملة"), "course_auto": ("Search and practice", "بحث وتدريب"),
    "change_course": ("Change course", "تغيير المادة"),
    # ---- ask
    "ask_ph": ("Ask a question about the course, e.g. What is an admissible heuristic?",
               "اسأل سؤال عن المادة، مثلًا: ايه هو البحث بالعرض؟"),
    "search_method": ("Search method", "طريقة البحث"),
    "ask_btn": ("Ask", "اسأل"),
    "ask_hint": ("You can ask in English or Arabic (e.g. «ايه هو البحث بالعرض»). The slides are in English.",
                 "تقدر تسأل بالعربي أو بالإنجليزي. الشرايح نفسها بالإنجليزي."),
    "detected": ("Detected topic", "الموضوع المتوقّع"),
    "confidence": ("confidence", "ثقة"),
    "passages_found": ("passages found", "فقرات ظهرت"),
    "similarity": ("similarity", "التشابه"),
    "was_helpful": ("Was this helpful?", "الإجابة دي مفيدة؟"),
    "right_decision": ("Was this the right decision?", "هل القرار ده صح؟"),
    "practise_topic": ("Practise {topic}", "تدرّب على {topic}"),
    "not_found": ("Not found in the course.", "مش موجود في المادة."),
    "not_found_body": ("This question is not covered by the {course} lecture slides, so StudyMate will not invent an answer. "
                       "Try other words, or ask your lecturer.",
                       "السؤال ده مش موجود في شرايح {course}، علشان كده ستادي ميت مش هيألّف إجابة. "
                       "جرّب كلمات تانية أو اسأل المحاضر."),
    "try_example": ("Try for example", "جرّب مثلًا"),
    "thanks": ("Thanks for the feedback!", "شكرًا على رأيك!"),
    # ---- practice
    "saved_you": ("Saved: you answered", "اتسجّلت: إجابتك كانت"),
    "correctly": ("correctly", "صح"), "incorrectly": ("incorrectly", "غلط"),
    "mastery": ("Mastery", "الإتقان"),
    "question_n": ("question {i} of {n}", "سؤال {i} من {n}"),
    "set_finished": ("set finished, keep going if you like", "خلصت المجموعة، كمّل لو حابب"),
    "hint": ("Hint", "تلميح"), "hint2": ("Clearer hint", "تلميح أوضح"),
    "answer_ph": ("Write your answer first, then check it (optional but recommended)",
                  "اكتب إجابتك الأول وبعدين اتحقق منها (اختياري بس مفضّل)"),
    "check_btn": ("Check my answer", "اتحقق من إجابتي"),
    "show_hint": ("Show hint", "اعرض تلميح"), "show_hint2": ("Show a clearer hint", "اعرض تلميح أوضح"),
    "show_answer": ("Show the answer", "اعرض الإجابة"),
    "your_answer": ("Your answer", "إجابتك"),
    "answer_lbl": ("Answer", "الإجابة"),
    "key_ideas": ("Your answer contains {a} of {b} key ideas", "إجابتك فيها {a} من {b} أفكار أساسية"),
    "looks_right": ("Looks right.", "تبدو صح."), "compare": ("Compare carefully.", "قارن بالإجابة بعناية."),
    "be_honest": ("Be honest: did you get it right? (hints used: {h})", "كن أمين: جاوبت صح؟ (تلميحات مستخدمة: {h})"),
    "got_right": ("I got it right", "جاوبت صح"), "got_wrong": ("I got it wrong", "جاوبت غلط"),
    "choose_topic": ("Choose a topic", "اختار موضوع"),
    "current": ("current", "الحالي"),
    "mastery_rule": ("Mastery rises most when you answer without hints: no hint = full credit, 1 hint = 70%, 2 hints = 40%, wrong = 0.",
                     "الإتقان بيزيد أكتر لما تجاوب من غير تلميحات: من غير تلميح = كامل، تلميح واحد = 70%، تلميحين = 40%، غلط = 0."),
    "all_topics": ("All topics", "كل المواضيع"),
    "fill_blank": ("Fill in the blank", "كمّل الفراغ"),
    # ---- progress / topics panel
    "practice_answers": ("practice answers", "إجابات التدريب"), "correct": ("correct", "صح"),
    "topics_green": ("topics green", "مواضيع خضرا"), "accuracy": ("accuracy", "الدقة"),
    "topics": ("Topics", "المواضيع"),
    "legend": ("red below 40% · amber 40–69% · green 70% and above", "أحمر أقل من 40% · أصفر 40–69% · أخضر 70% وأكتر"),
    "study_next": ("Study next", "ذاكر بعد كده"),
    "practise5": ("Practise 5 questions", "تدرّب على 5 أسئلة"),
    "how_level": ("How the level is computed: after each answer, level = level + 0.35 × (result − level). Result is 1 for a correct "
                  "answer without hints, 0.7 with one hint, 0.4 with two hints and 0 for a wrong answer.",
                  "طريقة حساب المستوى: بعد كل إجابة، المستوى = المستوى + 0.35 × (النتيجة − المستوى). النتيجة 1 للإجابة الصح "
                  "من غير تلميح، و0.7 بتلميح، و0.4 بتلميحين، و0 للإجابة الغلط."),
    "my_topics": ("My topics", "مواضيعي"),
    "pct_mastery": ("% mastery", "% إتقان"), "new": ("new", "جديد"),
    # ---- study_next reasons
    "sn_all_green": ("All topics are green. Revise with mixed practice before the exam.",
                     "كل المواضيع خضرا. راجع بتدريب متنوّع قبل الامتحان."),
    "sn_blocking": ("{t} is red and it is needed before {later}.", "{t} لسه أحمر وهو مطلوب قبل {later}."),
    "sn_needed": ("{t} is not mastered yet and it is needed before {after}.", "{t} لسه ما اتقنتوش وهو مطلوب قبل {after}."),
    "sn_ready": ("{t} is not mastered yet ({why}).", "{t} لسه ما اتقنتوش."),
    "sn_earliest": ("{t} is the earliest topic in the course that is not mastered yet.", "{t} أول موضوع في المادة لسه ما اتقنتوش."),
    # ---- lecturer
    "lecturer_area": ("Lecturer area", "منطقة المحاضر"),
    "lecturer_note": ("The dashboard and the admin page are for the course lecturer.", "لوحة المحاضر وصفحة الإدارة للمحاضر بس."),
    "password": ("Password", "كلمة المرور"), "enter": ("Enter", "دخول"),
    "wrong_password": ("Wrong password.", "كلمة المرور غلط."),
    # ---- dashboard
    "dash_title": ("Lecturer dashboard", "لوحة المحاضر"),
    "dash_sub": ("Read live from logs.xlsx (sheets Questions, Answers, Visits, Feedback).",
                 "بتتقرا مباشرة من logs.xlsx (الأوراق Questions وAnswers وVisits وFeedback)."),
    "download_logs": ("Download logs.xlsx", "تحميل logs.xlsx"),
    "students_codes": ("students (codes)", "طلاب (أكواد)"),
    "questions_asked": ("questions asked", "أسئلة اتسألت"), "not_found_n": ("not found", "غير موجودة"),
    "answers_marked_helpful": ("answers marked helpful", "إجابات مفيدة"),
    "no_activity": ("No student activity yet. Ask questions and practise as a student first; the charts fill in automatically.",
                    "لسه مفيش نشاط للطلاب. اسأل وتدرّب كطالب الأول، والرسوم هتتملي لوحدها."),
    "most_asked": ("Most asked topics", "أكتر المواضيع سؤالًا"),
    "lowest_scores": ("Topics with the lowest scores (practice, % correct)", "المواضيع الأقل درجات (تدريب، % صح)"),
    "weakest": ("Weakest", "الأضعف"), "top": ("Top", "الأعلى"),
    "students_per_colour": ("Students per mastery colour", "الطلاب حسب لون الإتقان"),
    "visits_day": ("Visits per day", "الزيارات في اليوم"),
    "latest_nf": ('Latest questions answered "Not found" (possible gaps in the slides)',
                  'آخر الأسئلة اللي إجابتها "غير موجود" (ممكن تكون ثغرات في الشرايح)'),
    "time": ("Time", "الوقت"), "student": ("Student", "الطالب"), "question": ("Question", "السؤال"),
    "none_yet": ("None yet.", "لسه مفيش."),
    "red": ("red", "أحمر"), "amber": ("amber", "أصفر"), "green": ("green", "أخضر"),
    # ---- admin
    "adm_upload": ("Upload a new lecture PDF", "ارفع محاضرة PDF جديدة"),
    "adm_upload_note": ("The slides are split into passages (one per slide) with pypdf and added to the search index. Slides of a new "
                        "lecture get their topic from the topic classifier. Uploading a lecture number that already exists replaces it.",
                        "الشرايح بتتقسم لفقرات (فقرة لكل شريحة) وبتتضاف لفهرس البحث. شرايح المحاضرة الجديدة موضوعها بيتحدد "
                        "بالمصنّف. رفع رقم محاضرة موجود بيستبدلها."),
    "lecture_number": ("Lecture number", "رقم المحاضرة"), "title": ("Title", "العنوان"),
    "upload_rebuild": ("Upload and rebuild index", "ارفع وأعد بناء الفهرس"),
    "lectures_in_index": ("Lectures in the index", "المحاضرات في الفهرس"), "passages": ("passages", "فقرات"),
    "topics_col": ("Topics", "المواضيع"),
    "maintenance": ("Maintenance", "الصيانة"),
    "rebuild_index": ("Rebuild search index", "أعد بناء فهرس البحث"),
    "rebuild_note": ("Re-reads every PDF of the selected course.", "بيعيد قراءة كل PDF في المادة الحالية."),
    "retrain": ("Retrain classifier + re-evaluate", "أعد تدريب المصنّف والتقييم"),
    "retrain_note": ("Use after editing the labelled questions or the question bank (takes a few seconds).",
                     "استخدمه بعد تعديل الأسئلة المصنّفة أو بنك الأسئلة (بياخد ثواني)."),
    "topic_model": ("Topic model", "نموذج المواضيع"), "question_bank": ("Question bank", "بنك الأسئلة"),
    "questions": ("questions", "سؤال"), "nf_threshold": ('"Not found" threshold', 'حد "غير موجود"'),
    "add_course": ("Add a new course", "أضف مادة جديدة"),
    "add_course_note": ("Upload the lecture PDFs of another course (file names like “lecture 1 Intro.pdf”). StudyMate builds the slide "
                        "index, one topic per lecture, a classifier and fill-in-the-blank practice questions automatically. "
                        "A course with its own question bank and labelled questions can be added later for a full evaluation.",
                        "ارفع محاضرات PDF لمادة تانية (أسماء الملفات زي «lecture 1 Intro.pdf»). ستادي ميت بيبني لوحده فهرس الشرايح "
                        "وموضوع لكل محاضرة ومصنّف وأسئلة تدريب بالفراغات. وتقدر تضيف بنك أسئلة خاص بالمادة بعدين لتقييم كامل."),
    "course_code": ("Course code", "كود المادة"), "course_name_en": ("Course name (English)", "اسم المادة (إنجليزي)"),
    "course_name_ar": ("Course name (Arabic)", "اسم المادة (عربي)"), "pdf_files": ("Lecture PDFs (several allowed)", "ملفات المحاضرات (أكتر من ملف)"),
    "create_course": ("Create course", "إنشاء المادة"),
    "courses": ("Courses", "المواد"),
    "no_eval_course": ("This course was built automatically from its lecture slides, so there is no labelled test set to evaluate yet.",
                       "المادة دي اتبنت أوتوماتيك من شرايح المحاضرات، فمفيش مجموعة اختبار مصنّفة لتقييمها لسه."),
    # ---- flashes
    "choose_pdf": ("Please choose a PDF file.", "اختار ملف PDF."),
    "give_number": ("Please give the lecture number.", "اكتب رقم المحاضرة."),
    "saved_file": ("Saved {name}.", "اتحفظ {name}."),
    "index_rebuilt": ("Index rebuilt: {n} passages from {m} lectures.", "اتبنى الفهرس: {n} فقرة من {m} محاضرات."),
    "retrained": ("Classifier retrained and evaluation updated.", "اتعاد تدريب المصنّف واتحدّث التقييم."),
    "course_created": ("Course {name} created: {n} slides from {m} lectures, {q} practice questions.",
                       "اتعملت المادة {name}: {n} شريحة من {m} محاضرات و{q} سؤال تدريب."),
    "course_bad": ("Course code must be 2–10 letters/digits and at least one PDF is needed.",
                   "كود المادة 2–10 حروف/أرقام ولازم ترفع PDF واحد على الأقل."),
    "course_exists": ("This course code already exists.", "كود المادة ده موجود قبل كده."),
    "course_failed": ("Could not read any slide text from the PDFs (scanned images?).", "ماقدرتش أقرا نص من الـ PDF (ممكن صور ممسوحة؟)."),
    # ---- evaluation
    "ev_none": ("No evaluation yet. Run python scripts/evaluate.py.", "مفيش تقييم لسه. شغّل python scripts/evaluate.py."),
    "ev_topic_acc": ("topic accuracy ({model}, {n} test questions)", "دقة تصنيف الموضوع ({model}، {n} سؤال اختبار)"),
    "ev_top1": ("search top-1 hit rate (TF-IDF)", "نسبة إصابة البحث في أول نتيجة (TF-IDF)"),
    "ev_top3": ("search top-3 hit rate (TF-IDF)", "نسبة إصابة البحث في أول 3 نتائج (TF-IDF)"),
    "ev_off": ('off-topic questions → "Not found"', 'أسئلة خارج المادة → "غير موجود"'),
    "ev_h1": ("1. Topic classifier (question → topic)", "1. مصنّف الموضوع (سؤال ← موضوع)"),
    "ev_h1p": ("{n} student-style questions in {k} topics, stratified 80/20 split. The test set ({t} questions) is never used for "
               "training. Training also uses the question bank and slide texts.",
               "{n} سؤال بأسلوب الطلاب في {k} موضوع، تقسيم 80/20 متوازن. مجموعة الاختبار ({t} سؤال) عمرها ما اتستخدمت "
               "في التدريب. التدريب بيستخدم كمان بنك الأسئلة ونصوص الشرايح."),
    "ev_model": ("Model", "النموذج"), "ev_acc": ("Accuracy", "الدقة"), "ev_mp": ("Macro precision", "Precision المتوسط"),
    "ev_mr": ("Macro recall", "Recall المتوسط"), "ev_mf": ("Macro F1", "F1 المتوسط"), "ev_used": ("used by the app", "المستخدم في التطبيق"),
    "ev_perclass": ("Per-class results ({m})", "نتائج كل فئة ({m})"), "ev_topic": ("Topic", "الموضوع"),
    "ev_cm": ("Confusion matrix", "مصفوفة الالتباس"), "ev_cm_nb": ("Naive Bayes confusion matrix", "مصفوفة التباس Naive Bayes"),
    "ev_err": ("Error analysis – wrong predictions of {m}", "تحليل الأخطاء – توقعات غلط لـ {m}"),
    "ev_true": ("True topic", "الموضوع الصحيح"), "ev_pred": ("Predicted", "المتوقّع"),
    "ev_h2": ("2. Search (question → slide)", "2. البحث (سؤال ← شريحة)"),
    "ev_h2p": ("{n} test questions written in different words from the slides, each with its correct slide. A hit means the correct "
               "slide is the first result (top-1) or among the three results (top-3).",
               "{n} سؤال اختبار بكلمات مختلفة عن الشرايح، ولكل سؤال شريحته الصحيحة. الإصابة يعني إن الشريحة الصحيحة هي أول نتيجة "
               "(top-1) أو من ضمن 3 نتائج (top-3)."),
    "ev_method": ("Method", "الطريقة"), "ev_show_all": ("Show all {n} search test questions", "اعرض كل أسئلة اختبار البحث ({n})"),
    "ev_correct_slide": ("Correct slide", "الشريحة الصحيحة"), "ev_top3_ret": ("Top 3 returned", "أول 3 نتائج"),
    "ev_h3": ('3. "Not found in the course" – off-topic test', '3. "غير موجود في المادة" – اختبار الأسئلة الخارجية'),
    "ev_h3p": ("A question is answered only if its best cosine similarity ≥ {t} and at least {c}% of its content words exist in the "
               "slides. Both values were tuned automatically so that every off-topic question is rejected. Cost: {a}/{b} "
               "search-test questions and {s}% of the student questions still get an answer.",
               "السؤال بيتجاوب بس لو أعلى تشابه cosine ≥ {t} و{c}% على الأقل من كلماته موجودة في الشرايح. القيمتين اتظبطوا "
               "أوتوماتيك علشان كل سؤال خارجي يتعمله رفض. التكلفة: {a}/{b} من أسئلة اختبار البحث و{s}% من أسئلة الطلاب لسه بتتجاوب."),
    "ev_offq": ("Off-topic question", "سؤال خارج المادة"), "ev_best": ("Best score", "أعلى درجة"), "ev_result": ("Result", "النتيجة"),
    "ev_h4": ("4. Robustness tests", "4. اختبارات المتانة"),
    "ev_h4p": ("The same test questions changed on purpose: spelling mistakes, upper case, only two key words, extra chatty words, and "
               "Arabic questions (bonus).",
               "نفس أسئلة الاختبار بعد تغييرها عمدًا: أخطاء إملائية، حروف كبيرة، كلمتين أساسيتين بس، كلام زيادة، وأسئلة عربي (بونص)."),
    "ev_test": ("Test", "الاختبار"), "ev_example": ("Example", "مثال"),
    "ev_clf_acc": ("Classifier accuracy", "دقة المصنّف"), "ev_search3": ('Search top-3 (with "Not found" rule)', 'البحث top-3 (مع قاعدة "غير موجود")'),
    "ev_arabic": ("Arabic examples", "أمثلة بالعربي"), "ev_expected": ("Expected topic", "الموضوع المتوقّع"),
}


def tr(key: str, lang: str = "en", **kw) -> str:
    en, ar = T.get(key, (key, key))
    s = ar if lang == "ar" else en
    return s.format(**kw) if kw else s
