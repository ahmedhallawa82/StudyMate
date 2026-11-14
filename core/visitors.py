"""Who visits the site: device, system, browser, country and network of every page view.

data/visitors.jsonl  one line per page view: {t, ip, ua, dev, os, br, who, page}
data/ipgeo.json      cache ip -> {cc, country, net}

The country and the network (TE Data, Vodafone, Orange ...) come from the free offline
GeoIP2Fast database (pip install geoip2fast). It is looked up in a separate process the
first time an address is shown, so the web process never holds the 70 MB table.
Without the package the page still works and shows "unknown" for the place.
"""
import json
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
LOG = DATA / "visitors.jsonl"
CACHE = DATA / "ipgeo.json"
KEEP = 30000                     # page views kept (older ones are dropped)
_lock = threading.Lock()

AR_COUNTRY = {"EG": "مصر", "SA": "السعودية", "AE": "الإمارات", "KW": "الكويت", "QA": "قطر", "BH": "البحرين", "OM": "عُمان", "JO": "الأردن",
              "LB": "لبنان", "SY": "سوريا", "IQ": "العراق", "PS": "فلسطين", "LY": "ليبيا", "SD": "السودان", "TN": "تونس", "DZ": "الجزائر",
              "MA": "المغرب", "YE": "اليمن", "US": "أمريكا", "GB": "بريطانيا", "DE": "ألمانيا", "FR": "فرنسا", "IT": "إيطاليا", "NL": "هولندا",
              "TR": "تركيا", "CA": "كندا", "IN": "الهند", "CN": "الصين", "RU": "روسيا", "IE": "أيرلندا", "SE": "السويد", "SG": "سنغافورة"}


# ---------------- device, system and browser from the browser's own description (User-Agent)
def parse_ua(ua):
    """(device, os, browser): device is phone | tablet | computer | bot."""
    u = ua or ""
    low = u.lower()
    if not u or re.search(r"bot|crawl|spider|slurp|curl|wget|python-requests|httpclient|headless|monitor|uptime|preview", low):
        dev = "bot"
    elif "ipad" in low or "tablet" in low or ("android" in low and "mobile" not in low) or ("macintosh" in low and "mobile" in low):
        dev = "tablet"
    elif re.search(r"iphone|ipod|android.*mobile|mobile|windows phone", low):
        dev = "phone"
    else:
        dev = "computer"
    m = re.search(r"Android (\d+)", u)
    if "Windows NT" in u:
        osn = "Windows"
    elif "iPad" in u:
        osn = "iPadOS"
    elif re.search(r"iPhone|iPod", u):
        v = re.search(r"OS (\d+)_", u)
        osn = "iOS" + (" " + v.group(1) if v else "")
    elif m:
        osn = "Android " + m.group(1)
    elif "CrOS" in u:
        osn = "ChromeOS"
    elif "Mac OS X" in u or "Macintosh" in u:
        osn = "macOS"
    elif "Linux" in u:
        osn = "Linux"
    else:
        osn = "Other"
    for pat, name in ((r"Edg[A-Z]?/", "Edge"), (r"OPR/|Opera", "Opera"), (r"SamsungBrowser/", "Samsung Internet"),
                      (r"FBAN|FBAV|Instagram", "Facebook / Instagram app"), (r"Firefox/|FxiOS/", "Firefox"),
                      (r"Chrome/|CriOS/", "Chrome"), (r"Safari/", "Safari")):
        if re.search(pat, u):
            return dev, osn, name
    return dev, osn, "Other"


def client_ip(req):
    """The visitor's address behind the PythonAnywhere front proxy."""
    ip = req.headers.get("X-Real-IP") or (req.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or req.remote_addr or ""
    return ip.strip()[:64]


def record(ip, ua, who, page):
    dev, osn, br = parse_ua(ua)
    row = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "ip": ip, "ua": (ua or "")[:300], "dev": dev, "os": osn, "br": br, "who": who or "", "page": page[:80]}
    with _lock:
        DATA.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        try:
            if LOG.stat().st_size > 12_000_000:                  # keep the newest page views only
                lines = LOG.read_text(encoding="utf-8").splitlines()[-KEEP:]
                LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass


