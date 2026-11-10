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
         "personalization_instructions")


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
    probs = problems(preset, ptype)
    if probs:
        raise RuntimeError(f"Hazır ayar hatalı ({path.name}): {'; '.join(probs)}")
    return preset


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


def problems(preset, ptype):
    """Same checks as an AI written plan (title and tag rules, banned words, number of designs)."""
    from . import research
    probs = [f"missing {f}" for f in ("niche", "search_query", "title", "tags", "palette", "designs") if not preset.get(f)]
    if probs:
        return probs
    probs += research.title_problems(preset["title"]) + research.tag_problems(preset["tags"], preset["title"])
    field, n = _list_field(ptype)
    items = [d for d in preset.get(field) or [] if isinstance(d, dict) and d.get("prompt") and d.get("name")]
    if len(items) != n:
        probs.append(f"'{field}' must have exactly {n} items with 'name' and 'prompt'")
    words = [preset["title"], preset["niche"], *preset["tags"]]
    for d in items:
        tag = str(d.get("tagline", ""))
        if ptype == "custom" and not 0 < len(tag) <= 30:
            probs.append(f"tagline of '{d['name']}' must be 1-30 characters")
        words += [tag, d["prompt"]]
    bad = sorted({w for w in words if research.is_banned(w)})
    if bad:
        probs.append(f"banned/trademark word in: {bad}")
    return probs


def for_request():
    """The preset asked for with /uret <type> <name> (ONLY_TYPE + ONLY_SUBJECT), or None."""
    return load(config.env("ONLY_TYPE"), config.env("ONLY_SUBJECT"))


def idea(preset, ptype):
    return {"type": ptype, "niche": preset["niche"], "search_query": preset["search_query"],
            "why": preset.get("why") or f"Hazır ayar: {preset['name']}", "source": "preset", "preset": preset["name"]}


def _ask_missing(preset, ptype, lo, hi):
    """The AI writes only what the preset does not fix: the description text and a few listing details."""
    from . import llm
    prompt = f"""Write the description for an Etsy digital product listing. Everything else is already decided.
Product type: {ptype} (personalized made-to-order PNG: the buyer types a name, we write it into every design)
Title (fixed, do not change): {preset['title']}
Made for: {preset.get('audience') or preset['niche']}
Designs: {', '.join(d['name'] for d in preset['designs'])}
Never use trademarks, brand names, characters, celebrities or copyrighted styles. All text in English.

Return JSON with these fields:
{{
  "intro": "2 short persuasive paragraphs. The FIRST sentence must contain the exact first part of the title. Describe the feeling, who it is for and how they will use it (gift, shirts, mugs); no file details, no emojis, no trademarks",
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
    lo, hi = config.settings()["price_ranges_usd"].get(ptype, [3, 8])
    extra = _ask_missing(preset, ptype, lo, hi)
    field, n = _list_field(ptype)
    out = {k: preset[k] for k in FIXED if preset.get(k)}
    out[field] = [dict(d) for d in preset[field][:n]]
    out["preset"] = preset["name"]
    part1 = preset["title"].split(",")[0].strip()
    intro = str(extra.get("intro") or "").strip()
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
