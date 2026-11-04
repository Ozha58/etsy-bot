"""Undated hyperlinked digital LIFE planner (iPad / Android, landscape PDF): 580+ pages, light + dark mode,
Sunday + Monday start, 540+ digital stickers and 6 covers. AI makes only the art (1 cover + 8 themed
stickers); all planner text is drawn by us, so there are no spelling mistakes."""
from PIL import Image, ImageDraw

from .. import ephemera as E
from .. import images, mockups, planner_pdf, planner_stickers
from ..imgutil import color_to_alpha_background, fit_text, font, hex2rgb, jpeg_bytes, make_zips, png_bytes, \
    paste_with_shadow, thumb_b64, trim_alpha
from ..mockups import H as MH, W as MW

LABEL_TR = "Dijital yaşam planlayıcısı (580+ linkli sayfa, açık/koyu mod, 540+ sticker)"
SPEC_FIELDS = """
  "planner_name": "short planner name, 2-4 words, about the theme (e.g. 'Honey Bee Garden')",
  "cover": {"prompt": "English prompt for ONE beautiful horizontal cover illustration for the theme, calm area in the center, no text"},
  "stickers": [ exactly 8 objects {"name": "short name", "prompt": "English prompt for ONE single isolated object that fits the theme (sticker), no text"} ]
"""
OBJECT_SUFFIX = ("single isolated object, centered with empty space around it, pure plain white background, "
                 "no shadow, no ground, no text, no letters, no border, no frame")
COVER_SUFFIX = "wide horizontal composition, soft calm area in the center, no text, no letters, no border, no frame"
FEATURES = ["580+ hyperlinked pages", "Light & dark mode", "Sunday & Monday start", "540+ digital stickers",
            "45+ life templates", "Daily pages for every week"]


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


def _canvas(col=(244, 240, 232)):
    return E.aged_paper(MW, MH, col, seed=11, stains=False).convert("RGBA")


def _heading(c, text, sub, accent, y=70):
    d = ImageDraw.Draw(c)
    hf = fit_text(d, text, "serif", 1700, 92, 50)
    d.text((MW / 2 - d.textlength(text, font=hf) / 2, y), text, font=hf, fill=(50, 46, 42, 255))
    if sub:
        sf = fit_text(d, sub, "sans", 1700, 42, 26)
        d.text((MW / 2 - d.textlength(sub, font=sf) / 2, y + 120), sub, font=sf, fill=accent + (255,))


def _cover_mock(light, dark, title, accent):
    c = _canvas()
    back = _tablet(dark, 1000)
    front = _tablet(light, 1150)
    paste_with_shadow(c, back.rotate(4, expand=True, resample=Image.BICUBIC), (1130, 250), radius=26, offset=(0, 18), opacity=110)
    paste_with_shadow(c, front, (300, 300), radius=30, offset=(0, 22), opacity=130)
    d = ImageDraw.Draw(c)
    # feature pills in the centre safe zone
    pf = font("sans_bold", 40)
    items = FEATURES[:3]
    y = 300 + front.height + 40
    widths = [d.textlength(t, font=pf) + 70 for t in items]
    x = (MW - (sum(widths) + 24 * (len(items) - 1))) / 2
    for t, w in zip(items, widths):
        d.rounded_rectangle((x, y, x + w, y + 76), 38, fill=accent + (255,))
        d.text((x + 35, y + 14), t, font=pf, fill=(255, 255, 255, 255))
        x += w + 24
    hf = font("sans_bold", 54)
    t = "UNDATED DIGITAL PLANNER"
    d.text((MW / 2 - d.textlength(t, font=hf) / 2, 140), t, font=hf, fill=(50, 46, 42, 255))
    return c.convert("RGB")


