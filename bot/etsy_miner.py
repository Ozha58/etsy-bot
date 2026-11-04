"""Find niches straight from Etsy data instead of only from AI ideas.

1. Search Etsy for a few on-theme seed phrases (e.g. "snowy owl clipart") and read the TAGS of the
   top listings: these are the phrases real sellers rank for and real buyers type.
2. Weight every tag by how much the listings using it are favorited (demand).
3. Search each promising tag phrase on its own: how many competitors, how many favorites, how fast
   the top listings collect favorites (trend), and the market price.
4. Return the best phrases as niche ideas (with product type), already scored.
Set "etsy_mining": false in settings.json to turn it off.
"""
import math
import random
import re
import statistics
import time

from . import config, etsy, research, theme

SEED_SUBJECTS = ["reindeer", "winter fox", "snowy owl", "woodland animals", "winter bunny", "snowy forest",
                 "christmas deer", "winter cardinal", "bear cub", "winter cottage", "winter birds", "forest animals",
                 "christmas village", "winter hedgehog", "moose"]
TYPE_SEED = {"scenes": "clipart", "wall_art": "print", "wallpaper": "phone wallpaper", "coloring": "coloring page"}
TYPE_WORDS = [  # phrase words -> our product type
    ("coloring", ("coloring", "colouring", "line art")),
    ("wallpaper", ("wallpaper", "lock screen", "lockscreen", "phone background", "iphone")),
    ("scenes", ("clipart", "clip art", "png", "junk journal", "illustration", "scrapbook", "card making", "sublimation")),
    ("wall_art", ("print", "wall art", "poster", "decor", "painting", "art")),
]
THEME_WORDS = set("""winter snow snowy christmas xmas holiday forest woodland woods deer reindeer fox foxes owl owls
bunny bunnies rabbit hare bear bears cardinal cardinals robin robins squirrel hedgehog moose elk wolf pine pinecone
cabin cottage village sleigh santa vintage storybook nature wildlife bird birds animal animals frosty frost cozy
spring easter autumn fall halloween valentine heart hearts nursery fairytale fairy tale""".split())
GENERIC = {"digital download", "instant download", "printable", "png", "clipart", "clip art", "digital print",
           "wall art", "printable art", "commercial use", "gift for her", "gift for him", "home decor"}


def _words(t):
    return re.findall(r"[a-z]+", t.lower())


def _type_of(phrase, allowed):
    low = phrase.lower()
    for t, words in TYPE_WORDS:
        if any(w in low for w in words):
            return t if t in allowed else None
    return ""  # no type word: any type fits


def _velocity(results):
    now = time.time()
    v = []
    for r in results:
        favs = int(r.get("num_favorers") or 0)
        born = r.get("original_creation_timestamp") or r.get("creation_timestamp") or now
        days = max(7.0, (now - float(born)) / 86400)
        v.append(favs / days)
    return statistics.median(v) if v else 0.0


def _measure(phrase):
    res = etsy.search_active(phrase)
    results = res.get("results", [])
    count = int(res.get("count", 0))
    favs = [int(r.get("num_favorers") or 0) for r in results]
    prices = [int(p["amount"]) / int(p["divisor"]) for p in (r.get("price") or {} for r in results)
              if p.get("currency_code") == "USD" and p.get("divisor")]
    med = statistics.median(favs) if favs else 0
    vel = _velocity(results)
    score = math.log1p(med) - 0.35 * math.log10(count + 10) + 1.5 * math.log1p(vel * 10)
    return {"etsy_results": count, "etsy_median_favs": med, "etsy_velocity": round(vel, 3),
            "etsy_median_price": round(statistics.median(prices), 2) if len(prices) >= 5 else None, "score": score}


def find(n=4, used=(), today=None, seeds=3, probe=10) -> list:
    if config.settings().get("etsy_mining") is False:
        return []
    allowed = [t for t in config.settings().get("product_types", {}) if t in TYPE_SEED] or list(TYPE_SEED)
    christmas = theme.angle(today).startswith("Christmas")
    used_l = {u.lower() for u in used}
    tag_weight, tag_hits = {}, {}
    for _ in range(seeds):
        subj = random.choice(SEED_SUBJECTS)
        if christmas and "christmas" not in subj and random.random() < 0.5:
            subj = "christmas " + subj
        seed = f"{subj} {TYPE_SEED[random.choice(allowed)]}"
        try:
            res = etsy.search_active(seed, limit=100)
        except Exception as e:
            print(f"[miner] Etsy araması başarısız ({seed}): {e}")
            continue
        for r in res.get("results", []):
            w = math.log1p(int(r.get("num_favorers") or 0))
            for tag in r.get("tags") or []:
                tag = str(tag).strip().lower()
                ws = _words(tag)
                if len(ws) < 2 or len(tag) > 20 or tag in GENERIC or tag == seed or research.is_banned(tag):
                    continue
                if not THEME_WORDS.intersection(ws):
                    continue
                tag_weight[tag] = tag_weight.get(tag, 0) + w
                tag_hits[tag] = tag_hits.get(tag, 0) + 1
    # tags used by several sellers are real search phrases; weight by demand
    cands = [t for t in tag_weight if tag_hits[t] >= 2 and t not in used_l and _type_of(t, allowed) is not None]
    cands.sort(key=lambda t: -tag_weight[t])
    ideas = []
    for phrase in cands[:probe]:
        try:
            m = _measure(phrase)
        except Exception as e:
            print(f"[miner] ölçülemedi ({phrase}): {e}")
            continue
        ptype = _type_of(phrase, allowed) or random.choice(allowed)
        ideas.append({
            "type": ptype, "niche": f"{phrase} in vintage storybook style", "search_query": phrase,
            "source": "etsy",
            "why": (f"Etsy'den bulundu: {tag_hits[phrase]} rakip ilanın etiketinde geçiyor; "
                    f"{m['etsy_results']:,} sonuç, ortanca {int(m['etsy_median_favs'])} favori"),
            **m,
        })
    ideas.sort(key=lambda i: -i["score"])
    print(f"[miner] {len(cands)} aday etiket, {len(ideas)} ölçüldü: "
          + ", ".join(f"{i['search_query']} ({i['score']:.2f})" for i in ideas[:6]))
    return ideas[:n]
