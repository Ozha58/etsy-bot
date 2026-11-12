"""Shop treatment ("mağaza tedavisi") built from the Nov 2026 shop audit (score 18/100, launch stage).

The audit's weakest areas and what this module does about each one:

  Trust & showcase (1/5)  -> shop headline, announcement, buyer thank-you messages and digital download
                             policy text are written through the API; banner + logo images and the
                             About / policies checklist are sent to Telegram (Etsy has no API for those).
  Title SEO (7/18)        -> every title becomes 3 comma separated parts, max 14 words, no filler words
                             (Beautiful, Unique, Perfect...), no repeated words.
  Tags & attributes       -> all 13 tags, at least 10 of them 2-3 word buyer phrases that add words the
                             title does not have; empty 'materials' and 'styles' are filled.
  Images & video          -> photos without alt text get one; listings with < 10 photos get honest extra
                             photos (what's included, file details, how to download, close-up details);
                             listings without a video get a short mockup video.
  Digital delivery        -> descriptions name the real file formats and sizes, a WHAT'S INCLUDED and a
                             HOW TO DOWNLOAD section, and the first sentence repeats the main keyword.

python -m bot shopfix --audit          only measure (nothing changes on Etsy)
python -m bot shopfix --dry-run        show what would change
python -m bot shopfix [--limit N]      treat the shop (continues where the last run stopped)
"""
import html
import io
import re
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import config, etsy, llm, research, storage, telegram
from .imgutil import font, jpeg_bytes
from .telegram import esc

VERSION = "shopfix-4"  # bump to treat every listing again
SHOP_NAME = config.SHOP_NAME
OLD_NAMES = ("Sebasteia",)  # earlier shop name: shop texts that still say it are rewritten

# ------------------------------------------------------------------ shop level texts (English: buyers read them)
SHOP_TITLE = "Realistic Printables, Coloring Pages, Junk Journal Kits"  # max 55
ANNOUNCEMENT = f"""Welcome to {SHOP_NAME} - realistic, detailed printables you can download in seconds.

What you will find here:
• Coloring pages and coloring books (PDF)
• Junk journal kits, ephemera and digital paper
• Printable bullet journal pages and digital planners
• Sublimation PNG designs, clipart and phone wallpapers

Every item is an INSTANT DIGITAL DOWNLOAD. Nothing is shipped - your files are ready under
You > Purchases and Reviews right after checkout.

New designs are added every week. Tap the heart next to our shop name to follow along and never miss a new release.

Questions or a file problem? Send us a message - we answer within 24 hours and always make it right."""

SALE_MESSAGE = f"""Thank you so much for your order from {SHOP_NAME}!

HOW TO DOWNLOAD
1. Sign in to Etsy on a computer or the Etsy website (the app does not always show downloads).
2. Go to You > Purchases and Reviews.
3. Click "Download Files" next to your order. ZIP files: right click > Extract All (on iPhone: open with Files).

Need help, another size or a different format? Just reply to this message - I will help right away.

If you enjoy your files, a short review means the world to a small shop and helps other buyers find us. Thank you!"""

POLICY_ADDITIONAL = """DIGITAL DOWNLOADS
• All items are instant digital downloads. No physical product is shipped.
• Files are available under You > Purchases and Reviews right after payment is confirmed.
• Because digital files cannot be returned, we do not accept returns or exchanges. If a file is damaged, missing or
  does not open, message us and we will send a working copy or a refund.
• Colors can look slightly different on screens and printers.

LICENSE
• Personal use unless the listing says commercial use. Please do not share or resell the files themselves.

CONTACT
• We reply to every message within 24 hours."""

MANUAL_STEPS = """📋 <b>Etsy'nin API ile izin vermediği adımlar (~15 dk)</b>
Hepsini <b>bilgisayardan</b> ya da telefonda tarayıcıdan etsy.com'da yap: Etsy Seller uygulamasında bu ayarların çoğu yok.

1️⃣ <b>Banner</b>: Shop Manager › sol menüde <i>Sales Channels</i> altında mağaza adının yanındaki <b>kalem</b> simgesi ›
   en üstte <i>Banner to showcase your brand…</i> › <i>Big banner</i> → ekteki <code>banner-3360x840.jpg</code>
   (küçük bant istersen <i>Mini banner</i> → <code>banner-mini-1200x300.jpg</code>)
2️⃣ <b>Logo</b>: Shop Manager › <b>Settings</b> › <b>Your shop</b> › <i>Logo</i> › Add / Edit → ekteki <code>logo-500.jpg</code>
3️⃣ <b>About (Hakkında)</b>: Settings › Your shop › sağ üstte <b>Shop home editor</b> › aşağı kaydır › <i>About</i> →
   aşağıdaki hikâye metnini yapıştır, mümkünse kendi fotoğrafını ekle
4️⃣ <b>Politikalar</b>: Shop Manager › <b>Settings</b> › <b>Policy settings</b>. Dijital ürünlerin iade kuralı
   (<i>Instant downloads</i>) Etsy'de hazır ve değiştirilemez, sen bir şey seçmezsin.
5️⃣ <b>FAQ</b>: mağaza sayfasındaki FAQ alanına "How do I download?" ve "Can I print at home?" sorularını ekle
   (Shop home editor › aşağıda <i>FAQs</i>; görünmüyorsa bu adımı atla)
6️⃣ <b>İlk satış indirimi</b>: Shop Manager › <b>Marketing</b> › <b>Sales and discounts</b> › <i>New special offer</i> ›
   %25-30, 14 gün
7️⃣ <b>Dış trafik</b>: Pinterest pinleri (/pin) ve TikTok videoları (/sosyal_3)
8️⃣ <b>Bölümler</b>: Shop Manager › <b>Listings</b> › sağdaki <i>Sections</i> kutusu; 3-8 bölüm ideal, boş ya da tek ilanlı
   bölümleri birleştir"""

