"""Topic list, prerequisites and the 'Study next' rule."""
import pandas as pd
import config
from core.i18n import tr


def load_topics(course=None) -> pd.DataFrame:
    t = pd.read_csv(config.course_paths(course).topics).fillna("")
    if "name_ar" not in t:
        t["name_ar"] = ""
    t["name_ar"] = [a or n for a, n in zip(t["name_ar"], t["name"])]
    t["prereq_list"] = t["prerequisites"].map(lambda s: [p for p in str(s).split(";") if p])
    return t


def topic_names(course=None) -> dict:
    t = load_topics(course)
    return dict(zip(t.topic, t.name))


def study_next(mastery: dict, topics: pd.DataFrame = None, lang: str = "en"):
    """Pick the next topic to study and explain why.

    Rule: among topics that are not green yet, prefer one whose prerequisites are green
    (it is 'ready'); if a weak topic is a prerequisite of others, say so. Course order breaks ties.
    """
    topics = load_topics() if topics is None else topics   # pass the course's topics table
    names = dict(zip(topics.topic, topics.name_ar if lang == "ar" else topics.name))
    order = list(topics.topic)
    needed_by = {t: [] for t in order}
    for _, r in topics.iterrows():
        for p in r.prereq_list:
            needed_by.setdefault(p, []).append(r.topic)

    def level(t):
        return mastery.get(t, 0.0)

    weak = [t for t in order if level(t) < config.GREEN_FROM]
    if not weak:
        return None, tr("sn_all_green", lang)

    # 1) a weak prerequisite of something you already started blocks progress -> fix it first
    for t in weak:
        started_later = [n for n in needed_by.get(t, []) if mastery.get(n) is not None and n in mastery]
        if started_later and level(t) < config.RED_BELOW:
            later = names[started_later[0]]
            return t, tr("sn_blocking", lang, t=names[t], later=later)

    # 2) first weak topic whose prerequisites are all green-ish (ready to learn)
    for t in weak:
        prereqs = topics.loc[topics.topic == t, "prereq_list"].iloc[0]
        if all(level(p) >= config.RED_BELOW for p in prereqs):
            after = needed_by.get(t, [])
            if after:
                return t, tr("sn_needed", lang, t=names[t], after=names[after[0]])
            why = topics.loc[topics.topic == t, "why"].iloc[0]
            return t, tr("sn_ready", lang, t=names[t], why=why)

    t = weak[0]
    return t, tr("sn_earliest", lang, t=names[t])
