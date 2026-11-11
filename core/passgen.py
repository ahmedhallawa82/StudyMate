"""Strong password generator (used by the "Generate a password" button).

Model: a tiny character-level language model (a Markov chain over the last 2 letters = trigram model) trained on the
words of the course slides. It writes pronounceable, easy-to-remember letter groups ("trainel", "gorithe"...).
Then the rules are added with the operating-system secure random generator (`secrets`):
  length 8-15, at least one capital letter, one small letter, one digit and one special symbol.
The model only shapes the letters; every random choice (length, which letters become capitals, where digits and
symbols go, which ones) is made with `secrets`, so the password is not predictable from the model.
"""
import re
import secrets
from collections import defaultdict

import config

MIN_LEN, MAX_LEN = 8, 15
SYMBOLS = "!@#$%^&*-_+=?"
_FALLBACK = ("intelligent agent search problem state action environment learning network probability heuristic "
             "algorithm decision minimax pruning knowledge logic inference sampling bayesian vehicle engine brake "
             "transmission suspension steering wheel chassis battery safety").split()
_MODEL = None


def _words():
    words = []
    try:
        import pandas as pd
        for f in sorted((config.BASE_DIR / "data").glob("*/passages.csv")):
            text = " ".join(pd.read_csv(f)["text"].astype(str).head(3000))
            words += [w.lower() for w in re.findall(r"[A-Za-z]{4,10}", text)]
    except Exception:
        pass
    return words + _FALLBACK * 3


def _train():
    """counts[(a, b)][c] = how often letter c follows the letters a, b inside the course words."""
    counts = defaultdict(lambda: defaultdict(int))
    for w in _words():
        s = "^^" + w + "$"
        for i in range(len(s) - 2):
            counts[s[i:i + 2]][s[i + 2]] += 1
    return {k: dict(v) for k, v in counts.items()}


def _pick(weights):
    total = sum(weights.values())
    r = secrets.randbelow(total)
    for ch, w in weights.items():
        r -= w
        if r < 0:
            return ch
    return next(iter(weights))


def _letters(n):
    """n pronounceable lowercase letters from the model (a new word starts when the model ends one)."""
    global _MODEL
    if _MODEL is None:
        _MODEL = _train()
    out, ctx = "", "^^"
    while len(out) < n:
        nxt = _pick(_MODEL.get(ctx) or _MODEL["^^"])
        if nxt == "$":
            ctx = "^^"
            continue
        out += nxt
        ctx = ctx[1] + nxt
    return out[:n]


def check(pw):
    """True when the password follows the rules (8-15 characters, capital, small, digit, symbol)."""
    return (MIN_LEN <= len(pw) <= MAX_LEN and any(c.isupper() for c in pw) and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw) and any(c in SYMBOLS for c in pw))


def generate():
    while True:
        n = MIN_LEN + secrets.randbelow(MAX_LEN - MIN_LEN + 1)
        digits = 2 + secrets.randbelow(2)                      # 2-3 digits
        syms = 1 + secrets.randbelow(2)                        # 1-2 symbols
        letters = list(_letters(n - digits - syms))
        caps = {0} | {1 + secrets.randbelow(len(letters) - 1)}  # the first letter and one more become capitals
        for i in caps:
            letters[i] = letters[i].upper()
        chars = letters
        for ch in [str(secrets.randbelow(10)) for _ in range(digits)] + [secrets.choice(SYMBOLS) for _ in range(syms)]:
            chars.insert(secrets.randbelow(len(chars) + 1), ch)
        pw = "".join(chars)
        if check(pw):
            return pw
