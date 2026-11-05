"""Undated hyperlinked digital LIFE planner (iPad / Android tablets, landscape PDF).

Benchmarked against the best sellers (BrighterPlans: 94k sales; 720 pages, 6 themes, 80+ templates,
50+ covers, 1000+ stickers). We ship: 750+ pages, 6 color themes (5 light + dark), Sunday and Monday
start, 80 templates, 12 notebooks, 50+ covers and 1000+ stickers, plus a how-to page.
AI makes only the art (1 cover + 8 themed stickers); every text is drawn by us, so no spelling mistakes."""
import random

from PIL import Image, ImageDraw, ImageFilter

from .. import ephemera as E
from .. import images, planner_pdf, planner_stickers
from ..bundle_cover import bundle_cover
from ..imgutil import color_to_alpha_background, fit_text, font, hex2rgb, jpeg_bytes, make_zips, png_bytes, \
    paste_with_shadow, thumb_b64, trim_alpha
from ..mockups import H as MH, W as MW

LABEL_TR = "Dijital yaşam planlayıcısı (750+ linkli sayfa, 6 renk teması, 80 şablon, 1000+ sticker, 50+ kapak)"
SPEC_FIELDS = """
  "edition": "one of: life, budget, student, adhd, wellness, business (use the one given in the planner theme)",
  "planner_name": "short planner name, 2-4 words: the aesthetic + the edition (e.g. 'Neutral Boho Budget', 'Sage Student', 'Dark Academia')",
  "cover": {"prompt": "English prompt for ONE beautiful aesthetic horizontal cover image in the planner style (texture, pattern, flowers or a calm scene; NO animals, NO people), calm area in the lower center, no text"},
  "stickers": [ exactly 8 objects {"name": "short name", "prompt": "English prompt for ONE single isolated aesthetic object that fits the style (flower, leaf, cup, candle, book...), no animals, no text"} ]
"""
OBJECT_SUFFIX = ("single isolated object, centered with empty space around it, pure plain white background, "
                 "no shadow, no ground, no text, no letters, no border, no frame")
COVER_SUFFIX = "wide horizontal composition, soft calm area in the center, no text, no letters, no border, no frame"

# preset color themes (besides the product's own palette and dark mode)
THEMES = {
    "Sage": [(124, 150, 120), (176, 152, 110), (150, 120, 130), (110, 130, 150)],
    "Blush": [(214, 140, 150), (180, 150, 190), (220, 170, 120), (150, 170, 190)],
    "Ocean": [(70, 120, 160), (90, 160, 170), (200, 150, 110), (120, 120, 170)],
    "Lavender": [(150, 130, 190), (190, 140, 170), (120, 160, 170), (200, 170, 120)],
    "Neutral": [(150, 130, 110), (120, 120, 120), (180, 160, 130), (110, 120, 110)],
}
INK = (48, 44, 40)


def _tablet(page, width=1500):
    pw = width
    ph = int(page.height * pw / page.width)
    bez = int(pw * 0.035)
    dev = Image.new("RGBA", (pw + 2 * bez, ph + 2 * bez), (0, 0, 0, 0))
    d = ImageDraw.Draw(dev)
    d.rounded_rectangle((0, 0, dev.width - 1, dev.height - 1), radius=bez * 2, fill=(28, 28, 32, 255))
    d.rounded_rectangle((3, 3, dev.width - 4, dev.height - 4), radius=bez * 2, outline=(70, 70, 76, 255), width=3)
    dev.paste(page.resize((pw, ph), Image.LANCZOS), (bez, bez))
    return dev


def _bg(accent):
    tint = tuple(int(c * 0.12 + 246 * 0.88) for c in accent)
    return E.aged_paper(MW, MH, tint, seed=11, stains=False).convert("RGBA")


def _title(c, text, sub, accent, y=60):
    d = ImageDraw.Draw(c)
    hf = fit_text(d, text, "sans_bold", 1700, 96, 50)
    d.text((MW / 2 - d.textlength(text, font=hf) / 2, y), text, font=hf, fill=INK + (255,))
    if sub:
        sf = fit_text(d, sub, "sans", 1600, 44, 26)
        d.text((MW / 2 - d.textlength(sub, font=sf) / 2, y + 120), sub, font=sf, fill=accent + (255,))


def _badge(c, cx, cy, big, small, col):
    d = ImageDraw.Draw(c)
    r = 118
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((cx - r, cy - r + 10, cx + r, cy + r + 10), fill=(0, 0, 0, 70))
    c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(c)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (255,), outline=(255, 255, 255, 255), width=8)
    bf = fit_text(d, big, "sans_bold", r * 1.6, 70, 34)
    d.text((cx - d.textlength(big, font=bf) / 2, cy - 62), big, font=bf, fill=(255, 255, 255, 255))
    sf = fit_text(d, small, "sans_bold", r * 1.6, 30, 18)
    d.text((cx - d.textlength(small, font=sf) / 2, cy + 18), small, font=sf, fill=(255, 255, 255, 255))


def _hero_bg(art, accent):
    """Listing background made from the planner's own cover art: soft focus, light veil, dark vignette."""
    a = art.convert("RGB")
    sc = max(MW / a.width, MH / a.height)
    a = a.resize((int(a.width * sc) + 1, int(a.height * sc) + 1), Image.LANCZOS)
    l, t = (a.width - MW) // 2, (a.height - MH) // 2
    a = a.crop((l, t, l + MW, t + MH)).filter(ImageFilter.GaussianBlur(7)).convert("RGBA")
    cream = tuple(int(c * 0.10 + 248 * 0.90) for c in accent)
    veil = Image.new("RGBA", (MW, MH), cream + (0,))
    d = ImageDraw.Draw(veil)
    for y in range(MH):  # strong veil at the top (title), lighter in the middle, stronger again at the bottom
        t = y / MH
        a_ = 215 if t < 0.17 else int(215 - (t - 0.17) * 300) if t < 0.45 else int(131 + (t - 0.45) * 120)
        d.line((0, y, MW, y), fill=cream + (max(90, min(225, a_)),))
    a.alpha_composite(veil)
    return a


