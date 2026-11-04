"""Hybrid niche picker.

The AI invents very specific micro-niches (new idea), then we keep the old data-driven checks:
  - product types and weights come from settings.json (and ONLY_TYPE for /uret wallpaper)
  - every idea stays inside the shop theme (theme.py): one subject per product, realistic detailed style,
    with a seasonal angle (Christmas share in season: settings.json "christmas_share", default 0.7)
  - niches used in the last days are not repeated
  - every idea is scored with Etsy's public search (demand = favorites, competition = number of results)
  - very crowded niches (more results than settings.json "max_competition", default 8000) are used only as a last resort
  - one idea can be a close variation of our own best seller (when we have sales)
"""
import datetime as dt
import random
import re

from . import config, llm, research, theme as shop
from .products import TYPES

def _weighted_types(n):
    cfg = config.settings().get("product_types", {})
    types = [t for t in cfg if t in TYPES] or list(TYPES)
    weights = [max(1, int(cfg.get(t, 1) or 1)) for t in types]
    return [random.choices(types, weights=weights)[0] for _ in range(n)]


def _words(text):
    return set(re.findall(r"[a-z]{3,}", (text or "").lower()))


def _too_similar(niche, others):
    a = _words(niche)
    if not a:
        return False
    for o in others:
        b = _words(o)
        if b and len(a & b) / len(a | b) >= 0.6:
            return True
    return False


def _used(today):
    try:
        from .generator import used_niches
        return used_niches(config.settings().get("niche_memory_days", 60))
    except Exception as e:
        print(f"[smart_niche] kullanılan nişler okunamadı: {e}")
        return []


def _used_queries(days=None):
    """Search phrases of products made recently (so the same scan phrase is not picked twice)."""
    import time
    from . import storage
    days = days or config.settings().get("niche_memory_days", 60)
    cutoff = time.time() - days * 86400
    return {str(p.get("research", {}).get("search_query") or "").lower() for p in storage.all_products()
            if p.get("created_at", 0) >= cutoff and p.get("status") != "rejected"} - {""}


def _slots(n_cand, today):
    """One slot per candidate: product type + theme instruction."""
    types = _weighted_types(n_cand)
    best = []
    try:
        best = research.winners()
    except Exception:
        pass
    slots = []
    for i, t in enumerate(types):
        if best and i < min(2, len(best)):
            w = best[i]
            theme = (f'close variation of our own best seller "{w["title"]}": same buyer and product type, '
                     f"but a clearly different subject or scene, still inside our shop theme ({shop.theme()}). Never copy it")
            slots.append({"type": t, "theme": theme, "variation_of": w["title"]})
        else:
            slots.append({"type": t, "theme": shop.slot_theme(today)})
    return slots


def _ask(slots, used, today):
    plan = "\n".join(f'{i + 1}. product type "{s["type"]}" ({TYPES[s["type"]].LABEL_TR}). Theme: {s["theme"]}'
                     for i, s in enumerate(slots))
    prompt = f"""You are the best Etsy digital-products seller. Today is {today.isoformat()}. Buyers shop 3-8 weeks ahead.
Find {len(slots)} VERY SPECIFIC micro-niche ideas that sell on Etsy but have few competitors. Idea number N is for slot N:
{plan}

Rules:
- Every idea MUST stay inside our shop theme: {shop.theme()}. Our art style is always: {shop.style()}.
- Be specific: subject + scene + season, never generic like "Christmas" or "animals". Ideas must differ clearly from each other.
- Each idea must suit its product type (coloring = clear black line art scenes; wallpaper = vertical phone wallpaper scenes;
  wall_art = art prints for a room; scenes = full illustrated scenes; clipart = separate objects; pattern = seamless papers;
  junk_journal = a printable vintage junk journal kit about ONE charming subject, e.g. honey bees, lighthouses, mushrooms).
- No trademarks, brands, celebrities, characters, franchises or copyrighted styles.
- The artwork is AI generated and CANNOT contain readable text: no quotes, words, names, monograms or lettering.
- Avoid these niches we already used recently: {', '.join(used[-40:]) or 'none'}.

Return ONLY a JSON array with exactly {len(slots)} objects in slot order:
[{{"niche": "specific niche in English", "search_query": "2-4 words a buyer types into Etsy search", "why": "short reason in Turkish"}}]"""
    data = llm.ask_json(prompt, temperature=1.0)
    if isinstance(data, dict):
        data = data.get("ideas") or [data]
    return data or []


