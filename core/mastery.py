"""Simple mastery update after every practice answer.

mastery_new = mastery_old + RATE * (outcome - mastery_old)
outcome: 1.0 correct without hints, 0.7 with one hint, 0.4 with two hints, 0.0 wrong.
Every topic starts at 0 (red). Colours: red < 0.40 <= amber < 0.70 <= green.
"""
import config

RATE = 0.35
OUTCOME = {0: 1.0, 1: 0.7, 2: 0.4}


def outcome(correct: bool, hints_used: int) -> float:
    if not correct:
        return 0.0
    return OUTCOME.get(min(int(hints_used), 2), 0.4)


def update(old: float, correct: bool, hints_used: int) -> float:
    return round(old + RATE * (outcome(correct, hints_used) - old), 4)


def colour(level: float) -> str:
    if level >= config.GREEN_FROM:
        return "green"
    if level >= config.RED_BELOW:
        return "amber"
    return "red"


def replay(answers, qid_to_topic: dict) -> dict:
    """Rebuild a student's mastery from their rows in the Answers sheet (oldest first)."""
    m = {}
    for a in answers:
        t = qid_to_topic.get(a["question_id"])
        if t is None:
            continue
        correct = str(a["correct"]).strip().lower() in ("1", "true", "yes")
        m[t] = update(m.get(t, 0.0), correct, int(a.get("hints_used") or 0))
    return m
