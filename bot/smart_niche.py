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


FORMAT_WORDS = set("""junk journal journals journaling kit kits ephemera printable printables digital download clipart clip
art png wall prints print poster phone wallpaper wallpapers lock screen lockscreen coloring colouring pages page book
paper papers pattern patterns seamless scrapbook collage sheet sheets stickers sticker cards card tags bundle pack set
realistic detailed style vintage illustration illustrations aesthetic cute svg sublimation background backgrounds
for and the with of in kids adults
christmas xmas holiday holidays festive winter snowy snow spring summer autumn fall halloween valentine valentines
easter thanksgiving new year seasonal cozy cosy watercolor retro rustic boho minimalist modern woodland forest
soft pastel dark moody scene scenes nordic scandinavian colorful decor art line gift gifts instant""".split())


def _subject(text):
    """Subject words of a niche/search phrase without format words: 'bee ephemera' -> {'bee'}."""
    words = set(re.findall(r"[a-z]{3,}", (text or "").lower()))
    words = {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words}
    return {w for w in words if w not in FORMAT_WORDS}


def _recent_subjects(days=14):
    """Subjects of products made in the last days (rejected ones don't count)."""
    import time
    from . import storage
    cutoff = time.time() - days * 86400
    out = set()
    for p in storage.all_products():
        if p.get("created_at", 0) >= cutoff and p.get("status") != "rejected":
            out |= _subject(p.get("research", {}).get("search_query") or p.get("niche", ""))
    return out


def _recent_subjects_by_type(days=45):
    """{product type: subject words} of products made in the last days (rejected ones don't count)."""
    import time
    from . import storage
    cutoff = time.time() - days * 86400
    out = {}
    for p in storage.all_products():
        if p.get("created_at", 0) >= cutoff and p.get("status") != "rejected":
            out.setdefault(p.get("type"), set()).update(
                _subject(p.get("research", {}).get("search_query") or p.get("niche", "")) | _subject(p.get("title", "")))
    return out


def _today_types(today):
    from . import storage
    out = {}
    for p in storage.all_products():
        if p.get("day") == today.isoformat() and p.get("status") != "rejected":
            out[p.get("type")] = out.get(p.get("type"), 0) + 1
    return out


def _slots(n_cand, today):
    """One slot per candidate: product type + theme instruction."""
    types = _weighted_types(n_cand)
    best = []
    try:
        best = research.winners()
    except Exception:
        pass
    slots = []
    subj = config.env("ONLY_SUBJECT", "").strip()
    for i, t in enumerate(types):
        if subj:  # /uret planner migraine: every idea is about this subject (it overrides the shop theme)
            slots.append({"type": t, "theme": f"MANDATORY SUBJECT (overrides the shop theme): {subj}. The product must be "
                                              f"made for exactly this need or person, e.g. a {subj} {t.replace('_', ' ')}. "
                                              + (f"PLANNER STYLE (mandatory): {random.choice(shop.PLANNER_STYLES)}. Calm, pretty, adult; "
                                                 "no animals, no people. Do NOT add another planner edition (no business, "
                                                 "budget or student planner): the subject above is the edition."
                                                 if t == "planner" else "")})
            continue
        if best and i < min(2, len(best)):
            w = best[i]
            theme = (f'close variation of our own best seller "{w["title"]}": same buyer and product type, '
                     f"but a clearly different subject or scene, still inside our shop theme ({shop.theme()}). Never copy it")
            slots.append({"type": t, "theme": theme, "variation_of": w["title"]})
        else:
            slots.append({"type": t, "theme": shop.slot_theme(today, t)})
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
  junk_journal = a printable junk journal kit about ONE charming subject, e.g. honey bees, lighthouses, mushrooms;
  planner = an undated digital planner with a themed cover and matching stickers, e.g. cozy cottage, ocean, botanical).
- No trademarks, brands, celebrities, characters, franchises or copyrighted styles.
- The artwork is AI generated and CANNOT contain readable text: no quotes, words, names, monograms or lettering.
- Avoid these niches we already used recently: {', '.join(used[-40:]) or 'none'}.