def _pill_badge(c, cx, cy, big, small, accent, r=124):
    """White round badge with an accent ring: one calm color family instead of a rainbow."""
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((cx - r, cy - r + 14, cx + r, cy + r + 14), fill=(0, 0, 0, 80))
    c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
    d = ImageDraw.Draw(c)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    d.ellipse((cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12), outline=accent + (255,), width=5)
    bf = fit_text(d, big, "sans_bold", r * 1.28, 74, 34)
    bb = d.textbbox((0, 0), big, font=bf)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - 22 - (bb[3] - bb[1]) - bb[1] + 8), big, font=bf, fill=accent + (255,))
    sf = fit_text(d, small, "sans_bold", r * 1.4, 27, 16)
    d.text((cx - d.textlength(small, font=sf) / 2, cy + 22), small, font=sf, fill=INK + (255,))


def _cover_mock(front, backs, accent, badges, art=None):
    """First listing photo: the planner's own art as a soft backdrop, three tablets, calm white badges.
    Everything important sits inside Etsy's centre-square crop (x 300-2100)."""
    if art is None:  # take the art from the rendered cover page
        art = front.crop((0, int(front.height * 0.1), int(front.width * 0.94), front.height))
    dark = tuple(int(v * 0.55) for v in accent)
    c = _hero_bg(art, accent)
    d = ImageDraw.Draw(c)
    tt = "Digital Planner"
    hf = font("serif", 150)
    try:
        hf.set_variation_by_name("SemiBold")
    except Exception:
        pass
    d.text((MW / 2 - d.textlength(tt, font=hf) / 2, 30), tt, font=hf, fill=INK + (255,))
    sub = "UNDATED   •   HYPERLINKED   •   iPad & ANDROID"
    sf = fit_text(d, sub, "sans_bold", 1300, 38, 22)
    sw = d.textlength(sub, font=sf)
    d.text((MW / 2 - sw / 2, 246), sub, font=sf, fill=dark + (255,))
    d.line((MW / 2 - sw / 2 - 90, 270, MW / 2 - sw / 2 - 30, 270), fill=accent + (255,), width=4)
    d.line((MW / 2 + sw / 2 + 30, 270, MW / 2 + sw / 2 + 90, 270), fill=accent + (255,), width=4)
    for k, pg in enumerate(backs[:2]):
        t = _tablet(pg, 860).rotate((6, -6)[k], expand=True, resample=Image.BICUBIC)
        paste_with_shadow(c, t, ((420, MW - 420 - t.width)[k], 360), radius=26, offset=(0, 18), opacity=110)
    t = _tablet(front, 1200)
    fx, fy = (MW - t.width) // 2, 590
    paste_with_shadow(c, t, (fx, fy), radius=36, offset=(0, 28), opacity=150)
    spots = [(470, 470), (1930, 470), (440, 1150), (1960, 1150)]
    for k, ((big, small), (x, y)) in enumerate(zip(badges, spots)):
        _pill_badge(c, min(max(x, 440), MW - 440), y, big, small, dark if k % 2 else accent)
    if len(badges) > 4:  # the fifth one as a ribbon under the tablet, so it never hides the screen
        text = f"{badges[4][0]} {badges[4][1]}   •   INSTANT DOWNLOAD"
        d = ImageDraw.Draw(c)
        rf = fit_text(d, text, "sans_bold", 1100, 40, 24)
        rw = d.textlength(text, font=rf) + 120
        y0 = fy + t.height + 40
        sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((MW / 2 - rw / 2, y0 + 10, MW / 2 + rw / 2, y0 + 100), 45, fill=(0, 0, 0, 70))
        c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
        d = ImageDraw.Draw(c)
        d.rounded_rectangle((MW / 2 - rw / 2, y0, MW / 2 + rw / 2, y0 + 90), 45, fill=accent + (255,))
        bb = d.textbbox((0, 0), text, font=rf)
        d.text((MW / 2 - (bb[2] - bb[0]) / 2 - bb[0], y0 + 45 - (bb[3] - bb[1]) / 2 - bb[1]), text, font=rf, fill=(255, 255, 255, 255))
    return c.convert("RGB")


