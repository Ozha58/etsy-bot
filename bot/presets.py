"""Ready-made presets: a niche that was researched by hand, stored as presets/<product type>/<name>.json.

/uret custom xmaskids (tappable: /uret_custom_xmaskids) builds the product from the preset: the designs, taglines,
title, tags and palette come from the file, the AI only writes the description and the few fields the file leaves
out. A subject without a preset file (e.g. /uret custom teacher) keeps the normal AI research.
"""
import json
import re

from . import config

DIR = config.ROOT / "presets"
NAME_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
# taken from the file as they are; everything else is filled in by spec()
FIXED = ("title", "tags", "palette", "set_name", "kind", "sample_name", "sample_names", "look",
         "personalization_instructions", "page_style", "doodles", "above", "art", "subject")
# product types whose preset may ask for more (or fewer) designs than the type's usual number: "count": 12
FLEX_COUNT = {"sublimation": (4, 16)}


# a theme may replace these fields of the preset (same look and delivery, other characters, title and tags)
THEME_FIELDS = ("label_tr", "niche", "search_query", "why", "set_name", "sample_name", "sample_names", "style",
                "palette", "title", "tags", "designs", "pages", "audience", "doodles", "above", "skin")


def load(ptype, name):
    """The preset dict, or None when there is no such file (then the caller keeps the old behaviour)."""
    name = (name or "").strip().lower().replace(" ", "_")
    if not ptype or not NAME_OK.match(name):
        return None
    path = DIR / ptype / f"{name}.json"
    if not path.is_file():
        return None
    try:
        preset = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"Hazır ayar okunamadı ({path.name}): {e}")
    preset["name"] = name
    for v in variants(preset):
        probs = problems(v, ptype)
        if probs:
            raise RuntimeError(f"Hazır ayar hatalı ({path.name}, tema {v['theme']}): {'; '.join(probs)}")
    return preset


def variants(preset):
    """The preset once per theme: the file's own fields are the first theme, "themes" adds more."""
    base = {k: v for k, v in preset.items() if k != "themes"}
    out = [dict(base, theme=str(preset.get("theme") or "classic"))]
    for t in preset.get("themes") or []:
        if isinstance(t, dict) and t.get("theme"):
            out.append(dict(base, **{k: t[k] for k in THEME_FIELDS if k in t}, theme=str(t["theme"]).lower()))
    return out


def _used_themes(name):
    """Themes of this preset that already became a product (oldest first; rejected products do not count)."""
    try:
        from . import storage
        ps = [p for p in storage.all_products()
              if (p.get("spec") or {}).get("preset") == name and p.get("status") != "rejected"]
    except Exception as e:
        print(f"[presets] kullanılan temalar okunamadı: {e}")
        return []
    return [str((p.get("spec") or {}).get("theme") or "classic") for p in sorted(ps, key=lambda p: p.get("created_at", 0))]


def choose(preset, want=""):
    """One theme of the preset: the one asked for (/uret custom xmaskids dino), otherwise a theme that has not
    been made yet, otherwise the one made longest ago. So two runs never give the same listing twice in a row."""
    vs = variants(preset)
    want = (want or "").strip().lower().replace(" ", "_")
    if want:
        hit = [v for v in vs if v["theme"] == want]
        if not hit:
            raise RuntimeError(f"'{preset['name']}' ayarında '{want}' teması yok. Temalar: {', '.join(v['theme'] for v in vs)}")
        return hit[0]
    used = _used_themes(preset["name"])
    fresh = [v for v in vs if v["theme"] not in used]
    if fresh:
        return fresh[0]
    last = {t: i for i, t in enumerate(used)}  # position of each theme's latest product
    return min(vs, key=lambda v: last.get(v["theme"], -1))


def fresh(preset):
    """A theme of the preset that has not become a product yet, or None when every theme is already in the shop
    (the daily plan then makes something else instead of the same listing a second time)."""
    used = _used_themes(preset["name"])
    return next((v for v in variants(preset) if v["theme"] not in used), None)


def names(ptype):
    d = DIR / ptype
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def _list_field(ptype):
    """(field name, item count) of the product type's design list, e.g. custom -> ("designs", 6)."""
    from . import research
    lf = research._LIST_FIELD.get(ptype)
    if not isinstance(lf, tuple):
        raise RuntimeError(f"'{ptype}' türü için hazır ayar desteklenmiyor")
    return lf


def _count(preset, ptype):
    """(field name, item count) for this preset: the type's own number, or the preset's "count" where allowed."""
    field, n = _list_field(ptype)
    lo, hi = FLEX_COUNT.get(ptype, (n, n))
    want = preset.get("count")
    if isinstance(want, int) and not isinstance(want, bool) and lo <= want <= hi:
        n = want
    return field, n


def problems(preset, ptype):
    """Same checks as an AI written plan (title and tag rules, banned words, number of designs)."""
    from . import research
    probs = [f"missing {f}" for f in ("niche", "search_query", "title", "tags", "palette", "designs") if not preset.get(f)]
    if probs:
        return probs
    probs += research.title_problems(preset["title"]) + research.tag_problems(preset["tags"], preset["title"])
    field, n = _count(preset, ptype)
    if preset.get("count") not in (None, n):
        lo, hi = FLEX_COUNT.get(ptype, (n, n))
        probs.append(f"'count' must be a whole number from {lo} to {hi} for {ptype}")
    no_art = preset.get("art") is False  # lettering only (name coloring pages): designs carry a caption, no drawing
    items = [d for d in preset.get(field) or [] if isinstance(d, dict) and (no_art or d.get("prompt")) and d.get("name")]
    if len(items) != n:
        probs.append(f"'{field}' must have exactly {n} items with 'name' and 'prompt'")
    words = [preset["title"], preset["niche"], *preset["tags"]]
    for d in items:
        tag = str(d.get("tagline", ""))
        if ptype == "custom" and not 0 < len(tag) <= 30:
            probs.append(f"tagline of '{d['name']}' must be 1-30 characters")
        words += [tag, str(d.get("prompt", ""))]
    bad = sorted({w for w in words if research.is_banned(w)})
    if bad:
        probs.append(f"banned/trademark word in: {bad}")
    return probs