def find_trending_niches(count=1):
    today = dt.date.today()
    s = config.settings()
    used = _used(today)
    n_cand = max(8, count * 4)
    slots = _slots(n_cand, today)
    ideas = []
    try:
        for slot, item in zip(slots, _ask(slots, used, today)):
            if not isinstance(item, dict) or not item.get("niche"):
                continue
            niche = str(item["niche"]).strip()
            query = str(item.get("search_query") or niche).strip()
            if research.is_banned(niche + " " + query):
                continue
            if niche.lower() in [u.lower() for u in used] or _too_similar(niche, used):
                continue
            idea = {"type": slot["type"], "niche": niche, "search_query": query, "why": str(item.get("why") or ""),
                    "source": "ai"}
            if slot.get("variation_of"):
                idea["variation_of"] = slot["variation_of"]
            ideas.append(idea)
    except Exception as e:
        print(f"[smart_niche] AI niş bulma hatası: {e}")

    # score with Etsy search data: demand (favorites) vs competition (results)
    for rank, idea in enumerate(ideas):
        sc = research._score(idea)
        idea["score"] = (sc if sc is not None else 0) + (len(ideas) - rank) * 0.02 + random.random() * 0.1
    # ideas found directly in Etsy search data (real seller tags), already scored the same way
    try:
        from . import etsy_miner
        seen = {i["search_query"].lower() for i in ideas}
        for m in etsy_miner.find(max(3, count * 2), used, today):
            if m["search_query"] not in seen and not _too_similar(m["niche"], used):
                ideas.append(m)
    except Exception as e:
        print(f"[smart_niche] Etsy madenciliği atlandı: {e}")
    # best phrases from the /nis niche scan database (real Etsy data, last 21 days)
    try:
        from . import niche_scan
        allowed = set(s.get("product_types", {})) or set(TYPES)
        seen = {i["search_query"].lower() for i in ideas} | _used_queries()
        for v in niche_scan.best(n=12):
            ph = v["phrase"]
            if v.get("type") not in allowed or ph in seen or ph in [u.lower() for u in used] or _too_similar(ph, used):
                continue
            ideas.append({"type": v["type"], "niche": f"{ph}, realistic detailed style", "search_query": ph, "source": "scan",
                          "why": (f"Niş taramasından: {v['results']:,} ilan, ortanca {int(v['favs'])} favori, "
                                  f"ilk 25'te %{int(v['fresh'] * 100)} yeni ilan"),
                          "etsy_results": v["results"], "etsy_median_favs": v["favs"], "etsy_median_price": v.get("price"),
                          "etsy_velocity": v.get("speed"), "score": v["score"]})
    except Exception as e:
        print(f"[smart_niche] niş taraması verisi kullanılamadı: {e}")
    cap = int(s.get("max_competition", 8000) or 0)
    floor = int(s.get("min_results", 150) or 0)
    crowded = [i for i in ideas if (cap and (i.get("etsy_results") or 0) > cap)
               or (floor and i.get("etsy_results") is not None and i["etsy_results"] < floor)]
    for i in crowded:
        print(f"[smart_niche] Çok kalabalık ya da aranmıyor, sona atıldı: {i['niche']} ({i['etsy_results']} ilan)")
    # not-crowded ideas first (best score first), crowded ones only if we run out
    ideas.sort(key=lambda i: (i in crowded, -i["score"]))

    chosen, per_type, variations = [], {}, 0
    for idea in ideas:
        t = idea["type"]
        if per_type.get(t, 0) >= s.get("max_same_type_per_day", 1):
            continue
        if idea.get("variation_of"):
            if variations >= 1:
                continue
            variations += 1
        chosen.append(idea)
        per_type[t] = per_type.get(t, 0) + 1
        if len(chosen) >= count:
            break
    reserve = [i for i in ideas if i not in chosen and not i.get("variation_of")]

    # nothing usable from the AI: on-theme fallback so the day is never empty
    backups = [
        "realistic honey bees and beehives",
        "realistic lighthouse by the sea",
        "realistic forest mushrooms",
        "realistic garden birds",
    ]
    types = _weighted_types(count + 4)
    j = 0
    while len(chosen) + len(reserve) < count + 2 and j < len(types):
        n = backups[j % len(backups)]
        chosen_or_reserve = {"type": types[j], "niche": n, "search_query": " ".join(n.split()[2:5]),
                             "why": "Yedek niş kullanıldı.", "etsy_results": None}
        (chosen if len(chosen) < count else reserve).append(chosen_or_reserve)
        j += 1
    return chosen + reserve