def boho_art(palette, w=1536, h=1152, seed=5):
    """Calm neutral-boho cover art drawn with Pillow (no quota, never an animal): cream paper, soft arches,
    a half sun, rounded hills and a few leaf sprigs in muted tones of the palette."""
    rnd = random.Random(seed)
    mute = lambda c, t: tuple(int(v * (1 - t) + 236 * t) for v in c)
    cols = [mute(c, 0.45) for c in palette] + [(214, 190, 168), (196, 160, 136), (226, 210, 190), (182, 168, 146)]
    im = Image.new("RGBA", (w, h), (246, 240, 232, 255))
    d = ImageDraw.Draw(im)
    # nested rainbow arches, left
    cx, base = int(w * 0.26), int(h * 0.78)
    for k, r in enumerate((420, 340, 260, 180)):
        d.pieslice((cx - r, base - r, cx + r, base + r), 180, 360, fill=cols[k % len(cols)] + (255,))
    d.rectangle((0, base, w, h), fill=(246, 240, 232, 255))
    # half sun, right
    sx, sy, sr = int(w * 0.74), int(h * 0.42), 170
    d.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=cols[4 % len(cols)] + (255,))
    # rolling hills at the bottom
    for k in range(3):
        y0 = int(h * (0.70 + k * 0.08))
        pts = [(0, h)]
        for x in range(0, w + 40, 40):
            pts.append((x, y0 + int(40 * __import__("math").sin(x / (190 + 60 * k) + k * 1.7))))
        pts.append((w, h))
        d.polygon(pts, fill=cols[(k + 1) % len(cols)] + (255,))
    # leaf sprigs
    for _ in range(3):
        lx, ly = rnd.randrange(int(w * 0.55), w - 120), rnd.randrange(int(h * 0.62), int(h * 0.8))
        col = mute(cols[rnd.randrange(len(cols))], 0.15)
        d.line((lx, ly, lx + 30, ly - 210), fill=col + (255,), width=6)
        for j in range(5):
            yy = ly - 40 - j * 34
            xx = lx + 6 + j * 5
            d.ellipse((xx - 46, yy - 12, xx - 2, yy + 12), fill=col + (255,))
            d.ellipse((xx + 2, yy - 20, xx + 46, yy + 4), fill=col + (255,))
    # paper grain
    noise = Image.effect_noise((w, h), 18).convert("L").point(lambda v: int(v * 0.12))
    grain = Image.new("RGBA", (w, h), (90, 70, 50, 0))
    grain.putalpha(noise)
    im.alpha_composite(grain)
    return im.convert("RGB")


def pick_edition_look(spec, slug=""):
    """Edition from the product's own words (title / niche), else the least used one; look = least used so far."""
    import zlib
    text = " ".join(str(spec.get(k, "")) for k in ("edition", "title", "planner_name", "niche"))
    ed = spec.get("edition") if spec.get("edition") in planner_pdf.EDITIONS else planner_pdf.edition_of(text)
    used_ed, used_look = {}, {}
    try:
        from .. import storage
        for p in storage.all_products():
            if p.get("type") == "planner":
                sp = p.get("spec", {})
                used_ed[sp.get("edition", "life")] = used_ed.get(sp.get("edition", "life"), 0) + 1
                if sp.get("look"):
                    used_look[sp["look"]] = used_look.get(sp["look"], 0) + 1
    except Exception:
        pass
    h = zlib.crc32(slug.encode())
    look = spec.get("look") if spec.get("look") in planner_pdf.LOOKS else \
        min(planner_pdf.LOOKS, key=lambda l: (used_look.get(l, 0), (zlib.crc32(l.encode()) ^ h) & 255))
    return ed, look


NOTES = {  # handwritten sticky-note words per edition (shown on the listing collage only)
    "life": [("Pay rent", "call mom!"), ("Yoga 7am", "drink water"), ("Dinner w/ Anna", "8 pm")],
    "budget": [("Save $50", "this week"), ("No spend", "weekend!"), ("Bills due", "the 15th")],
    "student": [("Essay due", "Friday!"), ("Study group", "4 pm"), ("Exam prep", "chapter 5")],
    "adhd": [("Just 3 things", "today"), ("Take meds", "8 am"), ("You got this", "one step")],
    "wellness": [("10k steps", "walk 30 min"), ("Meal prep", "Sunday"), ("Sleep by", "10:30")],
    "business": [("Ship orders", "by 3 pm"), ("Post reel", "tonight"), ("Invoice", "client B")],
    "migraine": [("Drink water", "every hour"), ("Neuro appt", "Tue 10 am"), ("Dark room", "+ ice pack")],
}


def _note_sticker(note_img, lines, ink):
    """A sticky note with two handwritten lines on it."""
    from .. import display_fonts as DF
    n = note_img.copy()
    d = ImageDraw.Draw(n)
    f = DF.get("hand", int(n.width * 0.13))
    y = n.height * 0.30
    for ln in lines:
        d.text((n.width * 0.14, y), ln, font=f, fill=ink + (255,))
        y += f.size * 1.15
    return n


def decorate_page(page, pools, ed, rnd, ink):
    """A planner page dressed like the best sellers' previews: washi tape, labels, a handwritten sticky note,
    icons and a date circle, all from the product's own stickers."""
    pg = page.convert("RGBA").copy()
    w, h = pg.size

    def put(im, scale, xy, ang):
        im = im.copy()
        im.thumbnail((int(w * scale), int(h * scale * 1.4)), Image.LANCZOS)
        im = im.rotate(ang, expand=True, resample=Image.BICUBIC)
        pg.alpha_composite(im, (int(xy[0] - im.width / 2), int(xy[1] - im.height / 2)))

    if pools["washi"]:
        put(rnd.choice(pools["washi"]), 0.42, (w * 0.16, h * 0.10), rnd.uniform(-38, -28))
        put(rnd.choice(pools["washi"]), 0.36, (w * 0.86, h * 0.92), rnd.uniform(-35, -25))
    if pools["notes"]:
        note = _note_sticker(rnd.choice(pools["notes"]), rnd.choice(NOTES.get(ed, NOTES["life"])), ink)
        put(note, 0.26, (w * rnd.uniform(0.70, 0.80), h * rnd.uniform(0.55, 0.68)), rnd.uniform(-8, 8))
    for k in range(2):
        if pools["labels"]:
            put(rnd.choice(pools["labels"]), 0.22, (w * rnd.uniform(0.28, 0.55), h * (0.38 + 0.26 * k)), rnd.uniform(-6, 6))
    if pools["themed"]:
        put(rnd.choice(pools["themed"]), 0.16, (w * rnd.uniform(0.82, 0.88), h * 0.28), rnd.uniform(-10, 10))
    elif pools["icons"]:
        put(rnd.choice(pools["icons"]), 0.10, (w * 0.86, h * 0.30), rnd.uniform(-12, 12))
    if pools["dates"]:
        put(rnd.choice(pools["dates"]), 0.09, (w * 0.08, h * 0.88), 0)
    return pg.convert("RGB")