def for_request():
    """The preset theme asked for with /uret <type> <name> [theme] (ONLY_TYPE + ONLY_SUBJECT), or None."""
    name, _, want = config.env("ONLY_SUBJECT").strip().lower().partition(" ")
    preset = load(config.env("ONLY_TYPE"), name)
    return choose(preset, want) if preset else None


def idea(preset, ptype):
    return {"type": ptype, "niche": preset["niche"], "search_query": preset["search_query"],
            "why": preset.get("why") or f"Hazır ayar: {preset['name']}", "source": "preset", "preset": preset["name"],
            "theme": preset.get("theme") or "classic"}


KIND_NOTE = {"custom": "personalized made-to-order PNG: the buyer types a name, we write it into every design",
             "sublimation": "instant download bundle of finished PNG shirt designs with short funny phrases, "
                            "transparent background, for sublimation, DTF and print on demand"}


def _ask_missing(preset, ptype, lo, hi):
    """The AI writes only what the preset does not fix: the description text and a few listing details."""
    from . import llm
    prompt = f"""Write the description for an Etsy digital product listing. Everything else is already decided.
Product type: {ptype} ({KIND_NOTE.get(ptype, KIND_NOTE["custom"])})
Title (fixed, do not change): {preset['title']}
Made for: {preset.get('audience') or preset['niche']}
Designs: {', '.join(d['name'] for d in preset['designs'])}
Never use trademarks, brand names, characters, celebrities or copyrighted styles. All text in English.

Return JSON with these fields:
{{
  "intro": "2 short persuasive paragraphs. The FIRST sentence must contain the exact first part of the title. Describe the feeling, who it is for and how they will use it (gift, shirts, mugs); no file details, no emojis, no trademarks, no movie, song or character names",
  "styles": [2 short Etsy style words for this artwork],
  "price_usd": number between {lo} and {hi},
  "cover_scene": "English prompt for ONE cozy lifestyle scene about this product's subject, no text, no faces in close-up"
}}"""
    for attempt in range(2):
        try:
            data = llm.ask_json(prompt, temperature=0.8)
            if isinstance(data, dict) and str(data.get("intro") or "").strip():
                return data
        except Exception as e:
            print(f"[presets] açıklama yazılamadı (deneme {attempt + 1}): {e}")
    return {}


def spec(idea):
    """Product plan in the shape research.product_spec() returns, built from the preset file."""
    from . import research, theme
    ptype = idea["type"]
    preset = load(ptype, idea["preset"])
    if preset is None:
        raise RuntimeError(f"Hazır ayar bulunamadı: {ptype}/{idea['preset']}")
    preset = choose(preset, idea.get("theme") or "classic")
    lo, hi = config.settings()["price_ranges_usd"].get(ptype, [3, 8])
    extra = _ask_missing(preset, ptype, lo, hi)
    field, n = _count(preset, ptype)
    out = {k: preset[k] for k in FIXED if preset.get(k) not in (None, "", [])}  # keeps false, e.g. "art": false
    out[field] = [dict(d) for d in preset[field][:n]]
    out["preset"] = preset["name"]
    out["theme"] = preset["theme"]
    if ptype in FLEX_COUNT:
        out["count"] = n
    if preset.get("look") == "festive":  # every theme gets its own colours and decorations (custom_festive.SKINS)
        out["skin"] = str(preset.get("skin") or preset["theme"])
    part1 = preset["title"].split(",")[0].strip()
    intro = str(extra.get("intro") or "").strip()
    if (not intro or research.is_banned(intro)) and ptype != "custom":
        intro = (f"{part1} for {preset.get('audience') or 'crafters and small shops'}: {n} finished designs, "
                 "each with its own short phrase.\n\nReady to press on shirts, sweatshirts, mugs and totes, "
                 "with a transparent background.")
    if not intro or research.is_banned(intro):
        intro = (f"{part1} made to order for {preset.get('audience') or 'your family'}. "
                 f"Type the name at checkout and we write it into all {n} designs.\n\n"
                 "Ready to press on shirts, mugs, totes and more, with a transparent background.")
    out["intro"] = intro
    style = str(preset.get("style") or extra.get("style") or "")
    # the shop style is mandatory for every image, unless the preset brings its own ("own_style": true)
    if not (preset.get("own_style") and style) and theme.style()[:30].lower() not in style.lower():
        style = f"{theme.style()}, {style[:80]}".strip(", ")
    out["style"] = style
    out["styles"] = [str(s) for s in (preset.get("styles") or extra.get("styles") or [])][:2]
    out["cover_scene"] = str(preset.get("cover_scene") or extra.get("cover_scene") or "")
    try:
        ai_price = float(preset.get("price_usd") or extra.get("price_usd"))
    except (TypeError, ValueError):
        ai_price = (lo + hi) / 2
    out["price_usd"] = research.market_price(idea, lo, hi, ai_price)  # always inside the settings.json range
    out["tags"] = [t for t in (research.fit_tag(t) for t in preset["tags"]) if t][:13]
    return out