Return ONLY a JSON array with exactly {len(slots)} objects in slot order:
[{{"niche": "specific niche in English", "search_query": "2-4 words a buyer types into Etsy search", "why": "short reason in Turkish"}}]"""
    data = llm.ask_json(prompt, temperature=1.0)
    if isinstance(data, dict):
        data = data.get("ideas") or [data]
    return data or []


def daily_plan(today):
    """Preset ideas for today's automatic production, from settings.json "daily_presets": one list per daily slot,
    e.g. [["sublimation:vintagexmas"], ["custom:xmaskids"], ["custom:boyama", ""]]. A slot with several entries
    takes the next one each day ("" = no preset that day, an AI idea of the normal product types fills the place).
    A preset whose themes are all in the shop already, or that was made today, is skipped the same way."""
    from . import presets, storage
    out = []
    try:
        today_presets = {(p.get("spec") or {}).get("preset") for p in storage.all_products()
                         if p.get("day") == today.isoformat() and p.get("status") != "rejected"}
    except Exception:
        today_presets = set()
    for slot in config.settings().get("daily_presets") or []:
        entry = slot[today.toordinal() % len(slot)] if slot else ""
        ptype, _, name = str(entry).partition(":")
        if not name or name in today_presets:
            continue
        try:
            preset = presets.load(ptype, name)
            v = presets.fresh(preset) if preset else None
        except Exception as e:
            print(f"[smart_niche] günlük plan: {entry} atlandı: {e}")
            continue
        if not v:
            print(f"[smart_niche] günlük plan: {entry} temalarının hepsi mağazada, bugün atlandı")
            continue
        idea = presets.idea(v, ptype)
        research._score(idea)
        out.append(idea)
    return out


def find_trending_niches(count=1, plan=True):
    from . import presets
    preset = presets.for_request()  # /uret custom xmaskids: a researched niche stored in presets/, no AI idea needed
    if preset:
        idea = presets.idea(preset, config.env("ONLY_TYPE"))
        research._score(idea)  # Etsy numbers for the approval message and the price (best effort)
        return [idea]
    if plan and not config.env("ONLY_TYPE") and not config.env("ONLY_SUBJECT", "").strip():
        from zoneinfo import ZoneInfo
        planned = daily_plan(dt.datetime.now(ZoneInfo(config.settings()["timezone"])).date())[:count]
        if planned:  # the owner's fixed daily products first, AI ideas only for the places they leave open
            rest = count - len(planned)
            try:
                return planned + (find_trending_niches(rest, plan=False) if rest > 0 else [])
            except Exception as e:
                print(f"[smart_niche] plan dışı fikirler bulunamadı: {e}")
                return planned
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
    subj = config.env("ONLY_SUBJECT", "").strip()
    try:
        if subj:
            raise RuntimeError("konu sabit (/uret ... konu)")
        from . import etsy_miner
        seen = {i["search_query"].lower() for i in ideas}
        for m in etsy_miner.find(max(3, count * 2), used, today):
            if m["search_query"] not in seen and not _too_similar(m["niche"], used):
                ideas.append(m)
    except Exception as e:
        print(f"[smart_niche] Etsy madenciliği atlandı: {e}")
    # best phrases from the /nis niche scan database (real Etsy data, last 21 days)
    try:
        if subj:
            raise RuntimeError("konu sabit (/uret ... konu)")
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

    # different subject than the last 2 weeks, and different product type than what was made today
    try:
        recent = _recent_subjects(int(s.get("subject_gap_days", 14) or 14))
    except Exception:
        recent = set()
    fresh = [i for i in ideas if not (_subject(i.get("search_query") or i["niche"]) & recent)]
    if fresh:
        ideas = fresh + [i for i in ideas if i not in fresh]
    try:
        made_today = _today_types(today)
    except Exception:
        made_today = {}
    max_same = s.get("max_same_type_per_day", 1)
    if all(made_today.get(i["type"], 0) >= max_same for i in ideas):
        made_today = {}  # every type already made today: allow repeats rather than producing nothing
    # never the same subject twice in the same product type (e.g. 4 Santa coloring books, 2 bee junk journals):
    # those listings only compete with each other in Etsy search
    try:
        recent_by_type = _recent_subjects_by_type(int(s.get("duplicate_gap_days", 45) or 45))
    except Exception:
        recent_by_type = {}

    def _dupe(i):
        return bool(_subject(i.get("search_query") or i["niche"]) & recent_by_type.get(i["type"], set()))

    chosen, per_type, variations = [], dict(made_today), 0
    for pass_no in (1, 2):
        for idea in ideas:
            if len(chosen) >= count:
                break
            t = idea["type"]
            if idea in chosen or per_type.get(t, 0) >= max_same or _dupe(idea):
                continue
            if pass_no == 1 and fresh and idea not in fresh:
                continue  # first pass: only subjects not used in the last 2 weeks
            if idea.get("variation_of"):
                if variations >= 1:
                    continue
                variations += 1
            chosen.append(idea)
            per_type[t] = per_type.get(t, 0) + 1
    reserve = [i for i in ideas if i not in chosen and not i.get("variation_of")]
    # reserves: no duplicates first, types not made today first, fresh subjects first
    reserve.sort(key=lambda i: (_dupe(i), per_type.get(i["type"], 0) >= max_same, i not in fresh))

    # nothing usable from the AI: on-theme fallback so the day is never empty (subjects not used yet first)
    backups = [(f"realistic {sub}", sub) for sub in shop.SUBJECTS]
    random.shuffle(backups)
    types = _weighted_types(count + 4)
    j = 0
    while len(chosen) + len(reserve) < count + 2 and j < len(types):
        t = types[j]
        if subj:  # /uret planner migraine: even the fallback stays on the requested subject
            sub = random.choice(shop.PLANNER_STYLES).split(":")[0] if t == "planner" else ""
            word = {"planner": "tracker planner", "journal": "journal", "stickers": "stickers"}.get(t, t.replace("_", " "))
            niche = f"{sub} {subj} {word}".strip()
            idea = {"type": t, "niche": niche, "search_query": f"{subj} {word.split()[0]}",
                    "why": f"Yedek niş (konu: {subj}).", "etsy_results": None}
            (chosen if len(chosen) < count else reserve).append(idea)
            j += 1
            continue
        if t == "planner":  # planners: an aesthetic, never an animal
            sub = random.choice(shop.PLANNER_STYLES).split(":")[0]
            ed = random.choice(["", "budget ", "student ", "ADHD ", "wellness ", "small business "])
            niche = f"{sub} {ed}digital planner"
        else:
            pool = [b for b in backups if not (_subject(b[1]) & recent_by_type.get(t, set()))] or backups
            niche, sub = pool[0]
            backups.remove((niche, sub))
        idea = {"type": t, "niche": niche, "search_query": " ".join(sub.split()[:3]),
                "why": "Yedek niş kullanıldı.", "etsy_results": None}
        (chosen if len(chosen) < count else reserve).append(idea)
        j += 1
    return chosen + reserve