def collage_pages(pages, stickers, ed, palette):
    rnd = random.Random(11)
    pool = lambda key: [im for n, im in stickers if key in n]
    pools = {"washi": pool("washi"), "notes": [im for n, im in stickers if "note-square" in n],
             "labels": pool(f"08-{ed}-labels") or pool("04-labels"), "themed": pool("01-themed") or pool("09-pain-scale"),
             "icons": pool("10-trigger-icons") or pool("07-icons"), "dates": pool("dates")}
    ink = tuple(int(v * 0.45) for v in palette[0])
    return [decorate_page(p, pools, ed, rnd, ink) for p in pages]


def _soft_bg(accent):
    """Dreamy soft background like the best sellers: light tinted gradient + a few big blurred light shapes."""
    top = tuple(int(c * 0.10 + 246 * 0.90) for c in accent)
    bot = tuple(int(c * 0.18 + 236 * 0.82) for c in accent)
    c = Image.new("RGBA", (MW, MH))
    d = ImageDraw.Draw(c)
    for y in range(MH):
        t = y / MH
        d.line((0, y, MW, y), fill=tuple(int(a * (1 - t) + b * t) for a, b in zip(top, bot)) + (255,))
    blobs = Image.new("RGBA", (MW, MH), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    rnd = random.Random(3)
    for _ in range(7):
        x, y, r = rnd.randrange(0, MW), rnd.randrange(0, MH), rnd.randrange(250, 520)
        bd.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randrange(50, 95)))
    c.alpha_composite(blobs.filter(ImageFilter.GaussianBlur(90)))
    return c


def _center_text(d, y, text, f, fill):
    bb = d.textbbox((0, 0), text, font=f)
    d.text((MW / 2 - (bb[2] - bb[0]) / 2 - bb[0], y), text, font=f, fill=fill)


def _shadow_shape(c, box, radius, blur=18, off=14, alpha=80, ellipse=False):
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    b = (box[0], box[1] + off, box[2], box[3] + off)
    (sd.ellipse(b, fill=(0, 0, 0, alpha)) if ellipse else sd.rounded_rectangle(b, radius, fill=(0, 0, 0, alpha)))
    c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))


def _black_pill(c, x, y, text, size=54):
    d = ImageDraw.Draw(c)
    f = font("sans_bold", size)
    bb = d.textbbox((0, 0), text, font=f)
    w, h = bb[2] - bb[0] + 120, int(size * 2.05)
    _shadow_shape(c, (x, y, x + w, y + h), h // 2, blur=14, off=10, alpha=70)
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((x, y, x + w, y + h), h // 2, fill=(20, 20, 22, 255))
    d.text((x + 60 - bb[0], y + (h - (bb[3] - bb[1])) / 2 - bb[1]), text, font=f, fill=(255, 255, 255, 255))
    return w, h


def _burst(c, cx, cy, r, lines):
    import math
    pts = []
    n = 18
    for k in range(n * 2):
        rr = r if k % 2 == 0 else r * 0.86
        a = math.pi * k / n
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon([(x, y + 12) for x, y in pts], fill=(0, 0, 0, 80))
    c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(c)
    d.polygon(pts, fill=(20, 20, 22, 255))
    w = (255, 255, 255, 255)  # download icon
    d.line((cx, cy - r * 0.62, cx, cy - r * 0.30), fill=w, width=7)
    d.line((cx - 20, cy - r * 0.42, cx, cy - r * 0.28, cx + 20, cy - r * 0.42), fill=w, width=7, joint="curve")
    d.line((cx - 34, cy - r * 0.30, cx - 34, cy - r * 0.20, cx + 34, cy - r * 0.20, cx + 34, cy - r * 0.30), fill=w, width=6)
    f = font("sans_bold", int(r * 0.24))
    for k, ln in enumerate(lines):
        bb = d.textbbox((0, 0), ln, font=f)
        d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - r * 0.08 + k * r * 0.30), ln, font=f, fill=w)


