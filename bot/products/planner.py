"""Undated hyperlinked digital LIFE planner (iPad / Android tablets, landscape PDF).

Benchmarked against the best sellers (BrighterPlans: 94k sales; 720 pages, 6 themes, 80+ templates,
50+ covers, 1000+ stickers). We ship: 750+ pages, 6 color themes (5 light + dark), Sunday and Monday
start, 80 templates, 12 notebooks, 50+ covers and 1000+ stickers, plus a how-to page.
AI makes only the art (1 cover + 8 themed stickers); every text is drawn by us, so no spelling mistakes."""
import random

from PIL import Image, ImageDraw, ImageFilter

from .. import ephemera as E
from .. import images, planner_pdf, planner_stickers
from ..imgutil import color_to_alpha_background, fit_text, font, hex2rgb, jpeg_bytes, make_zips, png_bytes, \
    paste_with_shadow, thumb_b64, trim_alpha
from ..mockups import H as MH, W as MW

LABEL_TR = "Dijital yaşam planlayıcısı (750+ linkli sayfa, 6 renk teması, 80 şablon, 1000+ sticker, 50+ kapak)"
SPEC_FIELDS = """
  "planner_name": "short planner name, 2-4 words, about the theme (e.g. 'Honey Bee Garden')",
  "cover": {"prompt": "English prompt for ONE beautiful horizontal cover illustration for the theme, calm area in the center, no text"},
  "stickers": [ exactly 8 objects {"name": "short name", "prompt": "English prompt for ONE single isolated object that fits the theme (sticker), no text"} ]
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


def _cover_mock(front, backs, accent, n_pages, n_tpl, n_cov, n_st):
    """First listing photo, like the best sellers: stacked tablets + big feature badges, all inside the centre square."""
    c = _bg(accent)
    _title(c, "DIGITAL PLANNER", "undated  •  hyperlinked  •  iPad & Android", accent, y=50)
    for k, pg in enumerate(backs[:2]):
        t = _tablet(pg, 820).rotate((-7, 7)[k], expand=True, resample=Image.BICUBIC)
        paste_with_shadow(c, t, ((480, 1020)[k], 330 + k * 10), radius=22, offset=(0, 14), opacity=100)
    t = _tablet(front, 1080)
    paste_with_shadow(c, t, ((MW - t.width) // 2, 520), radius=30, offset=(0, 22), opacity=140)
    cols = [accent, (200, 120, 110), (110, 140, 120), (100, 130, 170), (160, 120, 170)]
    spots = [(470, 430), (1930, 430), (420, 1080), (1980, 1080), (MW // 2, 1500)]
    for (big, small), (x, y), col in zip([(f"{n_pages}+", "LINKED PAGES"), ("6", "COLOR THEMES"), (f"{n_tpl}", "TEMPLATES"),
                                           (f"{n_st}+", "STICKERS"), (f"{n_cov}+", "COVERS")], spots, cols):
        _badge(c, min(max(x, 430), MW - 430), y, big, small, col)
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
    name = spec.get("planner_name", "Digital Planner")
    title = f"{name} Planner" if "planner" not in name.lower() else name

    # 6 color themes: the product's own palette (light + dark) and 4 presets
    themes = [("Signature", palette, False), ("Dark", palette, True)] + [(n, THEMES[n], False) for n in ("Sage", "Blush", "Ocean", "Lavender")]
    pdfs, previews, n_pages, main = [], {}, 0, None
    for tname, pal, dark in themes:
        starts = ("sun", "mon") if tname in ("Signature", "Dark") else ("sun",)
        for start in starts:
            p = planner_pdf.Planner(title, list(pal), cover, objs, start, dark)
            data = p.build()
            n_pages = p.pages
            pdfs.append((f"{slug}-{tname.lower()}-{'sunday' if start == 'sun' else 'monday'}-start.pdf", data))
            if start == "sun":
                keys = ["cover", "index", "guide", "m0", "m0g", "m0w0", "m0w0s", "m0w0d0", "m0h", "m0b",
                        "smart", "budgetyear", "workout", "notes", "nb0p1", "mood"]
                previews[tname] = dict(zip(keys, planner_pdf.render_pages(data, [p.order.index(k) for k in keys], 1400)))
                if tname == "Signature":
                    main = p
    n_tpl = len(planner_pdf.TEMPLATES)
    all_colors = list(palette) + [c for v in THEMES.values() for c in v]
    stickers = planner_stickers.make_all(all_colors[:12], [E.sticker(o) for o in objs])
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
    feats = [f"{n_pages} hyperlinked pages, undated", "6 color themes incl. dark mode", "Sunday & Monday start",
             "12 months, 60 weeks, 420 daily pages", f"{n_tpl} templates: goals, health, money, life",
             "12 custom notebooks + 8 note papers", f"{n_st}+ stickers & {n_cov}+ covers", "How-to page + index on every tab"]
    mock = [
        ("01-cover.jpg", _cover_mock(sig["cover"], [previews["Sage"]["m0"], dk["m0w0d0"]], accent, n_pages // 50 * 50, n_tpl, n_cov, n_st)),
        ("02-features.jpg", _features_mock(accent, feats, sig["index"])),
        ("03-navigation.jpg", _grid_mock([sig["index"], sig["guide"]], "EASY NAVIGATION", "index, top tabs, month tabs and arrows on every page", accent)),
        ("04-monthly.jpg", _grid_mock([sig["m0"], sig["m0g"], sig["m0h"], sig["m0b"]], "MONTHLY PAGES", "calendar • at a glance • habits & mood • budget", accent)),
        ("05-weekly.jpg", _grid_mock([sig["m0w0"], sig["m0w0s"]], "WEEKLY LAYOUTS", "weekly overview + hourly schedule • Sunday & Monday start", accent)),
        ("06-daily.jpg", _grid_mock([sig["m0w0d0"], dk["m0w0d0"]], "DAILY PAGES", "420 linked daily pages • light & dark", accent)),
        ("07-templates.jpg", _grid_mock([sig["smart"], sig["budgetyear"], sig["workout"], sig["mood"]], f"{n_tpl} BONUS TEMPLATES", "goals • health • finance • life", accent)),
        ("08-themes.jpg", _themes_mock([previews[t]["m0"] for t in ("Signature", "Dark", "Sage", "Blush", "Ocean", "Lavender")],
                                       ["Signature", "Dark", "Sage", "Blush", "Ocean", "Lavender"], accent)),
        ("09-notes.jpg", _grid_mock([sig["notes"], sig["nb0p1"]], "NOTES & NOTEBOOKS", "12 custom notebooks • lined, dotted, grid, blank, Cornell, music", accent)),
        ("10-extras.jpg", _extras_mock(stickers, covers, accent, n_st, n_cov)),
    ]
    return {
        "delivery": delivery,
        "mockups": [(n, jpeg_bytes(im, 86, dpi=72)) for n, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [
            f"Undated digital planner, {n_pages} hyperlinked pages (landscape PDF)",
            "6 color themes: Signature, Dark, Sage, Blush, Ocean, Lavender (Sunday and Monday start)",
            "Year at a glance, quarterly plans, 12 monthly calendars, month at a glance, 60 weekly + 60 hourly schedule pages, 420 daily pages",
            "Every month: habit & mood tracker, budget, reflection",
            f"{n_tpl} templates: goals, SMART goals, priority matrix, fitness, meals, sleep, budget, savings, debt, investments, reading, travel, gifts and more",
            "12 custom notebooks and 8 note papers (lined, dotted, grid, blank, Cornell, music)",
            f"{len(stickers)} digital stickers (PNG) and {len(covers)} covers",
        ],
        "details": ["Landscape 4:3 for iPad and Android tablets", "Clickable top tabs, month tabs, index and previous/next arrows",
                    "Works in any PDF note-taking app"],
        "usage": ["Open in a PDF note-taking app and write with your stylus",
                  "Undated: start any month and reuse it every year"],
        "license": "For personal use only. Please do not share, resell or redistribute the files.",
        "taxonomy": ["Calendars & Planners", "Planner Templates", "Digital Prints"],
        "taxonomy_fallback_id": 2078,
        "is_supply": False,
        "skip_attributes": ["room", "home style"],
    }
