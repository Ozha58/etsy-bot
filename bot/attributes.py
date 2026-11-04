"""Etsy listing attributes (Holiday, Occasion, Room, Subject, Orientation, colors...).

Attributes work like free extra tags: Etsy uses them for search filters and matching.
We read the attributes Etsy offers for the listing's category, let the AI choose
values ONLY from Etsy's own lists, and save them on the listing.
Any problem here is logged and skipped; it never stops a publish.
"""
from . import llm

# not useful or risky for digital downloads
SKIP = {"craft type", "materials", "dimensions", "width", "height", "length", "size", "weight",
        "personalization", "made to order", "recipient", "framing", "number of items"}
MAX_VALUES = 120


def _properties(req, taxonomy_id):
    res = req("GET", f"/seller-taxonomy/nodes/{taxonomy_id}/properties")
    out = []
    for pr in res.get("results", []):
        name = (pr.get("display_name") or pr.get("name") or "").strip()
        vals = pr.get("possible_values") or []
        if not name or not vals or name.lower() in SKIP:
            continue
        if pr.get("supports_attributes") is False:
            continue
        out.append({
            "id": pr["property_id"],
            "name": name,
            "multi": bool(pr.get("is_multivalued")),
            "max": int(pr.get("max_values_allowed") or (5 if pr.get("is_multivalued") else 1)),
            "values": {str(v["name"]).strip(): v["value_id"] for v in vals[:MAX_VALUES] if v.get("name")},
        })
    return out


def choose(p, props):
    """Ask the AI which values fit this product. Returns {property name: [value names]}."""
    menu = "\n".join(f'- "{pr["name"]}" (choose {"up to " + str(min(pr["max"], 3)) if pr["multi"] else "1"}): '
                     + " | ".join(pr["values"]) for pr in props)
    prompt = f"""You fill in Etsy listing attributes for a DIGITAL DOWNLOAD product.
Title: {p.get('title')}
Product type: {p.get('type')}
Niche: {p.get('niche')}
Tags: {', '.join(p.get('tags', []))}

Available attributes and their ONLY allowed values:
{menu}

Rules:
- Pick values only when they clearly fit this product; skip an attribute if nothing fits.
- Copy the value text exactly as written in the list.
- Holiday / Occasion: only when the theme really is that holiday or occasion.
- Colors: the main colors of the artwork.

Return ONLY JSON: {{"attributes": {{"<attribute name>": ["<value>", ...]}}}}"""
    data = llm.ask_json(prompt, temperature=0.2)
    if isinstance(data, dict) and isinstance(data.get("attributes"), dict):
        return data["attributes"]
    return data if isinstance(data, dict) else {}


def fill(req, shop_id, listing_id, taxonomy_id, p) -> list:
    """Set attributes on a listing. req = etsy._req bound to a token. Returns the saved 'Name: value' texts."""
    saved = []
    try:
        props = _properties(req, taxonomy_id)
        if not props:
            return saved
        picks = choose(p, props)
        by_name = {pr["name"].lower(): pr for pr in props}
        for name, vals in picks.items():
            pr = by_name.get(str(name).lower())
            if not pr:
                continue
            vals = vals if isinstance(vals, list) else [vals]
            lookup = {k.lower(): (k, v) for k, v in pr["values"].items()}
            hits = [lookup[str(v).strip().lower()] for v in vals if str(v).strip().lower() in lookup]
            hits = hits[:pr["max"] if pr["multi"] else 1]
            if not hits:
                continue
            try:
                req("PUT", f"/shops/{shop_id}/listings/{listing_id}/properties/{pr['id']}",
                    json={"value_ids": [h[1] for h in hits], "values": [h[0] for h in hits]})
                saved.append(f"{pr['name']}: {', '.join(h[0] for h in hits)}")
            except Exception as e:
                print(f"[attributes] {pr['name']} kaydedilemedi: {e}")
    except Exception as e:
        print(f"[attributes] atlandı: {e}")
    return saved