def read(days=None):
    if not LOG.exists():
        return []
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - (days - 1) * 86400)) if days else ""
    out = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("t", "") >= since:
            out.append(r)
    return out


# ---------------- country and network of an address (offline database, separate process)
_PRIVATE = re.compile(r"^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|::1$|fc|fd|fe80)")
_SCRIPT = r"""
import json, sys, warnings
warnings.filterwarnings('ignore')
from geoip2fast import GeoIP2Fast
g = GeoIP2Fast(geoip2fast_data_file='geoip2fast-asn-ipv6.dat.gz', verbose=False)
out = {}
for ip in sys.argv[1:]:
    try:
        r = g.lookup(ip)
        out[ip] = {'cc': r.country_code, 'country': r.country_name, 'net': getattr(r, 'asn_name', '') or ''}
    except Exception:
        out[ip] = {'cc': '--', 'country': '', 'net': ''}
print(json.dumps(out))
"""


def _cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def geo(ips):
    """{ip: {cc, country, net}} for these addresses, from the cache or looked up once."""
    cache = _cache()
    todo = [ip for ip in set(ips) if ip and ip not in cache]
    for ip in list(todo):
        if _PRIVATE.match(ip):
            cache[ip] = {"cc": "LAN", "country": "Local network", "net": ""}
            todo.remove(ip)
    for i in range(0, len(todo), 400):
        part = todo[i:i + 400]
        try:
            res = subprocess.run([sys.executable, "-c", _SCRIPT, *part], capture_output=True, text=True, timeout=60)
            cache.update(json.loads(res.stdout or "{}"))
        except (OSError, ValueError, subprocess.SubprocessError):
            break                                          # no database here: the page shows "unknown"
    if todo:
        try:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return {ip: cache.get(ip, {"cc": "--", "country": "", "net": ""}) for ip in ips}


def country_name(g, lang):
    cc = g.get("cc") or "--"
    if cc == "--":
        return "غير معروف" if lang == "ar" else "Unknown"
    if cc == "LAN":
        return "شبكة محلية" if lang == "ar" else "Local network"
    return AR_COUNTRY.get(cc, g.get("country") or cc) if lang == "ar" else (g.get("country") or cc)


def summary(rows, lang="en"):
    """Everything the visitors page shows, for these page views."""
    people = [r for r in rows if r.get("dev") != "bot"]
    g = geo([r["ip"] for r in people])
    uniq = {}
    for r in people:                                       # one visitor = one address + one browser
        uniq.setdefault((r["ip"], r.get("ua", "")), r)
    vis = list(uniq.values())
    dev = Counter(r["dev"] for r in vis)
    cc = Counter(g[r["ip"]]["cc"] for r in vis)
    countries = [{"cc": c, "name": country_name({"cc": c, "country": next((g[r["ip"]]["country"] for r in vis if g[r["ip"]]["cc"] == c), "")}, lang), "n": n}
                 for c, n in cc.most_common(12)]
    nets = Counter(g[r["ip"]]["net"] or "–" for r in vis).most_common(8)
    hours = [0] * 24
    for r in people:
        try:
            hours[int(r["t"][11:13])] += 1
        except (ValueError, KeyError):
            pass
    known = sum(n for c, n in cc.items() if c not in ("--", "LAN"))
    recent = []
    for r in reversed(people[-300:]):
        x = g[r["ip"]]
        recent.append({**r, "cc": x["cc"], "country": country_name(x, lang), "net": x["net"]})
    return {"views": len(people), "visitors": len(vis), "signed": len({r["who"] for r in people if r.get("who")}),
            "bots": len(rows) - len(people),
            "dev": {k: dev.get(k, 0) for k in ("phone", "tablet", "computer")},
            "egypt": cc.get("EG", 0), "abroad": known - cc.get("EG", 0), "unknown": len(vis) - known,
            "countries": countries, "nets": nets, "os": Counter(r["os"] for r in vis).most_common(6),
            "br": Counter(r["br"] for r in vis).most_common(6), "hours": hours, "recent": recent}
