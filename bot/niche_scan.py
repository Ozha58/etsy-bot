"""Theme-free niche scan on real Etsy data (Telegram: /nis or /nis <keyword>).

Pass 1: search many "subject + product format" phrases our system can make (AI art, no text).
Pass 2: read the TAGS of the best listings found and measure those long-tail phrases too.
For every phrase we measure:
  - results  : number of competing listings (competition)
  - favs     : median favorites of the top 25 (demand)
  - speed    : median favorites per day of the top 25 (is it selling NOW?)
  - fresh    : share of the top 25 created in the last 120 days (can a NEW shop still reach the top?)
  - price    : median USD price of the top 25
Results are kept for 21 days in meta["niche_scan"], so every run adds to one growing database,
and the report ranks everything measured so far.
"""
import datetime as dt
import math
import random
import re
import statistics
import time

from . import config, etsy, research, storage, telegram
from .telegram import esc

SUBJECTS = [
    # animals
    "fox", "owl", "deer", "bunny", "bear", "frog", "bee", "butterfly", "hedgehog", "cat", "dog", "horse",
    "highland cow", "chicken", "duck", "whale", "octopus", "jellyfish", "axolotl", "dinosaur", "dragon", "unicorn",
    "raven", "moth", "safari animals", "woodland animals", "farm animals", "ocean animals", "birds",
    # nature, food, places
    "mushroom", "lemon", "strawberry", "cherry", "peony", "wildflower", "sunflower", "lavender", "botanical", "fern",
    "cactus", "lighthouse", "mountain landscape", "cottage", "teapot", "vintage books",
    # styles / moods
    "cottagecore", "witchy", "celestial", "fairy", "gothic", "boho", "vintage floral", "nursery",
]
SEASONAL = {
    "christmas": ["christmas", "gingerbread", "nutcracker", "snowman", "poinsettia", "winter cardinal", "reindeer", "winter village"],
    "valentine": ["valentine", "love birds", "heart flowers"],
    "spring": ["easter bunny", "spring flowers", "spring birds"],
    "autumn": ["autumn leaves", "pumpkin", "halloween cat"],
}
FORMATS = [  # (phrase word, our product type)
    ("clipart", "clipart"), ("wall art", "wall_art"), ("phone wallpaper", "wallpaper"),
    ("coloring pages", "coloring"), ("digital paper", "pattern"), ("junk journal", "scenes"),
]
TYPE_WORDS = [
    ("coloring", ("coloring", "colouring", "line art")),
    ("wallpaper", ("wallpaper", "lock screen", "lockscreen", "phone background")),
    ("pattern", ("digital paper", "seamless", "pattern", "scrapbook paper")),
    ("scenes", ("junk journal", "ephemera", "journal")),
    ("clipart", ("clipart", "clip art", "png", "sublimation", "transparent")),
    ("wall_art", ("print", "wall art", "poster", "decor", "painting")),
]
GENERIC = {"digital download", "instant download", "printable", "png", "clipart", "clip art", "digital print",
           "wall art", "printable art", "commercial use", "gift for her", "gift for him", "home decor", "digital",
           "download", "printable wall art", "wall decor", "art print", "instant download png", "png bundle",
           "clipart bundle", "sublimation png", "sublimation design", "digital art", "art prints", "png files"}
KEEP_DAYS = 21
MIN_RESULTS = 150


def _type_of(phrase):
    low = phrase.lower()
    for t, words in TYPE_WORDS:
        if any(w in low for w in words):
            return t
    return None


def _season():
    m = dt.date.today().month
    d = dt.date.today().day
    if m in (10, 11) or (m == 12 and d <= 15):
        return "christmas"
    if m in (12, 1, 2):
        return "valentine"
    if m in (3, 4):
        return "spring"
    if m in (8, 9):
        return "autumn"
    return None


def measure(phrase, results=None, count=None):
    if results is None:
        res = etsy.search_active(phrase, limit=25)
        results, count = res.get("results", []), int(res.get("count", 0))
    top = results[:25]
    now = time.time()
    favs, speed, fresh, prices = [], [], 0, []
    for r in top:
        f = int(r.get("num_favorers") or 0)
        born = float(r.get("original_creation_timestamp") or r.get("creation_timestamp") or now)
        days = max(7.0, (now - born) / 86400)
        favs.append(f)
        speed.append(f / days)
        if days <= 120:
            fresh += 1
        p = r.get("price") or {}
        if p.get("currency_code") == "USD" and p.get("divisor"):
            prices.append(int(p["amount"]) / int(p["divisor"]))
    med = statistics.median(favs) if favs else 0
    vel = statistics.median(speed) if speed else 0
    fr = fresh / len(top) if top else 0
    score = (math.log1p(med) + 1.5 * math.log1p(vel * 10) + 1.2 * fr - 0.35 * math.log10(count + 10))
    if count < MIN_RESULTS:
        score -= 3  # nobody searches it
    return {"phrase": phrase, "results": count, "favs": med, "speed": round(vel, 3), "fresh": round(fr, 2),
            "price": round(statistics.median(prices), 2) if len(prices) >= 5 else None, "score": round(score, 3),
            "type": _type_of(phrase), "at": int(now)}