ABOUT_STORY = f"""Hi, I'm the maker behind {SHOP_NAME}.

I create realistic, detailed printables - each one about a single charming subject: honey bees, lighthouses, cozy
cottages, woodland animals and winter forests. Every design is drawn with the help of digital tools, then
hand-curated, cleaned up and tested in print before it reaches the shop.

My goal is simple: files that print beautifully at home, download instantly and make your journaling, coloring and
crafting time a little calmer. If anything is not right, message me - I always answer."""


# ------------------------------------------------------------------ audit
_FORMAT_WORDS = re.compile(r"\b(pdf|png|jpe?g|svg|zip|dpi|mb|pixels?|px|a4|a5|us letter|8\.5\s*x\s*11)\b", re.I)


def _plain(s):
    return html.unescape(s or "")


def title_parts(title):
    return [p.strip() for p in _plain(title).split(",") if p.strip()]


def listing_audit(li, images=None, video=None, files=None) -> dict:
    """Numbers for one listing, the same checks the shop audit used."""
    title, desc = _plain(li.get("title")), _plain(li.get("description"))
    tags = [_plain(t) for t in li.get("tags") or []]
    first = re.split(r"(?<=[.!?])\s|\n", desc.strip(" ✨\n"), maxsplit=1)[0].lower() if desc else ""
    lead = (title_parts(title) or [""])[0].lower()
    a = {
        "title_problems": research.title_problems(title),
        "three_parts": len(title_parts(title)) == 3,
        "words": len(title.split()),
        "filler": research.filler_in(title),
        "tag_problems": research.tag_problems(tags, title),
        "tags": len(tags),
        "multi_tags": sum(len(t.split()) >= 2 for t in tags),
        "materials": bool(li.get("materials")),
        "styles": bool(li.get("style") or li.get("styles")),
        "desc_words": len(desc.split()),
        "first_sentence_keyword": bool(lead) and lead[:25] in first,
        "file_details": bool(_FORMAT_WORDS.search(desc)),
        "how_to_download": "download" in desc.lower() and ("purchases" in desc.lower() or "how to" in desc.lower()),
        "favorites": int(li.get("num_favorers") or 0),
        "views": int(li.get("views") or 0),
    }
    if images is not None:
        a["images"] = len(images)
        a["alt_missing"] = sum(not (i.get("alt_text") or "").strip() for i in images)
    if video is not None:
        a["video"] = bool(video)
    if files is not None:
        a["files"] = len(files)
    # a 0-100 listing score, used to treat the weakest listings first
    s = 0
    s += 20 if not a["title_problems"] else max(0, 20 - 5 * len(a["title_problems"]))
    s += 15 if not a["tag_problems"] else max(0, 15 - 5 * len(a["tag_problems"]))
    s += 5 * a["materials"] + 5 * a["styles"]
    s += 10 * a["first_sentence_keyword"] + 10 * a["file_details"] + 5 * a["how_to_download"]
    if images is not None:
        s += min(15, int(1.5 * a["images"])) + (5 if not a["alt_missing"] else 0)
    if video is not None:
        s += 10 * a["video"]
    a["score"] = s
    return a


def shop_audit(listings, details=None) -> dict:
    """Shop wide totals (what the audit report showed)."""
    n = len(listings) or 1
    rows = [l["_audit"] for l in listings if "_audit" in l]
    if not rows:
        rows = [listing_audit(l) for l in listings]
    pct = lambda k: round(100 * sum(bool(r.get(k)) for r in rows) / n)
    out = {
        "listings": len(listings),
        "three_part_titles_pct": pct("three_parts"),
        "titles_ok_pct": round(100 * sum(not r["title_problems"] for r in rows) / n),
        "avg_title_words": round(sum(r["words"] for r in rows) / n, 1),
        "titles_with_filler": sum(bool(r["filler"]) for r in rows),
        "all_13_tags_pct": round(100 * sum(r["tags"] >= 13 for r in rows) / n),
        "tags_ok_pct": round(100 * sum(not r["tag_problems"] for r in rows) / n),
        "materials_pct": pct("materials"),
        "styles_pct": pct("styles"),
        "keyword_first_sentence_pct": pct("first_sentence_keyword"),
        "file_details_pct": pct("file_details"),
        "how_to_download_pct": pct("how_to_download"),
        "favorites_total": sum(r["favorites"] for r in rows),
        "avg_score": round(sum(r["score"] for r in rows) / n),
    }
    if all("images" in r for r in rows):
        out["avg_images"] = round(sum(r["images"] for r in rows) / n, 1)
        out["ten_images_pct"] = round(100 * sum(r["images"] >= 10 for r in rows) / n)
        out["alt_missing"] = sum(r["alt_missing"] for r in rows)
    if all("video" in r for r in rows):
        out["video_pct"] = pct("video")
    if details is not None:
        out["announcement"] = bool((details.get("announcement") or "").strip())
        out["sale_message"] = bool((details.get("digital_sale_message") or details.get("sale_message") or "").strip())
        out["shop_title"] = bool((details.get("title") or "").strip())
        out["shop_favorites"] = details.get("num_favorers")
        out["sales"] = details.get("transaction_sold_count")
    return out


# ------------------------------------------------------------------ titles and tags
_llm_fails = [0]  # text AI failures in a row during this run
_llm_skip = [0]   # listings skipped since the last failed try


