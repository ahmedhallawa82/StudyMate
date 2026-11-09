"""Topic list, prerequisites and the 'Study next' rule."""
import pandas as pd
import config


def load_topics() -> pd.DataFrame:
    t = pd.read_csv(config.TOPICS_CSV).fillna("")
    t["prereq_list"] = t["prerequisites"].map(lambda s: [p for p in str(s).split(";") if p])
    return t


def topic_names() -> dict:
    return dict(zip(load_topics().topic, load_topics().name))


def study_next(mastery: dict, topics: pd.DataFrame = None):
    """Pick the next topic to study and explain why.

    Rule: among topics that are not green yet, prefer one whose prerequisites are green
    (it is 'ready'); if a weak topic is a prerequisite of others, say so. Course order breaks ties.
    """
    topics = load_topics() if topics is None else topics
    names = dict(zip(topics.topic, topics.name))
    order = list(topics.topic)
    needed_by = {t: [] for t in order}
    for _, r in topics.iterrows():
        for p in r.prereq_list:
            needed_by.setdefault(p, []).append(r.topic)

    def level(t):
        return mastery.get(t, 0.0)

    weak = [t for t in order if level(t) < config.GREEN_FROM]
    if not weak:
        return None, "All topics are green. Revise with mixed practice before the exam."

    # 1) a weak prerequisite of something you already started blocks progress -> fix it first
    for t in weak:
        started_later = [n for n in needed_by.get(t, []) if mastery.get(n) is not None and n in mastery]
        if started_later and level(t) < config.RED_BELOW:
            later = names[started_later[0]]
            return t, f"{names[t]} is red and it is needed before {later}."

    # 2) first weak topic whose prerequisites are all green-ish (ready to learn)
    for t in weak:
        prereqs = topics.loc[topics.topic == t, "prereq_list"].iloc[0]
        if all(level(p) >= config.RED_BELOW for p in prereqs):
            after = needed_by.get(t, [])
            if after:
                return t, f"{names[t]} is not mastered yet and it is needed before {names[after[0]]}."
            why = topics.loc[topics.topic == t, "why"].iloc[0]
            return t, f"{names[t]} is not mastered yet ({why})."

    t = weak[0]
    return t, f"{names[t]} is the earliest topic in the course that is not mastered yet."
