"""Text helpers: cleaning slide text, fixing glued words, normalising questions."""
import re

try:  # optional: splits words that the PDF glued together ("Bayesnetwork" -> "Bayes network")
    import wordninja
    _WORDS = set(wordninja.DEFAULT_LANGUAGE_MODEL._wordcost.keys())
except Exception:  # pragma: no cover - works without it, just less clean
    wordninja = None
    _WORDS = set()

# course words that the splitter must never break
PROTECTED = {
    "minimax", "optimality", "unexpanded", "percept", "percepts", "marginalization",
    "norvig", "haugeland", "charniak", "kurzweil", "yusria", "soliman", "zagazig",
    "zerind", "timisoara", "bucharest", "arad", "sibiu", "kalman", "mdps", "pomdps",
    "queueingfn", "robotized", "consistence", "astrat", "captcha", "schalkol", "fringe",
}

_FOOTER_PATTERNS = [
    r",?\s*LECTURE\s*\d+\s*\d*", r"\bLEC\s*\d+\b", r"CSC\s*412\s*(LECTURE|LEC)?\s*\d*",
    r"Prof\.?\s*Dr\s*:.*?Ayman Soliman",
]


def _split_token(tok: str) -> str:
    low = tok.lower()
    if wordninja is None or len(tok) < 6 or low in _WORDS or low in PROTECTED:
        return tok
    for p in sorted(PROTECTED, key=len, reverse=True):      # e.g. "MinimaxAlgorithm"
        if low.startswith(p) and len(low) > len(p):
            return tok[:len(p)] + " " + _split_token(tok[len(p):])
    return " ".join(wordninja.split(tok))


def fix_glued_words(text: str) -> str:
    text = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", text)   # camelCase -> camel Case
    return re.sub(r"[A-Za-z]{6,}", lambda m: _split_token(m.group(0)), text)


# Symbol-font characters used by PowerPoint (private-use area) -> readable words
_SYMBOL_FONT = {
    "": " alpha ", "": " beta ", "": " gamma ", "": " delta ",
    "": " epsilon ", "": " >= ", "": " <= ", "": " -> ", "": " x ",
    "": " not ", "": " and ", "": " or ", "": " infinity ",
}


def clean_slide_text(text: str) -> str:
    text = text or ""
    for k, v in _SYMBOL_FONT.items():
        text = text.replace(k, v)
    text = re.sub(r"[-\x00-\x08\x0b-\x1f]", " ", text)   # other bullets / control chars
    text = re.sub(r"alpha\s*-\s*beta\s*Pruning", "Alpha-Beta Pruning", text)
    for pat in _FOOTER_PATTERNS:
        text = re.sub(pat, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[▪▫●•◦➢❑■□]", " ", text)  # bullets
    text = re.sub(r"\s+", " ", text).strip()
    text = fix_glued_words(text)
    text = re.sub(r"\s+\d{1,2}(\s+\d{1,2})?\s*$", "", text)   # trailing slide numbers
    return re.sub(r"\s+", " ", text).strip()


def is_useful(text: str, min_words: int = 6) -> bool:
    """Drop empty, title-only, 'THANKS' and picture-only slides."""
    words = re.findall(r"[A-Za-z]{2,}", text)
    if len(words) < min_words:
        return False
    if re.fullmatch(r"(ARTIFICIAL INTELLIGENCE.*|THANKS.*)", text, flags=re.IGNORECASE):
        return False
    return True


ARABIC_RE = re.compile(r"[؀-ۿ]")


def normalize_question(q: str) -> str:
    q = (q or "").lower()
    q = q.replace("a*", "astar ").replace("a star", "astar ")
    q = q.replace("α", "alpha ").replace("β", "beta ")
    q = re.sub(r"alpha\s*-\s*beta", "alpha beta", q)
    q = re.sub(r"[^a-z0-9؀-ۿ\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


_BULLET_LEAD = re.compile(r"^\s*([▪▫●•◦➢❑■□]|[-–*](?=\s))\s*")


def clean_line(line: str) -> str:
    """One slide line for DISPLAY: symbol fonts fixed, glued words split, bullets kept as '• ' (no trailing-number rule)."""
    s = line or ""
    bullet = bool(_BULLET_LEAD.match(s))
    s = _BULLET_LEAD.sub("", s)
    for k, v in _SYMBOL_FONT.items():
        s = s.replace(k, v)
    s = re.sub(r"[-\x00-\x08\x0b-\x1f]", " ", s)
    s = re.sub(r"alpha\s*-\s*beta\s*Pruning", "Alpha-Beta Pruning", s)
    s = re.sub(r"[▪▫●•◦➢❑■□]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", fix_glued_words(s)).strip()
    return ("• " + s) if bullet else s