def _seeds(keyword, n):
    if keyword:
        return [f"{keyword} {w}" for w, _ in FORMATS] + [keyword]
    season = _season()
    pool = [f"{s} {w}" for s in SUBJECTS for w, _ in FORMATS]
    random.shuffle(pool)
    seeds = pool[:n]
    if season:
        seeds += [f"{s} {w}" for s in random.sample(SEASONAL[season], min(3, len(SEASONAL[season])))
                  for w, _ in random.sample(FORMATS, 2)]
    return seeds


def run(keyword="", n_seeds=45, n_tags=25):
    keyword = (keyword or "").strip().lower()
    meta = storage.load_meta()
    db = {k: v for k, v in (meta.get("niche_scan") or {}).items() if time.time() - v.get("at", 0) < KEEP_DAYS * 86400}
    tag_w, tag_n, measured, calls = {}, {}, [], 0
    for seed in _seeds(keyword, n_seeds):
        if research.is_banned(seed):
            continue
        try:
            res = etsy.search_active(seed, limit=100)
            calls += 1
        except Exception as e:
            print(f"[scan] {seed}: {e}")
            continue
        results = res.get("results", [])
        m = measure(seed, results, int(res.get("count", 0)))
        db[seed] = m
        measured.append(m)
        for r in results:
            w = math.log1p(int(r.get("num_favorers") or 0))
            for tag in r.get("tags") or []:
                tag = str(tag).strip().lower()
                ws = re.findall(r"[a-z]+", tag)
                if len(ws) < 2 or len(tag) > 20 or tag in GENERIC or research.is_banned(tag):
                    continue
                tag_w[tag] = tag_w.get(tag, 0) + w
                tag_n[tag] = tag_n.get(tag, 0) + 1
        time.sleep(0.15)
    # pass 2: long-tail phrases real sellers use on the best listings
    cands = [t for t in tag_w if tag_n[t] >= 2 and t not in db]
    if keyword:
        cands = [t for t in cands if keyword in t] or cands
    cands.sort(key=lambda t: -tag_w[t])
    for tag in cands[:n_tags]:
        try:
            m = measure(tag)
            calls += 1
            db[tag] = m
            measured.append(m)
        except Exception as e:
            print(f"[scan] {tag}: {e}")
        time.sleep(0.15)
    meta["niche_scan"] = db
    storage.save_meta(meta)
    report(db if not keyword else {m["phrase"]: m for m in measured}, keyword, len(measured), calls, len(db))
    return db


def best(db=None, n=15, makeable=True):
    if db is None:
        db = storage.load_meta().get("niche_scan") or {}
    rows = [v for v in db.values() if v["results"] >= MIN_RESULTS]
    if makeable:
        rows = [v for v in rows if v.get("type")]
    return sorted(rows, key=lambda v: -v["score"])[:n]


def report(db, keyword, new_count, calls, total=None):
    top = best(db, 15, makeable=not keyword)
    head = (f"🔭 <b>Niş taraması</b>{' – ' + esc(keyword) if keyword else ''}\n"
            f"Bu turda {new_count} ifade ölçüldü ({calls} Etsy araması). Veritabanında {total or len(db)} ifade var.\n"
            "Sütunlar: ilan = rakip sayısı · fav = ilk 25'in ortanca favorisi · hız = günde favori · "
            "yeni = ilk 25'te son 4 ayda açılmış ilan oranı (yüksekse yeni mağaza da üste çıkabiliyor)\n")
    lines = []
    for i, v in enumerate(top, 1):
        price = f" · ${v['price']:.2f}" if v.get("price") else ""
        lines.append(f"{i}. <b>{esc(v['phrase'])}</b> [{v.get('type') or '?'}]\n"
                     f"    {v['results']:,} ilan · {int(v['favs'])} fav · {v['speed']:.2f}/gün · yeni %{int(v['fresh'] * 100)}{price}")
    if not lines:
        lines = ["Ölçülebilir ifade bulunamadı."]
    telegram.send(head + "\n" + "\n".join(lines) + "\n\nBelirli bir konuyu derin taramak için: <code>/nis kurbağa</code> gibi yazın (İngilizce kelime daha iyi: <code>/nis frog</code>).")