def new_seo(li, ptype, product=None) -> dict:
    """{"title", "tags", "styles"} that pass the audit rules (LLM, then a safe local repair)."""
    title = _plain(li.get("title"))
    tags = [_plain(t) for t in li.get("tags") or []]
    desc = _plain(li.get("description"))[:700]
    prompt = f"""You are an Etsy SEO expert fixing a DIGITAL DOWNLOAD listing of a brand new shop.
Current title: {title}
Current tags: {', '.join(tags)}
Product type: {ptype or 'digital download'}
Description start: {desc}

Write:
1. "title": a {research.TITLE_RULE}.
   Keep the real product (do not invent items, counts or features). Part 2 must say the format buyers search
   (e.g. 'Printable PDF', 'Digital Download', 'PNG Bundle'). Example of the shape:
   "Space Christmas Coloring Pages, Printable PDF Kids Activity, Astronaut Winter Holiday Gift"
2. "tags": exactly 13 Etsy tags, each max 20 characters, at least 10 of them 2-3 word phrases real buyers type.
   Tag 1 = part 1 of the title (shortened to 20 characters if needed). At least 8 tags must add words that are NOT in
   the title: synonyms, colors, room, occasion/holiday, recipient/gift ('gift for mom'), use ('teacher resource').
   No single generic words, no brand names, no tag about art style quality.
3. "styles": 2 Etsy style words for the artwork (e.g. Vintage, Watercolor, Minimalist, Boho, Rustic, Cottagecore).

Return ONLY JSON: {{"title": "...", "tags": ["..."], "styles": ["...", "..."]}}"""
    best = None
    for attempt in range(3):
        if _llm_fails[0] >= 2 and _llm_skip[0] < 3:  # the text AI is down (overloaded or out of quota): the next
            _llm_skip[0] += 1                        # three listings do not wait for it, the fourth asks again
            break
        _llm_skip[0] = 0
        try:
            res = llm.ask_json(prompt, temperature=0.5)
            _llm_fails[0] = 0
        except Exception as e:
            print(f"[shopfix] LLM hatası: {e}")
            _llm_fails[0] += 1
            break  # quota / outage: a second try now fails the same way and only costs minutes
        t = (res.get("title") or "").strip().strip('"')
        tg = []
        for x in res.get("tags") or []:
            x = research.fit_tag(x)
            if x and not research.is_banned(x) and x.lower() not in [y.lower() for y in tg]:
                tg.append(x)
        tg = tg[:13]
        probs = (research.title_problems(t) if t else ["no title"]) + research.tag_problems(tg, t)
        if t and research.is_banned(t):
            probs.append("contains a banned/trademark word")
        cand = {"title": t, "tags": tg, "styles": [str(s) for s in (res.get("styles") or [])][:2], "probs": probs}
        if best is None or len(probs) < len(best["probs"]):
            best = cand
        if not probs:
            break
        prompt += f"\n\nYour previous answer had problems: {probs}. Fix ALL of them."
    if not best or not best["title"]:
        best = {"title": title, "tags": tags, "styles": [], "probs": ["LLM yanıt vermedi"], "no_llm": True}
    if research.title_problems(best["title"]):
        fixed = research.fix_title(best["title"])
        if len(research.title_problems(fixed)) <= len(research.title_problems(best["title"])):
            best["title"] = fixed
    # never lose tags: fill up to 13 with the old multi-word tags
    for x in tags:
        x = research.fit_tag(x)
        if len(best["tags"]) >= 13:
            break
        if x and x.lower() not in [y.lower() for y in best["tags"]]:
            best["tags"].append(x)
    best["tags"] = etsy._clean_tags(best["tags"])
    return best


# ------------------------------------------------------------------ description
def _fsize(f):
    """Etsy listing files give size_bytes (and a text 'filesize'); our own records give size."""
    return int(f.get("size_bytes") or f.get("size") or 0)


def _mb(n):
    return f"{(n or 0) / 1048576:.1f} MB"


def fixed_description(desc, title, files, ptype=None, known_dpi=False) -> str:
    """Keep the seller's text and add what the audit found missing. Returns the (maybe unchanged) description."""
    d = _plain(desc).strip()
    parts = title_parts(title)
    lead = parts[0] if parts else title
    low = d.lower()
    first = re.split(r"(?<=[.!?])\s|\n", d.strip(" ✨\n"), maxsplit=1)[0].lower() if d else ""
    if lead and lead.lower()[:25] not in first:
        rest = ", ".join(parts[1:])
        opener = f"{lead}" + (f" - {rest}." if rest else ".")
        d = opener + "\n\n" + d
        low = d.lower()
    names = [f.get("filename") or f.get("name") or "" for f in files or []]
    exts = sorted({n.rsplit(".", 1)[-1].upper() for n in names if "." in n})
    if names and "what's included" not in low and "whats included" not in low and "what is included" not in low:
        lines = [f"• {n} ({_mb(_fsize(f))})" for n, f in zip(names, files)]
        d += "\n\n🎁 WHAT'S INCLUDED\n" + "\n".join(lines)
    if not _FORMAT_WORDS.search(d) or "file details" not in low:
        det = []
        if exts:
            det.append("File format: " + ", ".join(exts) + (" (unzip to see the PDF/PNG/JPG files inside)" if "ZIP" in exts else ""))
        if names:
            det.append(f"{len(names)} downloadable file{'s' if len(names) > 1 else ''}, total "
                       f"{_mb(sum(_fsize(f) for f in files))}")
        if known_dpi:
            det.append("High resolution 300 DPI - prints sharp at home or at a print shop")
        if ptype in ("coloring", "journal", "planner", "junk_journal"):
            det.append("Sized for US Letter and A4 paper")
        det.append("Instant digital download - no physical item is shipped")
        d += "\n\n📁 FILE DETAILS\n" + "\n".join(f"• {x}" for x in det)
    if "purchases" not in d.lower():
        d += ("\n\n💡 HOW TO DOWNLOAD\n• After payment go to You > Purchases and Reviews on etsy.com\n"
              "• Click Download Files (ZIP: right click > Extract All; iPhone: open with Files)\n"
              "• Problem with a file? Message us - we reply within 24 hours")
    if "digital download" not in d.lower():
        d += "\n\nThis is a digital download."
    return d[:4900] if len(d) > 4900 else d


