"""Quality gate for every NEW product (from the Nov 2026 "Etsy Mağaza Doktoru" audit of the shop).

The audit's weak points were: titles without the 3-part rule, listings with ~6.5 photos instead of 10, dark covers,
descriptions whose first sentence misses the main keyword, and missing file format / size details.
Before a product is shown for approval this module

  1. repairs what code can repair   - tags topped up to 13, the description opens with the title's first part,
                                      a dark cover is brightened, photos are topped up to 10 with honest info
                                      cards and close-ups made from the product's own images and real file list
  2. scores the product out of 100  - our OWN checklist (not Etsy's algorithm, not a sales forecast)

  Title SEO 10 · Tags & attributes 10 · Description 10 · Photos 20 · Digital delivery 10 ·
  Different from the rest of the shop 15 · Buyer trust 10 · Commercial presentation 15

Target: 90+. Under 90 the product is still sent to Telegram, with the missing points listed, so the owner decides.
"""
import io
import re

import numpy as np
from PIL import Image, ImageEnhance

from . import config, research
from .imgutil import jpeg_bytes

TARGET = 90
PHOTOS = 10
DARK = 115        # mean brightness (0-255) of the cover under which a thumbnail reads as dark
DESC_WORDS = 150
_FORMAT = re.compile(r"\b(pdf|png|jpe?g|svg|zip)\b", re.I)
_SIZE = re.compile(r"\b(\d{3,5}\s*x\s*\d{3,5}|dpi|px|pixels?|a4|a5|us letter|inch(es)?)\b", re.I)


def title_lead(title):
    return (title or "").split(",")[0].strip()


def _first_sentence(desc):
    return re.split(r"(?<=[.!?])\s|\n", (desc or "").strip(" ✨\n"), maxsplit=1)[0]


# ------------------------------------------------------------------ repairs
def lead_intro(intro, title):
    """The first sentence must carry the title's first part (Etsy and Google show it as the summary)."""
    lead = title_lead(title)
    intro = (intro or "").strip()
    if not lead or lead.lower()[:25] in _first_sentence(intro).lower():
        return intro
    return f"{lead}, ready as an instant digital download. {intro}".strip()


def fill_tags(tags, title, extra=()):
    """All 13 tags: keep the good ones, then add 2-3 word phrases from the title and `extra` (never longer than 20)."""
    out = []

    def add(t):
        t = research.fit_tag(t) if t else ""
        if t and len(t) <= 20 and not research.is_banned(t) and t.lower() not in [x.lower() for x in out]:
            out.append(t)

    for t in tags or []:
        add(str(t))
    words = [w.strip(",.!()").lower() for w in (title or "").split() if len(w.strip(",.!()")) > 2]
    cands = list(extra)
    for part in (title or "").split(","):
        ws = [w.strip(".!()").lower() for w in part.split() if w.strip(".!()")]
        for n in (3, 2):
            cands += [" ".join(ws[i:i + n]) for i in range(0, max(0, len(ws) - n + 1))]
    cands += [f"{a} {b}" for a, b in zip(words, words[2:])] + ["digital download", "instant download", "printable gift"]
    for c in cands:
        if len(out) >= 13:
            break
        add(c)
    return out[:13]


def brightness(im):
    return float(np.asarray(im.convert("L").resize((64, 64))).mean())


def brighten(im):
    """A dark cover is hard to read as a small thumbnail: lift it gently (never a washed-out picture)."""
    b = brightness(im)
    if b >= DARK:
        return im
    out = ImageEnhance.Brightness(im.convert("RGB")).enhance(min(1.45, (DARK + 12) / max(b, 1)))
    return ImageEnhance.Contrast(out).enhance(1.04)


def top_up_photos(mockups, files, title):
    """[(name, jpeg)] -> at least 10 photos; the extra ones come from the product's own images and file list."""
    if len(mockups) >= PHOTOS or not mockups:
        return mockups
    from . import shopfix
    ims = [Image.open(io.BytesIO(b)).convert("RGB") for _, b in mockups]
    have = {n for n, _ in mockups}
    extra = shopfix.extra_photos(ims[0], ims, [{"filename": f["name"], "size": f["size"]} for f in files], title,
                                 PHOTOS - len(mockups))
    k = len(mockups)
    out = list(mockups)
    for n, b in extra:
        k += 1
        n = f"{k:02d}-{n}"
        if n not in have:
            out.append((n, b))
    return out[:PHOTOS]


def repair_cover(mockups):
    if not mockups:
        return mockups
    name, data = mockups[0]
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if brightness(im) >= DARK:
        return mockups
    return [(name, jpeg_bytes(brighten(im), 90, dpi=72))] + list(mockups[1:])


# ------------------------------------------------------------------ score
def _tiny(data):
    return np.asarray(Image.open(io.BytesIO(data)).convert("L").resize((16, 16))).astype(np.int16)