def _stylus(c, x1, y1, x2, y2):
    import math
    L = int(math.hypot(x2 - x1, y2 - y1))
    st = Image.new("RGBA", (L, 44), (0, 0, 0, 0))
    sd = ImageDraw.Draw(st)
    sd.rounded_rectangle((70, 4, L - 1, 40), 18, fill=(252, 252, 252, 255), outline=(210, 210, 214, 255), width=2)
    sd.polygon([(72, 6), (72, 38), (4, 22)], fill=(238, 238, 240, 255))
    sd.polygon([(20, 17), (20, 27), (2, 22)], fill=(80, 80, 85, 255))
    sd.rectangle((L - 60, 4, L - 54, 40), fill=(225, 225, 228, 255))
    ang = math.degrees(math.atan2(-(y2 - y1), x2 - x1))
    st = st.rotate(ang + 180, expand=True, resample=Image.BICUBIC)
    sh = Image.new("RGBA", st.size, (0, 0, 0, 0))
    sh.putalpha(st.split()[-1].point(lambda v: v * 70 // 255))
    c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (int(min(x1, x2)) + 14, int(min(y1, y2)) + 22))
    c.alpha_composite(st, (int(min(x1, x2)), int(min(y1, y2))))


def hero_mock(art, daily, name, accent, swatches, info, ed=None):
    """First listing photo in the best-seller layout: small black pill, big elegant title, a tablet opened like a book
    (cover art on the left, a real daily page on the right), theme color dots, black call-outs, an INSTANT DOWNLOAD
    burst and a feature strip. All key parts stay inside Etsy's centre-square crop (x 300-2100)."""
    c = _soft_bg(accent)
    d = ImageDraw.Draw(c)
    # top pill
    pf = font("sans_medium", 40)
    ed = ed or planner_pdf.EDITIONS["life"]
    pt = ed["pill"]
    pw = d.textlength(pt, font=pf) + 90
    d.rounded_rectangle((MW / 2 - pw / 2, 52, MW / 2 + pw / 2, 132), 40, fill=(20, 20, 22, 255))
    _center_text(d, 62, pt, pf, (255, 255, 255, 255))
    # title
    tf = font("serif", 220)
    try:
        tf.set_variation_by_name("Medium")
    except Exception:
        pass
    tt = ed["heading"]
    while d.textlength(tt, font=tf) > 1760 and tf.size > 120:
        tf = tf.font_variant(size=tf.size - 6)
    _center_text(d, 140, tt, tf, (24, 22, 22, 255))
    sub = f"undated {ed['word']} planner  |  {info['pages']} hyperlinked pages  |  for iPad & Android"
    sf = fit_text(d, sub, "sans_light", 1760, 54, 30)
    _center_text(d, 400, sub, sf, (40, 38, 38, 255))
    # tablet opened like a book
    sh_ = 860
    wl = int(sh_ * 0.62)
    dpage = daily.convert("RGB")
    wr = int(dpage.width * sh_ / dpage.height)
    gap, bez = 16, 30
    W_, H_ = wl + gap + wr + 2 * bez, sh_ + 2 * bez
    tx, ty = (MW - W_) // 2, 515
    _shadow_shape(c, (tx, ty, tx + W_, ty + H_), 60, blur=30, off=26, alpha=110)
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((tx, ty, tx + W_, ty + H_), 60, fill=(22, 22, 25, 255))
    d.rounded_rectangle((tx + 3, ty + 3, tx + W_ - 3, ty + H_ - 3), 58, outline=(70, 70, 76, 255), width=3)
    # left: the cover
    a = art.convert("RGB")
    s_ = max(wl / a.width, sh_ / a.height)
    a = a.resize((int(a.width * s_) + 1, int(a.height * s_) + 1), Image.LANCZOS)
    l = (a.width - wl) // 2
    a = a.crop((l, 0, l + wl, sh_)).convert("RGBA")
    ad = ImageDraw.Draw(a)
    lab_w, lab_h = wl - 90, 190
    lx, ly = 45, int(sh_ * 0.40)
    veil = Image.new("RGBA", a.size, (0, 0, 0, 0))
    ImageDraw.Draw(veil).rounded_rectangle((lx, ly, lx + lab_w, ly + lab_h), 18, fill=(255, 253, 250, 225))
    a.alpha_composite(veil)
    ad = ImageDraw.Draw(a)
    nf = fit_text(ad, name.upper(), "sans_medium", lab_w - 60, 30, 16)
    ad.text((wl / 2 - ad.textlength(name.upper(), font=nf) / 2, ly + 28), name.upper(), font=nf, fill=accent + (255,))
    pf2 = font("serif", 76)
    ad.text((wl / 2 - ad.textlength("PLANNER", font=pf2) / 2, ly + 72), "PLANNER", font=pf2, fill=(60, 52, 48, 255))
    for x in range(26):  # spine shadow
        ad.line((wl - 1 - x, 0, wl - 1 - x, sh_), fill=(0, 0, 0, int(60 * (1 - x / 26))))
    c.paste(a.convert("RGB"), (tx + bez, ty + bez))
    # right: a real daily page
    c.paste(dpage.resize((wr, sh_), Image.LANCZOS), (tx + bez + wl + gap, ty + bez))
    # theme color dots on the left edge
    r = 46
    for k, col in enumerate(swatches[:6]):
        cx, cy = tx + 4, ty + 95 + k * 104
        _shadow_shape(c, (cx - r, cy - r, cx + r, cy + r), 0, blur=10, off=8, alpha=70, ellipse=True)
        d = ImageDraw.Draw(c)
        soft = tuple(int(v * 0.55 + 255 * 0.45) for v in col) if sum(col) > 200 else col
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=soft + (255,), outline=(255, 255, 255, 255), width=7)
    # black call-outs
    _black_pill(c, 310, ty + H_ - 250, f"{info['templates']}+ EXTRA TEMPLATES")
    _black_pill(c, 340, ty + H_ - 120, "MONDAY & SUNDAY START" if info.get("monday") else "LIGHT & DARK MODE")
    _burst(c, tx + W_ - 140, ty + 190, 150, ["INSTANT", "DOWNLOAD"])
    _stylus(c, tx + W_ - 520, ty + H_ - 60, tx + W_ + 40, ty + H_ - 330)
    # feature strip
    by = MH - 215
    strip = Image.new("RGBA", (MW, 150), (255, 255, 255, 120))
    c.alpha_composite(strip, (0, by))
    d = ImageDraw.Draw(c)
    ft = (f"{info['themes']} color themes  •  {info['stickers']}+ stickers  •  {info['covers']}+ covers  •  "
          f"{info['notebooks']} notebooks included")
    ff = fit_text(d, ft, "sans", 1760, 62, 30)
    bb = d.textbbox((0, 0), ft, font=ff)
    _center_text(d, by + 75 - (bb[3] - bb[1]) / 2 - bb[1], ft, ff, (30, 28, 28, 255))
    return c.convert("RGB")