# ------------------------------------------------------------------ extra listing photos
S = 2000
INK, PAPER, ACCENT = (44, 40, 36), (250, 246, 239), (176, 112, 74)


def _card(cover, heading, lines, sub=""):
    """Square info photo: heading, large lines on the left, the WHOLE cover as a framed thumbnail on the right.
    (The first version used a cut strip of the cover as a top band: half a title, half a picture - it looked like
    a mistake between the other photos.)"""
    im = Image.new("RGB", (S, S), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, S, 26), fill=ACCENT)
    d.text((140, 250), heading, font=font("serif", 150), fill=INK, anchor="lm")
    d.rectangle((140, 372, 420, 384), fill=ACCENT)
    th = 760  # the cover, complete and small: this card belongs to that product
    thumb = ImageOps.contain(cover.convert("RGB"), (th, th), Image.LANCZOS)
    tx, ty = S - 140 - thumb.width, 640 + (th - thumb.height) // 2
    sh = Image.new("RGBA", (thumb.width + 80, thumb.height + 80), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((40, 48, thumb.width + 40, thumb.height + 48), 36, fill=(60, 45, 30, 70))
    im.paste(sh.filter(ImageFilter.GaussianBlur(18)), (tx - 40, ty - 40), sh.filter(ImageFilter.GaussianBlur(18)))
    mask = Image.new("L", thumb.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, thumb.width - 1, thumb.height - 1), 36, fill=255)
    im.paste(thumb, (tx, ty), mask)
    y, width = 640, tx - 140 - 110
    for ln in lines:
        fl = font("sans_medium", 80)
        while d.textlength(ln, font=fl) > width and fl.size > 54:
            fl = font("sans_medium", fl.size - 2)
        if d.textlength(ln, font=fl) > width:  # a long file name: shorten it instead of running under the picture
            while len(ln) > 8 and d.textlength(ln + "…", font=fl) > width:
                ln = ln[:-1]
            ln += "…"
        d.ellipse((140, y + 22, 180, y + 62), fill=ACCENT)
        d.text((220, y), ln, font=fl, fill=INK)
        y += 190
        if y > S - 330:
            break
    if sub:
        d.text((140, S - 170), sub, font=font("sans", 54), fill=(110, 100, 92), anchor="lm")
    return im