def _grid_mock(pages, heading, sub, accent, cols=2):
    c = _canvas()
    _heading(c, heading, sub, accent)
    rows = (len(pages) + cols - 1) // cols
    tw = 820 if cols == 2 else 540
    for k, pg in enumerate(pages):
        t = _tablet(pg, tw)
        cw = (MW - 440) / cols
        x = 220 + (k % cols) * cw + (cw - t.width) / 2
        y = 290 + (k // cols) * ((MH - 330) / rows)
        paste_with_shadow(c, t, (x, y), radius=18, offset=(0, 12), opacity=110)
    return c.convert("RGB")


def _stickers_mock(stickers, accent, count):
    c = _canvas()
    _heading(c, f"{count}+ DIGITAL STICKERS", "washi tapes • sticky notes • labels • dates • icons • themed art", accent)
    picks = [s for n, s in stickers if "themed" in n][:4] + [s for n, s in stickers if "washi" in n][:3] + \
            [s for n, s in stickers if "note-square" in n][:2] + [s for n, s in stickers if "labels" in n][::37][:4] + \
            [s for n, s in stickers if "dates" in n][6:12:2] + [s for n, s in stickers if "icons" in n][6:12:2]
    x, y, rowh = 320, 300, 0
    for s in picks:
        s = s.copy()
        s.thumbnail((360, 230), Image.LANCZOS)
        if x + s.width > MW - 320:
            x, y, rowh = 320, y + rowh + 40, 0
        if y + s.height > MH - 60:
            break
        c.alpha_composite(s, (int(x), int(y)))
        x += s.width + 40
        rowh = max(rowh, s.height)
    return c.convert("RGB")


def _features_mock(accent, n_pages, n_stickers, page):
    c = _canvas()
    _heading(c, "EVERYTHING YOU NEED", "", accent, y=90)
    d = ImageDraw.Draw(c)
    items = [f"{n_pages} hyperlinked pages", "Light mode + dark mode", "Sunday + Monday start",
             "12 months: calendar, weeks, daily pages", "Habit, mood & budget every month",
             "45+ templates: health, finance, goals, life", f"{n_stickers}+ stickers & 6 covers",
             "Undated: start any time, reuse every year"]
    f = font("sans", 46)
    for k, t in enumerate(items):
        y = 300 + k * 160
        x = 330
        d.ellipse((x, y + 8, x + 44, y + 52), fill=accent + (255,))
        d.line((x + 11, y + 31, x + 20, y + 40, x + 34, y + 20), fill=(255, 255, 255, 255), width=6)
        d.text((x + 70, y), t, font=f, fill=(50, 46, 42, 255))
    return c.convert("RGB")


def _cover_variant(art, title, col, k):
    w, h = 2048, 1536
    if k == 0:
        bg = art.convert("RGB").resize((w, h), Image.LANCZOS).convert("RGBA")
    else:
        tint = tuple(int(v * (0.6 + 0.08 * k) + 255 * (0.4 - 0.08 * k)) for v in col)
        bg = E.aged_paper(w, h, tint, seed=k, stains=False).convert("RGBA")
    d = ImageDraw.Draw(bg)
    pw, ph = 1100, 420
    d.rounded_rectangle(((w - pw) / 2, (h - ph) / 2, (w + pw) / 2, (h + ph) / 2), 40, fill=(255, 255, 255, 230))
    f = fit_text(d, title, "serif", pw - 120, 110, 60)
    d.text((w / 2 - d.textlength(title, font=f) / 2, h / 2 - 70), title, font=f, fill=col + (255,))
    sf = font("sans_bold", 40)
    t = "DIGITAL PLANNER"
    d.text((w / 2 - d.textlength(t, font=sf) / 2, h / 2 + 70), t, font=sf, fill=(90, 90, 96, 255))
    return bg.convert("RGB")


def build(spec, slug):
    palette = [hex2rgb(x) for x in spec.get("palette", [])] or [(196, 140, 50), (110, 140, 90), (170, 90, 70)]
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

    pdfs, light_pdf, dark_pdf, n_pages = [], None, None, 0
    for dark in (False, True):
        for start in ("sun", "mon"):
            p = planner_pdf.Planner(title, palette, cover, objs, start, dark)
            data = p.build()
            n_pages = p.pages
            mode = "dark" if dark else "light"
            pdfs.append((f"{slug}-{mode}-{'sunday' if start == 'sun' else 'monday'}-start.pdf", data))
            if start == "sun":
                light_pdf, dark_pdf = (data, dark_pdf) if not dark else (light_pdf, data)
    stickers = planner_stickers.make_all(palette, [E.sticker(o) for o in objs])
    covers = [(f"covers/cover-{k + 1}.jpg", jpeg_bytes(_cover_variant(cover, title, palette[k % len(palette)], k), 90))
              for k in range(6)]
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n"
              f"PLANNER: undated, {n_pages} hyperlinked pages, landscape 4:3 PDF.\n"
              "Four versions: light / dark mode, each with Sunday or Monday start. Pick the one you like.\n"
              f"STICKERS: {len(stickers)} transparent PNG stickers in folders (washi tapes, sticky notes, labels, "
              "dates, days & months, icons, themed art).\nCOVERS: 6 cover images.\n\n"
              "HOW TO USE: open the PDF on your iPad or Android tablet in any PDF note-taking app. "
              "Tap the tabs at the top (Home, Year, Goals, Health, Finance, Life, Notes) and on the right (months) "
              "to jump around. Monthly pages link to their weeks, weekly pages link to each day. "
              "Add stickers by importing the PNG files into your app's sticker / image library.\n\n"
              "For personal use only. Please do not share or resell the files.\n")
    files = pdfs + [(f"stickers/{n}", png_bytes(im)) for n, im in stickers] + covers
    delivery = make_zips(slug, files, readme)

    idx = planner_pdf.page_index
    light = planner_pdf.render_pages(light_pdf, [idx(k) for k in ("cover", "index", "m0", "m0w0", "m0w0d0", "m0h", "m0b",
                                                                  "workout", "budgetyear", "goal1")], 1400)
    dark = planner_pdf.render_pages(dark_pdf, [idx(k) for k in ("m0", "m0w0d0")], 1400)
    accent = palette[0]
    mock = [
        ("01-cover.jpg", _cover_mock(light[0], dark[0], title, accent)),
        ("02-features.jpg", _features_mock(accent, n_pages, len(stickers), light[0])),
        ("03-calendar.jpg", _grid_mock(light[2:6], "MONTHLY • WEEKLY • DAILY", "every month links to its weeks, every week to its days", accent)),
        ("04-dark.jpg", _grid_mock([light[2], dark[0], light[4], dark[1]], "LIGHT & DARK MODE", "both included", accent)),
        ("05-templates.jpg", _grid_mock([light[1], light[6], light[7], light[9]], "45+ LIFE TEMPLATES", "health • finance • goals • life • notes", accent)),
        ("06-stickers.jpg", _stickers_mock(stickers, accent, len(stickers) // 10 * 10)),
        ("07-how.jpg", mockups.how_it_works(spec.get("palette", []))),
    ]
    return {
        "delivery": delivery,
        "mockups": [(n, jpeg_bytes(im, 88, dpi=72)) for n, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [
            f"Undated digital planner, {n_pages} hyperlinked pages (PDF, landscape)",
            "4 versions: light and dark mode, Sunday and Monday start",
            "Year at a glance, 12 monthly calendars, 60 weekly pages, 420 daily pages",
            "Every month: habit & mood tracker, budget, reflection",
            "45+ templates: goals, vision board, fitness, meals, budget, savings, debt, reading, travel and more",
            f"{len(stickers)} digital stickers (PNG) and 6 covers",
        ],
        "details": ["Landscape 4:3 for iPad and Android tablets", "Clickable top and side tabs, index page and previous/next buttons"],
        "usage": ["Open in any PDF note-taking app and write with your stylus",
                  "Undated: start any month and reuse it every year"],
        "license": "For personal use only. Please do not share, resell or redistribute the files.",
        "taxonomy": ["Calendars & Planners", "Planner Templates", "Digital Prints"],
        "taxonomy_fallback_id": 2078,
        "is_supply": False,
        "skip_attributes": ["room", "home style"],
    }