def _grid_mock(pages, heading, sub, accent, cols=2):
    c = _bg(accent)
    _title(c, heading, sub, accent)
    if len(pages) == 2:  # two big tablets, slightly overlapping
        for k, pg in enumerate(pages):
            t = _tablet(pg, 1150).rotate((3, -3)[k], expand=True, resample=Image.BICUBIC)
            paste_with_shadow(c, t, ((160, MW - 160 - t.width)[k], (290, 780)[k]), radius=22, offset=(0, 16), opacity=120)
        return c.convert("RGB")
    rows = (len(pages) + cols - 1) // cols
    tw = {1: 1500, 2: 820, 3: 520}[cols]
    for k, pg in enumerate(pages):
        t = _tablet(pg, tw)
        cw = (MW - 400) / cols
        x = 200 + (k % cols) * cw + (cw - t.width) / 2
        y = 300 + (k // cols) * ((MH - 340) / rows)
        paste_with_shadow(c, t, (x, y), radius=18, offset=(0, 12), opacity=110)
    return c.convert("RGB")


def _features_mock(accent, items, page):
    c = _bg(accent)
    _title(c, "EVERYTHING IN ONE PLANNER", "", accent, y=70)
    t = _tablet(page, 900)
    paste_with_shadow(c, t, (MW - t.width - 150, 300), radius=22, offset=(0, 16), opacity=110)
    d = ImageDraw.Draw(c)
    f = font("sans", 40)
    for k, line in enumerate(items):
        y = 270 + k * 128
        d.ellipse((150, y + 6, 194, y + 50), fill=accent + (255,))
        d.line((161, y + 29, 170, y + 38, 184, y + 18), fill=(255, 255, 255, 255), width=6)
        d.text((220, y), line, font=f, fill=INK + (255,))
    return c.convert("RGB")


def _themes_mock(pages, names, accent):
    c = _bg(accent)
    _title(c, "6 COLOR THEMES", "light & dark mode  •  Sunday & Monday start", accent)
    for k, (pg, name) in enumerate(zip(pages, names)):
        t = _tablet(pg, 560)
        x = 230 + (k % 3) * 660
        y = 330 + (k // 3) * 640
        paste_with_shadow(c, t, (x, y), radius=16, offset=(0, 10), opacity=100)
        d = ImageDraw.Draw(c)
        f = font("sans_bold", 40)
        d.text((x + t.width / 2 - d.textlength(name.upper(), font=f) / 2, y + t.height + 22), name.upper(), font=f, fill=INK + (255,))
    return c.convert("RGB")


def _extras_mock(stickers, covers, accent, n_st, n_cov):
    c = _bg(accent)
    _title(c, f"{n_st}+ STICKERS & {n_cov}+ COVERS", "washi tapes • sticky notes • labels • dates • icons • themed art", accent)
    for k, cv in enumerate(covers[:6]):
        im = cv.copy()
        im.thumbnail((420, 320))
        x = 200 + (k % 3) * 460
        y = 320 + (k // 3) * 360
        paste_with_shadow(c, im.convert("RGBA"), (x, y), radius=12, offset=(0, 8), opacity=90)
    picks = [s for n, s in stickers if "themed" in n][:3] + [s for n, s in stickers if "labels" in n][::97][:4] + \
            [s for n, s in stickers if "washi" in n][::9][:2] + [s for n, s in stickers if "dates" in n][10:16:2]
    x, y, rowh = 200, 1080, 0
    for s in picks:
        s = s.copy()
        s.thumbnail((330, 190), Image.LANCZOS)
        if x + s.width > MW - 200:
            x, y, rowh = 200, y + rowh + 30, 0
        if y + s.height > MH - 40:
            break
        c.alpha_composite(s, (int(x), int(y)))
        x += s.width + 34
        rowh = max(rowh, s.height)
    return c.convert("RGB")


def _covers(art, objs, title, colors, n=54):
    """Pillow-made cover options (+ the AI cover): solid, gradient, stripes, dots, scattered stickers, framed."""
    out = []
    w, h = 1366, 1024
    rnd = random.Random(7)
    styles = ["art", "solid", "gradient", "stripes", "dots", "scatter", "frame", "split", "arch"]
    k = 0
    while len(out) < n:
        st = styles[k % len(styles)]
        col = colors[(k // len(styles) + k) % len(colors)]
        soft = tuple(int(v * 0.35 + 255 * 0.65) for v in col)
        if st == "art":
            bg = art.convert("RGB").resize((w, h), Image.LANCZOS).convert("RGBA")
            if k:
                tint = Image.new("RGBA", (w, h), col + (70,))
                bg.alpha_composite(tint)
        else:
            bg = Image.new("RGBA", (w, h), soft + (255,))
            d = ImageDraw.Draw(bg)
            if st == "gradient":
                for y in range(h):
                    t = y / h
                    d.line((0, y, w, y), fill=tuple(int(a * (1 - t) + b * t) for a, b in zip(soft, col)) + (255,))
            elif st == "stripes":
                for x in range(0, w, 80):
                    d.rectangle((x, 0, x + 30, h), fill=col + (90,))
            elif st == "dots":
                for y in range(30, h, 70):
                    for x in range(30 + (y // 70 % 2) * 35, w, 70):
                        d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=col + (120,))
            elif st == "scatter" and objs:
                for _ in range(14):
                    o = objs[rnd.randrange(len(objs))].copy()
                    o.thumbnail((180, 180))
                    o = o.rotate(rnd.uniform(-25, 25), expand=True)
                    bg.alpha_composite(o, (rnd.randrange(0, w - o.width), rnd.randrange(0, h - o.height)))
            elif st == "frame":
                d.rectangle((40, 40, w - 40, h - 40), outline=col + (255,), width=10)
                d.rectangle((70, 70, w - 70, h - 70), outline=col + (160,), width=3)
            elif st == "split":
                d.rectangle((0, 0, w * 0.38, h), fill=col + (255,))
            elif st == "arch":
                d.rounded_rectangle((w * 0.28, h * 0.15, w * 0.72, h * 1.1), radius=int(w * 0.22), fill=col + (110,))
        d = ImageDraw.Draw(bg)
        pw, ph = 760, 260
        d.rounded_rectangle(((w - pw) / 2, (h - ph) / 2, (w + pw) / 2, (h + ph) / 2), 30, fill=(255, 255, 255, 235))
        f = fit_text(d, title, "serif", pw - 80, 76, 40)
        d.text((w / 2 - d.textlength(title, font=f) / 2, h / 2 - 60), title, font=f, fill=INK + (255,))
        sf = font("sans_bold", 28)
        sub = "DIGITAL PLANNER"
        d.text((w / 2 - d.textlength(sub, font=sf) / 2, h / 2 + 40), sub, font=sf, fill=col + (255,))
        out.append(bg.convert("RGB"))
        k += 1
    return out


def build(spec, slug):
    palette = [hex2rgb(x) for x in spec.get("palette", [])][:4] or [(196, 140, 50), (110, 140, 90), (170, 90, 70)]
    style = spec.get("style", "")
    cover = images.generate(f"{spec['cover']['prompt']}, {style}, {COVER_SUFFIX}", 1536, 1152).convert("RGB")
    objs = []
    for s in spec["stickers"][:8]:
        im = images.try_generate(f"{s['prompt']}, {style}, {OBJECT_SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is not None:
            objs.append(trim_alpha(color_to_alpha_background(im)))
    images.need(len(objs), 8, ratio=0.75)
    return assemble(spec, slug, cover, objs)


def assemble(spec, slug, cover, objs, palette=None):
    """Everything after the AI art: PDFs, stickers, covers, zips and the 10 listing photos.
    Also used by /kapak to rebuild an old planner from its own art (no image quota)."""
    palette = palette or [hex2rgb(x) for x in spec.get("palette", [])][:4] or [(196, 140, 50), (110, 140, 90), (170, 90, 70)]
    name = spec.get("planner_name", "Digital Planner")
    title = f"{name} Planner" if "planner" not in name.lower() else name
    edition, look = pick_edition_look(spec, slug)
    spec["edition"], spec["look"] = edition, look
    ed = planner_pdf.EDITIONS[edition]
    showcase = [t[0] for t in ed["extra"][:4]] or ["smart", "budgetyear", "workout", "mood"]

    # 6 color themes: the product's own palette (light + dark) and 4 presets
    themes = [("Signature", palette, False), ("Dark", palette, True)] + [(n, THEMES[n], False) for n in ("Sage", "Blush", "Ocean", "Lavender")]
    pdfs, previews, n_pages, main = [], {}, 0, None
    for tname, pal, dark in themes:
        starts = ("sun", "mon") if tname in ("Signature", "Dark") else ("sun",)
        for start in starts:
            p = planner_pdf.Planner(title, list(pal), cover, objs, start, dark, edition, look)
            data = p.build()
            n_pages = p.pages
            pdfs.append((f"{slug}-{tname.lower()}-{'sunday' if start == 'sun' else 'monday'}-start.pdf", data))
            if start == "sun":
                keys = list(dict.fromkeys(["cover", "index", "guide", "m0", "m0g", "m0w0", "m0w0s", "m0w0d0", "m0h", "m0b",
                                           "notes", "nb0p1"] + showcase))
                previews[tname] = dict(zip(keys, planner_pdf.render_pages(data, [p.order.index(k) for k in keys], 1400)))
                if tname == "Signature":
                    main = p
    n_tpl = len(main.templates)
    all_colors = list(palette) + [c for v in THEMES.values() for c in v]
    stickers = planner_stickers.make_all(all_colors[:12], [E.sticker(o) for o in objs], edition=edition)
    covers = _covers(cover, objs, title, all_colors)
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n"
              f"PLANNER: undated, {n_pages} hyperlinked pages, landscape 4:3 PDF for iPad and Android tablets.\n"
              "COLOR THEMES: Signature, Dark, Sage, Blush, Ocean, Lavender (Sunday start). "
              "Signature and Dark also come with Monday start.\n"
              f"STICKERS: {len(stickers)} transparent PNG stickers (washi tapes, sticky notes, labels, dates, days & months, "
              "icons, themed art).\n"
              f"COVERS: {len(covers)} cover images to replace the first page.\n\n"
              "HOW TO USE: open the PDF on your tablet in any PDF note-taking app. Read the 'How to use' page right after "
              "the index. Tap the top tabs (Home, Year, Goals, Health, Finance, Life, Notes) and the month tabs on the right "
              "to jump around. Add stickers by importing the PNG files into your app's sticker or image library.\n\n"
              "For personal use only. Please do not share or resell the files.\n")
    files = pdfs + [(f"stickers/{n}", png_bytes(im)) for n, im in stickers] + \
        [(f"covers/cover-{k + 1:02d}.jpg", jpeg_bytes(cv, 84)) for k, cv in enumerate(covers)]
    try:
        delivery = make_zips(slug, files, readme, max_zips=5)  # Etsy allows 5 files of 20 MB
    except ValueError:
        files = [f for f in files if "monday" not in f[0]]  # too big: keep Sunday start only
        delivery = make_zips(slug, files, readme.replace("Signature and Dark also come with Monday start.", ""), max_zips=5)

    sig, dk = previews["Signature"], previews["Dark"]
    accent = palette[0]
    n_st, n_cov = len(stickers) // 100 * 100, len(covers) // 10 * 10
    feats = ([f"{ed['word'].capitalize()} edition: {', '.join(t[1].lower() for t in ed['extra'][:3])}"] if ed["extra"] else []) + [
             f"{n_pages} hyperlinked pages, undated", "6 color themes incl. dark mode", "Sunday & Monday start",
             "12 months, 60 weeks, 420 daily pages", f"{n_tpl} templates: goals, health, money, life",
             "12 custom notebooks + 8 note papers", f"{n_st}+ stickers & {n_cov}+ covers", "How-to page + index on every tab"][:8]
    mock = [
        ("00-bundle.jpg", bundle_cover(
            collage_pages([sig[k] for k in ("m0w0d0", "m0", "m0w0", "m0g", "m0h", "m0b", "index", "m0w0s", "notes", "guide")] +
                          [sig[k] for k in showcase] + [dk["m0w0d0"], previews["Blush"]["m0"], previews["Ocean"]["m0w0d0"]],
                          stickers, edition, palette) + covers[:3], n_pages, "LINKED PAGES", name,
            ["#%02x%02x%02x" % c for c in palette], bundle_word=ed["heading"], ribbon="UNDATED",
            sticker=("6", "COLOR", "THEMES"),
            features=[f"{n_tpl}+ TEMPLATES", f"{n_st}+ STICKERS", "iPAD & ANDROID"])),
        ("01-cover.jpg", hero_mock(cover, sig["m0w0d0"], name, accent,
                                   [palette[0], (52, 54, 60)] + [THEMES[t][0] for t in ("Sage", "Blush", "Ocean", "Lavender")],
                                   {"pages": n_pages, "templates": n_tpl, "stickers": n_st, "covers": n_cov,
                                    "notebooks": planner_pdf.NOTEBOOKS, "themes": 6,
                                    "monday": any("monday" in f[0] for f in files)}, ed)),
        ("02-features.jpg", _features_mock(accent, feats, sig["index"])),
        ("03-navigation.jpg", _grid_mock([sig["index"], sig["guide"]], "EASY NAVIGATION", "index, top tabs, month tabs and arrows on every page", accent)),
        ("04-monthly.jpg", _grid_mock([sig["m0"], sig["m0g"], sig["m0h"], sig["m0b"]], "MONTHLY PAGES", "calendar • at a glance • habits & mood • budget", accent)),
        ("05-weekly.jpg", _grid_mock([sig["m0w0"], sig["m0w0s"]], "WEEKLY LAYOUTS", "weekly overview + hourly schedule • Sunday & Monday start", accent)),
        ("06-daily.jpg", _grid_mock([sig["m0w0d0"], dk["m0w0d0"]], "DAILY PAGES", "420 linked daily pages • light & dark", accent)),
        ("07-templates.jpg", _grid_mock([sig[k] for k in showcase],
                                        f"{len(ed['extra'])} {ed['word'].upper()} PAGES + {n_tpl - len(ed['extra'])} TEMPLATES" if ed["extra"] else f"{n_tpl} BONUS TEMPLATES",
                                        " • ".join(t[1].lower() for t in ed["extra"][:4]) if ed["extra"] else "goals • health • finance • life", accent)),
        ("08-themes.jpg", _themes_mock([previews[t]["m0"] for t in ("Signature", "Dark", "Sage", "Blush", "Ocean", "Lavender")],
                                       ["Signature", "Dark", "Sage", "Blush", "Ocean", "Lavender"], accent)),
        ("10-extras.jpg", _extras_mock(stickers, covers, accent, n_st, n_cov)),
    ]
    return {
        "delivery": delivery,
        "mockups": [(n, jpeg_bytes(im, 86, dpi=72)) for n, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [
            f"Undated {ed['word']} digital planner, {n_pages} hyperlinked pages (landscape PDF)",
            *([f"{ed['word'].capitalize()} pages: " + ", ".join(t[1] for t in ed["extra"]) + ", plus a " + ed["word"] + " daily page"] if ed["extra"] else []),
            "6 color themes: Signature, Dark, Sage, Blush, Ocean, Lavender (Sunday and Monday start)",
            "Year at a glance, quarterly plans, 12 monthly calendars, month at a glance, 60 weekly + 60 hourly schedule pages, 420 daily pages",
            "Every month: habit & mood tracker, budget, reflection",
            f"{n_tpl} templates: goals, SMART goals, priority matrix, fitness, meals, sleep, budget, savings, debt, investments, reading, travel, gifts and more",
            "12 custom notebooks and 8 note papers (lined, dotted, grid, blank, Cornell, music)",
            f"{len(stickers)} digital stickers (PNG) and {len(covers)} covers",
        ],
        "details": ["Landscape 4:3 for iPad and Android tablets", "Clickable top tabs, month tabs, index and previous/next arrows",
                    "Works in any PDF note-taking app"] + ([ed["note"]] if ed.get("note") else []),
        "usage": ["Open in a PDF note-taking app and write with your stylus",
                  "Undated: start any month and reuse it every year"],
        "license": "For personal use only. Please do not share, resell or redistribute the files.",
        "taxonomy": ["Calendars & Planners", "Planner Templates", "Digital Prints"],
        "count": n_pages,
        "cover_unit": "LINKED PAGES",
        "cover_kicker": ed["heading"] if edition != "life" else "Undated Digital Planner",
        "cover_items": collage_pages([sig["m0w0d0"]] + [sig[k] for k in showcase[:3]] + [sig["m0"], dk["m0w0d0"]] +
                                     [previews["Blush"]["m0w0d0"], sig["index"]], stickers, edition, palette),
        "cover_features": ([ed["extra"][0][1], ed["extra"][1][1]] if ed["extra"] else ["Hyperlinked tabs", "Light & dark mode"])
                          + [f"{n_st}+ stickers", "iPad & Android"],
        "taxonomy_fallback_id": 2078,
        "is_supply": False,
        "skip_attributes": ["room", "home style"],
    }