def closeups(photos: list, n: int) -> list:
    """Up to n square close-ups that show ONE whole design: a window whose edge runs over calm background while
    its inside is full of colour. A blind crop cut text cards and grids in half (seen in the shop); a photo with
    no such window (text card, full bleed scene) gives no close-up at all. The same design is not shown twice."""
    out, seen = [], []
    for im in photos:
        if len(out) >= n:
            break
        w, h = im.size
        if min(w, h) < 1000:
            continue
        q = max(1, min(w, h) // 250)
        a = np.asarray(im.convert("RGB").resize((w // q, h // q), Image.BILINEAR)).astype(np.int16)
        sh, sw = a.shape[:2]
        lum = a.mean(axis=2)
        busy = (a.max(axis=2) - a.min(axis=2)) > 50

        def calm_edge(x0, y0, side, limit=0.05):
            """The frame runs over background: almost no coloured or dark pixels on it."""
            r, x1, y1 = max(2, side // 22), x0 + side, y0 + side
            rim = np.concatenate([lum[y0:y0 + r, x0:x1].ravel(), lum[y1 - r:y1, x0:x1].ravel(),
                                  lum[y0:y1, x0:x0 + r].ravel(), lum[y0:y1, x1 - r:x1].ravel()])
            rimb = np.concatenate([busy[y0:y0 + r, x0:x1].ravel(), busy[y1 - r:y1, x0:x1].ravel(),
                                   busy[y0:y1, x0:x0 + r].ravel(), busy[y0:y1, x1 - r:x1].ravel()])
            return (rimb | (np.abs(rim - np.median(rim)) > 30)).mean() <= limit

        def artwork(x0, y0, side):
            """Real artwork has many colours. A flat shape (the round "1" of a how-it-works card, a button, a
            coloured box) has one or two and is no close-up - that is what got into the shop."""
            win = a[y0:y0 + side, x0:x0 + side][busy[y0:y0 + side, x0:x0 + side]]
            if len(win) < 30:
                return False
            codes = (win[:, 0] >> 5) * 64 + (win[:, 1] >> 5) * 8 + (win[:, 2] >> 5)
            counts = np.bincount(codes, minlength=512)
            return int((counts >= max(3, 0.03 * len(win))).sum()) >= 4 and counts.max() <= 0.7 * len(win)

        best = None
        for frac in (0.55, 0.45, 0.36, 0.28):
            side = int(min(sw, sh) * frac)
            ring = max(2, side // 22)
            step = max(2, side // 8)
            for y0 in range(0, sh - side + 1, step):
                for x0 in range(0, sw - side + 1, step):
                    fill = busy[y0 + ring:y0 + side - ring, x0 + ring:x0 + side - ring].mean()
                    if fill < 0.15 or not calm_edge(x0, y0, side) or not artwork(x0, y0, side):
                        continue
                    score = fill * (1 + frac)
                    if best is None or score > best[0]:
                        best = (score, x0, y0, side)
        if not best:
            continue
        _, x0, y0, side = best
        # frame the design itself: the biggest connected shape in the window, with a little air around it
        # (a stray word or a neighbour's sparkle near the window edge stays outside)
        from scipy import ndimage
        lab, cnt = ndimage.label(ndimage.binary_dilation(busy[y0:y0 + side, x0:x0 + side], iterations=3))
        if cnt:
            big = 1 + int(np.argmax(ndimage.sum(np.ones_like(lab), lab, range(1, cnt + 1))))
            ys, xs = np.nonzero(lab == big)
            s2 = int(max(ys.max() - ys.min(), xs.max() - xs.min()) * 1.16) + 2
            if side * 0.6 <= s2 <= side:
                cx, cy = x0 + (xs.min() + xs.max()) // 2, y0 + (ys.min() + ys.max()) // 2
                x0 = max(0, min(sw - s2, cx - s2 // 2))
                y0 = max(0, min(sh - s2, cy - s2 // 2))
                side = s2
        win = busy[y0:y0 + side, x0:x0 + side]
        ys, xs = np.flatnonzero(win.any(axis=1)), np.flatnonzero(win.any(axis=0))
        win = win[ys.min():ys.max() + 1, xs.min():xs.max() + 1]  # the design itself, wherever it sits in the frame
        sig = np.asarray(Image.fromarray((win * 255).astype(np.uint8)).resize((24, 24))) > 96
        if any((sig & o).sum() / max(1, (sig | o).sum()) > 0.6 for o in seen):
            continue
        seen.append(sig)
        out.append(im.crop((x0 * q, y0 * q, (x0 + side) * q, (y0 + side) * q)).resize((S, S), Image.LANCZOS))
    return out


# which extra photo is worth a free slot first (close-ups sell, the two cards answer the usual questions) ...
_PRIORITY = ("closeup-1", "files-included", "download-steps", "closeup-2", "closeup-3", "closeup-4")
# ... and the order they are shown in: artwork first, download help last
_ORDER = ("closeup-1", "closeup-2", "closeup-3", "closeup-4", "files-included", "download-steps")


def extra_photos(cover, existing: list, files, title, need: int, have=(), cards=True) -> list:
    """[(name, jpeg)] honest extra photos made from the listing's own images and real file list, in display order.
    At most two text cards (four near-identical ones in a row looked like filler). `have`: what the listing already
    shows ("what" / "how"), so nothing is said twice. cards=False: close-ups only - a made-to-order product is not
    an instant download, those cards would be wrong for it."""
    made = {}
    names = [f.get("filename") or "" for f in files or []]
    exts = sorted({n.rsplit(".", 1)[-1].upper() for n in names if "." in n})
    total = sum(_fsize(f) for f in files or [])
    if cards and names and "what" not in have:
        fmt = [e for e in exts if e != "ZIP"]
        lines = [f"{len(names)} file{'s' if len(names) > 1 else ''}, {_mb(total)} in total",
                 "Format: " + ", ".join(fmt) if fmt else "ZIP folder, unzip to open",
                 "Instant digital download",
                 "Opens on any device",
                 "Yours to keep"]
        made["files-included"] = _card(cover, "What's Included", lines, title_parts(title)[0][:60] if title else "")
    if cards and "how" not in have:
        made["download-steps"] = _card(cover, "How to Download", [
            "1. Complete your purchase",
            "2. Go to your Purchases",
            "3. Click Download Files",
            "4. Unzip, then print or use" if "ZIP" in exts else "4. Print at home or use it",
            "Download again any time",
        ], "Digital item, nothing is shipped. Questions? Message us any time.")
    if need > 0 and "detail" not in have:
        for k, im in enumerate(closeups(existing, 4), 1):
            made[f"closeup-{k}"] = im
    pick = [n for n in _PRIORITY if n in made][:max(0, need)]
    return [(f"{n}.jpg", jpeg_bytes(made[n].convert("RGB"), 90, dpi=72)) for n in _ORDER if n in pick]


# ------------------------------------------------------------------ banner and logo
def banner_images(covers: list) -> list:
    """[(name, jpeg)] big banner 3360x840, mini banner 1200x300 and a 500x500 logo from the shop's own covers."""
    covers = [c.convert("RGB") for c in covers if c is not None][:6] or [Image.new("RGB", (800, 800), (220, 210, 196))]
    out = []
    for name, (W, H) in (("banner-3360x840.jpg", (3360, 840)), ("banner-mini-1200x300.jpg", (1200, 300))):
        im = Image.new("RGB", (W, H), PAPER)
        n = len(covers)
        tile = W // max(n, 1)
        for i, c in enumerate(covers):
            im.paste(ImageOps.fit(c, (tile + 2, H), Image.LANCZOS), (i * tile, 0))
        veil = Image.new("RGBA", (W, H), (250, 246, 239, 150))
        im.paste(veil, (0, 0), veil)
        d = ImageDraw.Draw(im)
        bw, bh = int(W * 0.46), int(H * 0.62)
        d.rounded_rectangle(((W - bw) // 2, (H - bh) // 2, (W + bw) // 2, (H + bh) // 2), int(H * 0.06), fill=PAPER)
        d.text((W // 2, H // 2 - int(H * 0.07)), SHOP_NAME.upper(), font=font("serif", int(H * 0.2)), fill=INK, anchor="mm")
        d.text((W // 2, H // 2 + int(H * 0.13)), "Realistic Printables · Instant Download",
               font=font("sans_medium", int(H * 0.065)), fill=ACCENT, anchor="mm")
        out.append((name, jpeg_bytes(im, 92, dpi=72)))
    logo = Image.new("RGB", (500, 500), INK)
    d = ImageDraw.Draw(logo)
    d.ellipse((30, 30, 470, 470), outline=PAPER, width=8)
    d.text((250, 235), SHOP_NAME[0], font=font("serif", 260), fill=PAPER, anchor="mm")
    d.text((250, 395), SHOP_NAME.upper(), font=font("sans_medium", 40), fill=PAPER, anchor="mm")
    out.append(("logo-500.jpg", jpeg_bytes(logo, 92, dpi=72)))
    return out


# ------------------------------------------------------------------ run
def _img(b):
    try:
        return Image.open(io.BytesIO(b)).convert("RGB")
    except Exception:
        return None


def treat_shop(dry_run=False) -> list:
    notes = []
    try:
        det = etsy.shop_details()
    except Exception as e:
        return [f"⚠️ mağaza bilgisi alınamadı: {e}"]
    want = {"title": SHOP_TITLE, "announcement": ANNOUNCEMENT, "sale_message": SALE_MESSAGE,
            "digital_sale_message": SALE_MESSAGE, "policy_additional": POLICY_ADDITIONAL}
    # empty fields are filled; a text that still carries the shop's old name is replaced too
    change = {k: v for k, v in want.items()
              if not (det.get(k) or "").strip() or any(o.lower() in (det.get(k) or "").lower() for o in OLD_NAMES)}
    if not change:
        return ["mağaza başlığı, duyuru ve teşekkür mesajları zaten dolu"]
    if dry_run:
        return [f"(önizleme) doldurulacak: {', '.join(change)}"]
    for k, v in change.items():  # one by one: a field Etsy refuses never blocks the others
        try:
            etsy.update_shop(**{k: v})
            notes.append(f"✅ {k}")
        except Exception as e:
            notes.append(f"⚠️ {k}: {str(e)[:120]}")
    return notes


NO_LLM = "başlık/etiket bekliyor (Gemini yanıt vermedi)"
MADE_TO_ORDER = ("custom", "tattoo")  # personalised, sent later: "instant download" cards would be wrong


def _alt(im):
    return (im.get("alt_text") or "").rsplit(" - ", 1)[-1].strip().lower()


_OLD_CARDS = ("what is included", "how to download", "file formats and details", "good to know before you buy")
_NEW_CARDS = ("files you receive", "download steps")
_TEXT_ALTS = _OLD_CARDS + _NEW_CARDS + ("included sizes",)  # text cards: nothing to zoom into


def _late(images) -> list:
    """Photos added well after the listing's first photo: ours (a treatment), not the product's own set."""
    ts = [im.get("created_timestamp") for im in images if im.get("created_timestamp")]
    if not ts:
        return []
    return [im for im in images if (im.get("created_timestamp") or 0) >= min(ts) + 3600]


def old_extras(images) -> list:
    """Photos of earlier treatments that have to go:
    shopfix-1  blind crops as close-ups, recognised by their order: [what is included,] how to download,
               [file details,] close-ups
    shopfix-2  four text cards with a cut strip of the cover on top (looked like a broken picture)
    The product's own photos (also its own "how it works" card) and the good close-ups stay."""
    ims = sorted(images, key=lambda i: i.get("rank", 99))
    late = _late(ims)
    ours = late if late else ims  # with dates only photos added later can be ours
    out = []
    how = next((k for k, im in enumerate(ims) if _alt(im) == "how to download" and im in ours), None)
    if how is not None and any(_alt(im) == "close-up detail" for im in ims[how + 1:]):
        out = [ims[how]] + [im for im in ims[how + 1:] if _alt(im) in ("file formats and details", "close-up detail")]
        if how > 0 and _alt(ims[how - 1]) == "what is included" and ims[how - 1] in ours:
            out.insert(0, ims[how - 1])
    for im in ims:
        mine = im in late if late else _alt(im) in _OLD_CARDS[2:]  # no dates: only the labels nothing else uses
        if im not in out and mine and _alt(im) in _OLD_CARDS:
            out.append(im)
    # shopfix-2/3 close-ups could be a flat shape cut from a text card (a big round "1"): they carry the old label.
    # Then the whole late set goes, so the new one is built in the right order (artwork first, cards last).
    if any(_alt(im) == "close-up detail" for im in late):
        out += [im for im in late if im not in out and _alt(im) in ("close-up detail",) + _NEW_CARDS]
    return sorted(out, key=lambda i: i.get("rank", 99))


def shown(images) -> set:
    """What the listing already tells the buyer, so an extra photo never repeats it."""
    late = _late(images)
    have = set()
    for im in images:
        a = _alt(im)
        if a in ("what is included", "files you receive"):
            have.add("what")
        if a in ("how to download", "download steps"):
            have.add("how")
        if a == "close-up of one design":
            have.add("detail")
    return have


def treat_listing(li, product, dry_run=False) -> list:
    lid = li["listing_id"]
    ptype = (product or {}).get("type") or etsy._type_from_title(li.get("title"))
    notes, change = [], {}
    images = etsy.listing_images(lid)
    files = etsy.listing_files(lid)
    has_video = etsy.listing_video_count(lid) > 0
    before = listing_audit(li, images, has_video, files)

    seo = None
    title = _plain(li.get("title"))
    if before["title_problems"] or before["tag_problems"] or not before["styles"]:
        seo = new_seo(li, ptype, product)
        if seo.get("no_llm"):
            notes.append(NO_LLM)
        if seo["title"] and seo["title"] != title and \
                len(research.title_problems(seo["title"])) < len(before["title_problems"]):
            change["title"] = etsy.nice_title(seo["title"])[:140]
        old_tags = [_plain(t) for t in li.get("tags") or []]
        if len(research.tag_problems(seo["tags"], change.get("title", title))) < len(before["tag_problems"]) or \
                (before["tag_problems"] and len(seo["tags"]) > len(old_tags)):
            change["tags"] = seo["tags"]
        if not before["styles"] and seo.get("styles"):
            change["styles"] = etsy._clean_styles(seo["styles"])
    new_title = change.get("title", title)
    if not before["materials"]:
        change["materials"] = etsy.materials_for([f.get("filename") for f in files], ptype)
    desc = fixed_description(li.get("description"), new_title, files, ptype, known_dpi=bool(product))
    if desc.strip() != _plain(li.get("description")).strip():
        change["description"] = desc

    if change:
        label = ", ".join({"title": "başlık", "tags": "etiket", "styles": "stil", "materials": "materyal",
                           "description": "açıklama"}[k] for k in change)
        if dry_run:
            notes.append(f"(önizleme) {label}" + (f": {change['title']}" if "title" in change else ""))
        else:
            try:
                etsy.update_listing(lid, **change)
                notes.append(label)
            except Exception as e:
                if "styles" in change and "style" in str(e).lower():
                    change.pop("styles")
                    etsy.update_listing(lid, **change)
                    notes.append(label.replace(", stil", ""))
                else:
                    raise
            if product is not None:
                for k in ("title", "tags", "description"):
                    if k in change:
                        product[k] = change[k]
                storage.add_event(product, "mağaza tedavisi: " + label)
                storage.save_product(product)

    # alt text for every photo (search engines and accessibility)
    missing = [im for im in images if not (im.get("alt_text") or "").strip()]
    if missing and not dry_run:
        ok = 0
        for im in missing:
            try:
                etsy.set_alt_text(lid, im["listing_image_id"], im.get("rank", 1),
                                  etsy._alt_text(new_title, "cover" if im.get("rank") == 1 else f"page{im.get('rank')}"))
                ok += 1
            except Exception as e:
                print(f"[shopfix] {lid} alt metin: {e}")
                break
        if ok:
            notes.append(f"{ok} foto alt metni")
    elif missing:
        notes.append(f"(önizleme) {len(missing)} foto alt metni")

    # the first treatment added blind crops as "close-ups" (text cards and grids cut in half) and put the download
    # card before them: take that set away, the new one below replaces it in the right order
    stale = old_extras(images)
    if stale:
        if dry_run:
            notes.append(f"(önizleme) {len(stale)} eski ek foto silinip yenisi eklenecek")
            images = [im for im in images if im not in stale]
        else:
            gone = 0
            for im in stale:
                try:
                    etsy.delete_image(lid, im["listing_image_id"])
                    gone += 1
                except Exception as e:
                    print(f"[shopfix] {lid} eski ek foto silinemedi: {e}")
            if gone:
                notes.append(f"{gone} hatalı ek foto silindi")
            images = etsy.listing_images(lid)

    # extra photos up to 10, and a video when there is none
    pics = []
    need = 10 - len(images)
    have = shown(images)  # what is already there is never added a second time
    if (need > 0 or not has_video) and images:
        art = []  # photos a close-up may come from: the product's own artwork, never a text card
        for k, im in enumerate(images[:8 if need > 0 else 5]):  # more photos = more chances for a close-up
            try:
                pic = _img(etsy.download_image(im))
            except Exception as e:
                print(f"[shopfix] {lid} foto indirilemedi: {e}")
                continue
            if pic is None:
                continue
            pics.append(pic)
            if k and _alt(im) not in _TEXT_ALTS:
                art.append(pic)
    if need > 0 and pics:
        # close-ups from the inner photos first: a crop of the cover would cut its title text in half
        extra = extra_photos(pics[0], art, files, new_title, need, have,
                             cards=ptype not in MADE_TO_ORDER)
        if dry_run:
            if extra:
                notes.append(f"(önizleme) +{len(extra)} foto")
        else:
            added = 0
            for i, (name, data) in enumerate(extra):
                try:
                    etsy.add_image(lid, name, data, len(images) + i + 1, etsy._alt_text(new_title, name))
                    added += 1
                except Exception as e:
                    print(f"[shopfix] {lid} foto eklenemedi: {e}")
                    break
            if added:
                notes.append(f"+{added} foto ({len(images) + added}/10)")
    if not has_video and pics:
        if dry_run:
            notes.append("(önizleme) video")
        else:
            try:
                from . import etsy_video
                vb = etsy_video.make(pics[:5])
                if vb:
                    etsy.add_video(lid, bytes(vb))
                    notes.append("video")
            except Exception as e:
                print(f"[shopfix] {lid} video: {e}")
    return notes


def run(audit_only=False, dry_run=False, limit=None, shop_part=True):
    listings = etsy.shop_listings("active")
    by_lid = {str(p.get("etsy", {}).get("listing_id")): p for p in storage.all_products() if p.get("etsy")}
    try:
        details = etsy.shop_details()
    except Exception as e:
        print(f"[shopfix] mağaza bilgisi alınamadı: {e}")
        details = None
    for li in listings:
        li["_audit"] = listing_audit(li)
    before = shop_audit(listings, details)
    print(f"[shopfix] önce: {before}")
    if audit_only:
        _report("📊 <b>Mağaza denetimi</b> (hiçbir şey değişmedi)", before, None, [], [])
        return before

    shop_notes = treat_shop(dry_run) if shop_part else []
    if shop_part and not dry_run:
        try:  # banner + logo + manual steps (no API for these)
            covers = []
            for li in sorted(listings, key=lambda l: -int(l.get("num_favorers") or 0))[:6]:
                ims = etsy.listing_images(li["listing_id"])
                if ims:
                    covers.append(_img(etsy.download_image(ims[0])))
            for name, data in banner_images(covers):
                telegram.document(name, data, name)
            telegram.send(MANUAL_STEPS)
            telegram.send("📝 <b>About metni</b> (kopyala-yapıştır):\n\n<code>" + esc(ABOUT_STORY) + "</code>")
        except Exception as e:
            print(f"[shopfix] banner/el adımları gönderilemedi: {e}")

    meta = storage.load_meta()
    done = meta.setdefault("shopfix_done", {})
    todo = [li for li in listings if done.get(str(li["listing_id"])) != VERSION or dry_run]
    todo.sort(key=lambda l: l["_audit"]["score"])  # weakest listings first (the audit's 'urgent' list)
    if limit:
        todo = todo[:limit]
    results, errors = [], []
    t0 = time.time()
    no_llm = 0
    for li in todo:
        lid = str(li["listing_id"])
        try:
            notes = treat_listing(li, by_lid.get(lid), dry_run)
            results.append((_plain(li.get("title"))[:60], notes))
            if NO_LLM in notes:  # title / tags could not be rewritten: photos and description are done, the
                no_llm += 1      # listing stays on the list so the next run writes its title and tags
            elif not dry_run:
                done[lid] = VERSION
                storage.save_meta(meta)
            print(f"[shopfix] {lid}: {notes}", flush=True)
        except Exception as e:
            errors.append(f"{_plain(li.get('title'))[:50]}: {str(e)[:150]}")
            print(f"[shopfix] {lid} HATA: {e}", flush=True)
        if time.time() - t0 > 95 * 60:  # stay inside the workflow time limit; the next run continues
            errors.append("süre doldu - kalan ilanlar bir sonraki çalıştırmada")
            break

    if no_llm:
        errors.append(f"{no_llm} ilanın başlık/etiketi yazılamadı: metin yapay zekâsı (Gemini) yanıt vermedi, büyük "
                      "ihtimalle günlük kota doldu. Fotoğraf ve açıklamaları düzeltildi; kota yenilenince /tedavi "
                      "yeniden yazın, yalnızca başlık ve etiketleri tamamlar")
    after = None
    if not dry_run:
        fresh = etsy.shop_listings("active")
        for li in fresh:
            li["_audit"] = listing_audit(li)
        try:
            details = etsy.shop_details()
        except Exception:
            pass
        after = shop_audit(fresh, details)
        meta = storage.load_meta()
        meta["shop_audit"] = {"at": int(time.time()), "before": before, "after": after}
        storage.save_meta(meta)
    left = sum(1 for li in listings if storage.load_meta().get("shopfix_done", {}).get(str(li["listing_id"])) != VERSION)
    head = "🧪 <b>Mağaza tedavisi önizlemesi</b> (Etsy'de değişmedi)" if dry_run else "🩺 <b>Mağaza tedavisi</b>"
    _report(head, before, after, shop_notes, results, errors, left)
    return after or before


_LABELS = [("three_part_titles_pct", "3 bölümlü başlık", "%"), ("titles_ok_pct", "Kurala uyan başlık", "%"),
           ("avg_title_words", "Ort. başlık kelimesi", ""), ("titles_with_filler", "Dolgu kelimeli başlık", ""),
           ("all_13_tags_pct", "13 etiketin hepsi", "%"), ("tags_ok_pct", "Kurala uyan etiket", "%"),
           ("materials_pct", "Materyal dolu", "%"), ("styles_pct", "Stil dolu", "%"),
           ("keyword_first_sentence_pct", "İlk cümlede anahtar kelime", "%"),
           ("file_details_pct", "Dosya formatı/boyutu yazılı", "%"), ("how_to_download_pct", "İndirme talimatı", "%"),
           ("avg_score", "Ort. ilan puanı", "/100")]


def _report(head, before, after, shop_notes, results, errors=(), left=0):
    lines = [head, ""]
    for k, label, unit in _LABELS:
        if k not in before:
            continue
        b = before[k]
        lines.append(f"• {label}: {b}{unit}" + (f" → <b>{after[k]}{unit}</b>" if after and k in after else ""))
    for k, label in (("announcement", "Duyuru"), ("sale_message", "Teşekkür mesajı"), ("shop_title", "Mağaza başlığı")):
        if k in before:
            lines.append(f"• {label}: {'✅' if before[k] else '❌'}" + (f" → {'✅' if after.get(k) else '❌'}" if after and k in after else ""))
    if shop_notes:
        lines.append("\n🏪 Mağaza: " + "; ".join(esc(n) for n in shop_notes))
    if results:
        lines.append(f"\n🛠 {len(results)} ilan işlendi:")
        for t, notes in results[:30]:
            lines.append(f"• {esc(t)} → {esc(', '.join(notes) or 'zaten iyi')}")
    for e in list(errors)[:8]:
        lines.append(f"⚠️ {esc(e)}")
    if left:
        lines.append(f"\n⏭ Kalan ilan: {left} (tekrar çalıştır: /tedavi)")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) > 3800:
            _send(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        _send(chunk)


def _send(text):
    try:
        telegram.send(text)
    except Exception as e:
        print(f"[shopfix] Telegram: {e}\n{text}")