def score(p, mockups, other_titles=(), recent_layouts=()):
    """-> {"total": 0-100, "parts": {name: (points, max)}, "missing": [Turkish notes]} for one product dict."""
    title, desc, tags = p.get("title", ""), p.get("description", ""), p.get("tags") or []
    miss, parts = [], {}

    def part(name, mx, checks):
        got = 0
        for pts, ok, note in checks:
            if ok:
                got += pts
            elif note:
                miss.append(note)
        parts[name] = (min(got, mx), mx)

    tp = research.title_problems(title)
    lead_words = len(title_lead(title).split())
    part("Başlık SEO", 10, [(7 - min(7, 3 * len(tp)), True, ""), (0, not tp, "başlık: " + "; ".join(tp)[:160]),
                            (3, 2 <= lead_words <= 6, "başlığın ilk öbeği 2-6 kelime olmalı")])

    multi = sum(len(t.split()) >= 2 for t in tags)
    tw = set(research._title_words(title))
    echo = sum(all(w.lower() in tw for w in t.split()) for t in tags)
    styles = p.get("styles") or p.get("spec", {}).get("styles")
    part("Etiket ve nitelikler", 10, [
        (3, len(tags) >= 13, f"etiket {len(tags)}/13"),
        (3, multi >= 10, f"2-3 kelimelik etiket {multi}/10"),
        (1, all(len(t) <= 20 for t in tags), "20 karakteri aşan etiket var"),
        (1, echo <= 5, "etiketlerin çoğu başlığı tekrar ediyor"),
        (1, bool(styles), "stil niteliği boş"),
        (1, bool(p.get("files")), "materyal için dosya listesi yok")])

    words = len(desc.split())
    low = desc.lower()
    part("Açıklama", 10, [
        (3, words >= DESC_WORDS, f"açıklama {words} kelime (en az {DESC_WORDS})"),
        (3, title_lead(title).lower()[:25] in _first_sentence(desc).lower(), "ilk cümle ana anahtar kelimeyle başlamıyor"),
        (2, "what's included" in low, "What's Included bölümü yok"),
        (2, "how to use" in low or "how to download" in low, "kullanım bölümü yok")])

    sizes = [Image.open(io.BytesIO(b)).size for _, b in mockups]
    cover = Image.open(io.BytesIO(mockups[0][1])) if mockups else None
    tiny = [_tiny(b) for _, b in mockups]
    twins = sum(1 for i in range(len(tiny)) for j in range(i) if np.abs(tiny[i] - tiny[j]).mean() < 4)
    part("Görseller", 20, [
        (min(10, len(mockups)), True, ""), (0, len(mockups) >= PHOTOS, f"görsel {len(mockups)}/{PHOTOS}"),
        (3, bool(sizes) and min(sizes[0]) >= 2000, "kapak 2000 pikselden küçük"),
        (4, cover is not None and brightness(cover) >= DARK, "kapak karanlık"),
        (3, bool(sizes) and all(abs(w / h - 1) < 0.01 for w, h in sizes), "kare olmayan görsel var")])

    files = p.get("files") or []
    part("Dijital teslim", 10, [
        (4, bool(_FORMAT.search(desc)), "açıklamada dosya formatı yok"),
        (3, bool(_SIZE.search(desc)), "açıklamada ölçü / DPI yok"),
        (3, 0 < len(files) <= 5 and all(f["size"] <= 20 * 1048576 for f in files), "teslimat dosyaları Etsy sınırında değil")])

    mine = set(research._title_words(title))
    near = [t for t in other_titles if t and t != title and
            len(mine & set(research._title_words(t))) >= 0.75 * max(1, len(mine))]
    layout = p.get("cover_layout")
    part("Mağazadan farklılaşma", 15, [
        (6, not near, "başlık mağazadaki başka bir ilana çok benziyor: " + (near[0][:60] if near else "")),
        (4, not layout or layout not in list(recent_layouts)[-2:], "kapak düzeni son iki ürünle aynı"),
        (5, twins == 0, f"{twins} görsel birbirinin kopyası gibi")])

    part("Alıcıya güven", 10, [
        (3, "no physical item" in low, "fiziksel ürün gönderilmediği yazmıyor"),
        (3, "purchases" in low, "indirme yeri (Purchases) yazmıyor"),
        (2, "ai tools" in low or "ai-" in low, "yapay zekâ açıklaması yok"),
        (2, "use" in low and ("commercial" in low or "personal" in low), "lisans bilgisi yok")])

    lo, hi = config.settings()["price_ranges_usd"].get(p.get("type"), [0, 1e9])
    price = float(p.get("price_usd") or 0)
    med = (p.get("research") or {}).get("etsy_median_price")
    part("Ticari sunum", 15, [
        (5, lo <= price <= hi, f"fiyat ${price:.2f} ayarlanan aralığın dışında (${lo}-${hi})"),
        (5, not med or price <= float(med) * 1.25, f"fiyat piyasa ortancasının (${med}) belirgin üstünde"),
        (5, len(title) <= 140 and len(title_lead(title)) <= 45, "başlığın ilk öbeği telefonda kesilecek kadar uzun")])

    return {"total": sum(g for g, _ in parts.values()), "parts": parts, "missing": miss}


def caption_lines(q):
    """Telegram lines for the approval message."""
    icon = "✅" if q["total"] >= TARGET else "⚠️"
    lines = [f"{icon} Kalite kontrolü: <b>{q['total']}/100</b> (botun kendi kontrol listesi, Etsy puanı değildir)"]
    if q["total"] < TARGET or q["missing"]:
        short = [f"{n} {g}/{m}" for n, (g, m) in q["parts"].items() if g < m]
        if short:
            lines.append("   " + " · ".join(short))
        lines += [f"   – {m}" for m in q["missing"][:10]]
    return lines
