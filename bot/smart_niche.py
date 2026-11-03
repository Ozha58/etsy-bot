"""Hybrid niche picker.

The AI invents very specific micro-niches (new idea), then we keep the old data-driven checks:
  - product types and weights come from settings.json (and ONLY_TYPE for /uret wallpaper)
  - during the Christmas season most ideas are Christmas (settings.json "christmas_share", default 0.7)
  - niches used in the last days are not repeated
  - every idea is scored with Etsy's public search (demand = favorites, competition = number of results)
  - very crowded niches (more results than settings.json "max_competition", default 8000) are used only as a last resort
  - one idea can be a close variation of our own best seller (when we have sales)
"""
import datetime as dt
import random
import re

from . import config, llm, research
from .products import TYPES

CATEGORIES = ["animals", "seasons and holidays", "hobbies", "fantasy", "fashion and style", "food and drink",
              "space", "plants and flowers", "travel", "home and kitchen"]

CHRISTMAS_RULE = (
    "CHRISTMAS: the main subject must be Santa Claus (Father Christmas), or reindeer, winter woodland animals, "
    "a snowy village or happy children in winter. Use a vintage, retro, cozy winter, soft watercolor or poster style. "
    "No gnomes, no tomte, no elves, no Grinch, no Coca-Cola Santa, no film or brand characters."
)


def _christmas_share(today):
    share = config.settings().get("christmas_share", 0.7)
    try:
        share = float(share)
    except Exception:
        share = 0.7
    in_season = today.month in (10, 11) or (today.month == 12 and today.day <= 20)
    return share if in_season else 0.0


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


def _slots(n_cand, today):
    """One slot per candidate: product type + theme instruction."""
    types = _weighted_types(n_cand)
    share = _christmas_share(today)
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
                     "but a clearly different theme, colorway or art style. Never copy it")
            slots.append({"type": t, "theme": theme, "variation_of": w["title"]})
        elif random.random() < share:
            slots.append({"type": t, "theme": CHRISTMAS_RULE})
        else:
            slots.append({"type": t, "theme": f"free micro-niche in the category '{random.choice(CATEGORIES)}' "
                                              f"(season hint: {research.season_hint(today)})"})
    return slots


def _ask(slots, used, today):
    plan = "\n".join(f'{i + 1}. product type "{s["type"]}" ({TYPES[s["type"]].LABEL_TR}). Theme: {s["theme"]}'
                     for i, s in enumerate(slots))
    prompt = f"""You are the best Etsy digital-products seller. Today is {today.isoformat()}. Buyers shop 3-8 weeks ahead.
Find {len(slots)} VERY SPECIFIC micro-niche ideas that sell on Etsy but have few competitors. Idea number N is for slot N:
{plan}

Rules:
- Be specific: style + theme, never generic like "Christmas" or "cats". State the art style in the niche text.
- Each idea must suit its product type (coloring = clear black line art scenes; wallpaper = vertical phone wallpaper scenes;
  wall_art = art prints for a room; scenes = full illustrated scenes; clipart = separate objects; pattern = seamless papers).
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
            idea = {"type": slot["type"], "niche": niche, "search_query": query, "why": str(item.get("why") or "")}
            if slot.get("variation_of"):
                idea["variation_of"] = slot["variation_of"]
            ideas.append(idea)
    except Exception as e:
        print(f"[smart_niche] AI niş bulma hatası: {e}")

    # score with Etsy search data: demand (favorites) vs competition (results)
    for rank, idea in enumerate(ideas):
        sc = research._score(idea)
        idea["score"] = (sc if sc is not None else 0) + (len(ideas) - rank) * 0.02 + random.random() * 0.1
    cap = int(s.get("max_competition", 8000) or 0)
    crowded = [i for i in ideas if cap and (i.get("etsy_results") or 0) > cap]
    for i in crowded:
        print(f"[smart_niche] Çok rekabetli, sona atıldı: {i['niche']} ({i['etsy_results']} ilan)")
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

    # nothing usable from the AI: Christmas fallback so the day is never empty
    backups = [
        "vintage retro Santa Claus with reindeer in a snowy forest",
        "cozy winter woodland animals fox deer owl in snow",
        "vintage Santa delivering gifts to happy children",
        "retro Christmas morning by the fireplace with Santa",
    ]
    types = _weighted_types(count + 4)
    j = 0
    while len(chosen) + len(reserve) < count + 2 and j < len(types):
        n = backups[j % len(backups)]
        chosen_or_reserve = {"type": types[j], "niche": n, "search_query": n.split(" with ")[0],
                             "why": "Yedek niş kullanıldı.", "etsy_results": None}
        (chosen if len(chosen) < count else reserve).append(chosen_or_reserve)
        j += 1
    return chosen + reserve
