"""Topic-first listing covers, a different design for every product.

Every cover is built around ONE AI scene about the product's own subject (spec["cover_scene"], e.g. for a migraine
planner: a calm dim bedroom with lavender, a sleep mask and herbal tea) plus the real product files. There are
several layouts; the shop never repeats the layouts of its last products, so the shop grid stops looking like one
template. Output: 2000 x 2000 (square, Etsy's shop-home and desktop-search shape)."""
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import display_fonts as DF
from .imgutil import font, hex2rgb

S = 2000
LAYOUTS = ("scene_frame", "arch", "split", "flatlay", "magazine")
SCENE_SUFFIX = ("cozy lifestyle illustration, soft natural light, calm and inviting, rich detail, no people's faces "
                "in close-up, no text, no letters, no words, no logos, no watermark")
UNITS = {"planner": "PAGES", "journal": "PAGES", "stickers": "STICKERS", "clipart": "PNG CLIPART", "junk_journal": "PIECES",
         "coloring": "COLORING PAGES", "wallpaper": "WALLPAPERS", "pattern": "DIGITAL PAPERS", "wall_art": "PRINTS",
         "scenes": "ILLUSTRATIONS", "tumbler": "TUMBLER WRAPS"}


# ---------------------------------------------------------------- helpers
def _pal(palette):
    cols = [hex2rgb(c) if isinstance(c, str) else tuple(c) for c in (palette or [])] or [(150, 120, 160), (200, 170, 150)]
    lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    dark = min(cols, key=lum)
    while lum(dark) > 95:
        dark = tuple(int(v * 0.8) for v in dark)
    main = max(cols, key=lambda c: max(c) - min(c))
    cream = tuple(int(248 * 0.92 + v * 0.08) for v in cols[0])
    return {"dark": dark, "main": main, "cream": cream, "all": cols}


def _fill(im, w, h, focus=0.5):
    im = im.convert("RGB")
    s = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    l = int((im.width - w) * 0.5)
    t = int((im.height - h) * focus)
    return im.crop((l, t, l + w, t + h))


def _best_photo(items):
    """The most colourful, detailed full picture among the product images (a scene, not a text page or a cut-out)."""
    from PIL import ImageStat
    best, score = None, -1
    for im in items:
        if _is_cutout(im) or min(im.size) < 300:
            continue
        sm = im.convert("RGB").copy()
        sm.thumbnail((256, 256))
        sat = ImageStat.Stat(sm.convert("HSV")).mean[1]
        white = sum(1 for v in sm.convert("L").getdata() if v > 235) / (sm.width * sm.height)
        sc = sat * (1 - white)
        if sc > score:
            best, score = im, sc
    return _fill(best or items[0], 1024, 1024)


def _is_cutout(im):
    if im.mode != "RGBA":
        return False
    a = im.split()[-1]
    return a.getextrema()[0] < 20


def _shadow(canvas, im, xy, blur=22, off=(0, 18), alpha=90):
    a = im.split()[-1] if im.mode == "RGBA" else Image.new("L", im.size, 255)
    pad = blur * 3
    sh = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    m = Image.new("L", sh.size, 0)
    m.paste(a.point(lambda v: v * alpha // 255), (pad, pad))
    sh.putalpha(m.filter(ImageFilter.GaussianBlur(blur)))
    canvas.alpha_composite(sh, (int(xy[0] - pad + off[0]), int(xy[1] - pad + off[1])))
    canvas.alpha_composite(im.convert("RGBA"), (int(xy[0]), int(xy[1])))


def _card(item, maxw, maxh, border=14, radius=18):
    """A product file ready to place: cut-outs as they are, pages/papers with a white border and round corners."""
    it = item.copy()
    if _is_cutout(it):
        it.thumbnail((maxw, maxh), Image.LANCZOS)
        return it.convert("RGBA")
    it = it.convert("RGB")
    it.thumbnail((maxw - border * 2, maxh - border * 2), Image.LANCZOS)
    c = Image.new("RGBA", (it.width + border * 2, it.height + border * 2), (0, 0, 0, 0))
    m = Image.new("L", c.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, c.width - 1, c.height - 1), radius, fill=255)
    white = Image.new("RGBA", c.size, (255, 255, 255, 255))
    white.paste(it, (border, border))
    c.paste(white, (0, 0), m)
    return c


def _text(d, xy, text, f, fill, anchor="la"):
    d.text(xy, text, font=f, fill=fill, anchor=anchor)


def _wrap(d, text, kind, max_w, start, max_lines=2, min_size=70):
    """Biggest font size that fits text in max_lines lines of max_w."""
    words = text.split()
    size = start
    while size >= min_size:
        f = DF.get(kind, size)
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= max_w:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) <= max_lines and all(d.textlength(l, font=f) <= max_w for l in lines):
            return f, lines
        size -= 8
    return DF.get(kind, min_size), [text]


def _count_badge(canvas, cx, cy, r, count, unit, col, ink=(255, 255, 255)):
    d = ImageDraw.Draw(canvas)
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((cx - r, cy - r + 14, cx + r, cy + r + 14), fill=(0, 0, 0, 70))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (255,), outline=(255, 255, 255, 255), width=8)
    num = f"{count:,}"
    f = DF.fit(d, num, "bold", r * 1.45, int(r * 0.95), 40)
    _text(d, (cx, cy + r * 0.10), num, f, ink, "ms")
    uf = DF.fit(d, unit, "bold", r * 1.4, int(r * 0.30), 20)
    _text(d, (cx, cy + r * 0.20), unit, uf, ink, "mt")


def _pick(items, n, rnd):
    items = list(items)
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


# ---------------------------------------------------------------- layouts
def scene_frame(hero, items, t, rnd):
    c = _fill(hero, S, S).convert("RGBA")
    p = t["p"]
    # product cards floating at the top right
    cards = _pick(items, 2, rnd)
    for k, it in enumerate(cards[::-1]):
        cd = _card(it, 760, 620).rotate((-6, 5)[k % 2], expand=True, resample=Image.BICUBIC)
        _shadow(c, cd, (S - cd.width - 110 + k * 60, 120 + k * 150))
    # frosted panel at the bottom
    ph = 620
    panel = c.crop((0, S - ph, S, S)).filter(ImageFilter.GaussianBlur(26))
    panel = Image.blend(panel.convert("RGB"), Image.new("RGB", panel.size, p["cream"]), 0.78).convert("RGBA")
    c.alpha_composite(panel, (0, S - ph))
    d = ImageDraw.Draw(c)
    d.line((110, S - ph + 70, 330, S - ph + 70), fill=p["main"] + (255,), width=8)
    sf = DF.fit(d, t["kicker"], "bold", 1300, 70, 36)
    _text(d, (110, S - ph + 100), t["kicker"], sf, p["main"] + (255,))
    f, lines = _wrap(d, t["title"], "serif", 1350, 190, 2)
    y = S - ph + 200
    for ln in lines:
        _text(d, (105, y), ln, f, p["dark"] + (255,))
        y += f.size * 1.05
    if t.get("count"):
        _count_badge(c, S - 300, S - ph + 290, 200, t["count"], t["unit"], p["main"])
    return c


def arch(hero, items, t, rnd):
    p = t["p"]
    c = Image.new("RGBA", (S, S), p["cream"] + (255,))
    d = ImageDraw.Draw(c)
    # arch window with the scene, left
    aw, ah, ax, ay = 900, 1500, 110, 380
    win = _fill(hero, aw, ah).convert("RGBA")
    m = Image.new("L", (aw, ah), 0)
    md = ImageDraw.Draw(m)
    md.ellipse((0, 0, aw, aw), fill=255)
    md.rectangle((0, aw // 2, aw, ah), fill=255)
    win.putalpha(m)
    d.rounded_rectangle((ax - 26, ay - 26, ax + aw + 26, ay + ah + 26), 40, outline=p["main"] + (255,), width=0)
    _shadow(c, win, (ax, ay), blur=26, alpha=70)
    d = ImageDraw.Draw(c)
    # big stacked title, right
    kf = DF.fit(d, t["kicker"], "bold", 900, 66, 30)
    _text(d, (1090, 120), t["kicker"], kf, p["main"] + (255,))
    f, lines = _wrap(d, t["title"].upper(), "bold", 820, 240, 4, 60)
    y = 210
    for ln in lines:
        _text(d, (1085, y), ln, f, p["dark"] + (255,))
        y += f.size * 0.98
    if t.get("count"):
        num = f"{t['count']:,} {t['unit'].lower()}"
        nf = DF.fit(d, num, "elegant", 820, 130, 50)
        _text(d, (1090, y + 30), num, nf, p["main"] + (255,))
        y += nf.size + 60
    # product files fanned below the title
    cards = _pick(items, 3, rnd)
    for k, it in enumerate(cards):
        cd = _card(it, 560, 460).rotate((-8, 0, 8)[k], expand=True, resample=Image.BICUBIC)
        _shadow(c, cd, (1050 + k * 150, max(y + 40, 1080) + k * 70))
    return c


def split(hero, items, t, rnd):
    p = t["p"]
    c = Image.new("RGBA", (S, S), p["dark"] + (255,))
    c.paste(_fill(hero, S // 2, S), (0, 0))
    d = ImageDraw.Draw(c)
    x0 = S // 2 + 110
    kf = DF.fit(d, t["kicker"], "bold", 760, 62, 30)
    _text(d, (x0, 170), t["kicker"], kf, p["cream"] + (255,))
    f, lines = _wrap(d, t["title"], "serif", 780, 200, 3)
    y = 260
    for ln in lines:
        _text(d, (x0, y), ln, f, (255, 255, 255, 255))
        y += f.size * 1.04
    ff = font("sans", 52)
    y += 50
    for feat in t["features"][:4]:
        d.ellipse((x0, y + 8, x0 + 44, y + 52), fill=p["main"] + (255,))
        d.line((x0 + 12, y + 30, x0 + 20, y + 40, x0 + 34, y + 20), fill=(255, 255, 255, 255), width=6)
        _text(d, (x0 + 70, y), feat, ff, p["cream"] + (255,))
        y += 92
    cards = _pick(items, 1, rnd)
    if cards:
        cd = _card(cards[0], 700, 560).rotate(-4, expand=True, resample=Image.BICUBIC)
        _shadow(c, cd, (S // 2 - cd.width // 2, S - cd.height - 120))
    if t.get("count"):
        _count_badge(c, 300, 300, 200, t["count"], t["unit"], p["main"])
    return c


def flatlay(hero, items, t, rnd):
    p = t["p"]
    bg = _fill(hero, S, S).filter(ImageFilter.GaussianBlur(3))
    c = Image.blend(bg, Image.new("RGB", (S, S), p["cream"]), 0.18).convert("RGBA")
    spots = [(300, 380), (1000, 260), (1680, 420), (360, 1480), (1660, 1500), (1000, 1720), (1700, 960), (280, 960)]
    cards = _pick(items, len(spots), rnd)
    for (x, y), it in zip(spots, cards):
        cd = _card(it, 560, 460).rotate(rnd.uniform(-14, 14), expand=True, resample=Image.BICUBIC)
        _shadow(c, cd, (x - cd.width // 2, y - cd.height // 2), blur=18, alpha=80)
    # paper tag in the middle
    tw, th = 1240, 720
    tag = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    td = ImageDraw.Draw(tag)
    td.rounded_rectangle((0, 0, tw - 1, th - 1), 40, fill=(255, 253, 249, 255), outline=p["main"] + (255,), width=6)
    td.rounded_rectangle((22, 22, tw - 23, th - 23), 30, outline=p["main"] + (120,), width=2)
    kf = DF.fit(td, t["kicker"], "bold", tw - 200, 60, 30)
    _text(td, (tw // 2, 90), t["kicker"], kf, p["main"] + (255,), "mt")
    f, lines = _wrap(td, t["title"], "script", tw - 160, 190, 2, 80)
    y = 190
    for ln in lines:
        _text(td, (tw // 2, y), ln, f, p["dark"] + (255,), "mt")
        y += f.size * 1.05
    if t.get("count"):
        num = f"{t['count']:,} {t['unit']}"
        nf = DF.fit(td, num, "bold", tw - 240, 96, 40)
        td.rounded_rectangle((tw // 2 - td.textlength(num, font=nf) / 2 - 40, th - 170,
                              tw // 2 + td.textlength(num, font=nf) / 2 + 40, th - 60), 50, fill=p["dark"] + (255,))
        _text(td, (tw // 2, th - 115), num, nf, (255, 255, 255, 255), "mm")
    tag = tag.rotate(rnd.uniform(-3, 3), expand=True, resample=Image.BICUBIC)
    _shadow(c, tag, ((S - tag.width) // 2, (S - tag.height) // 2), blur=26, alpha=110)
    return c


def magazine(hero, items, t, rnd):
    p = t["p"]
    c = Image.new("RGBA", (S, S), (255, 254, 251, 255))
    hh = 1080
    c.paste(_fill(hero, S, hh, focus=0.45), (0, 0))
    d = ImageDraw.Draw(c)
    # kicker on a colour strip over the image edge
    kf = DF.fit(d, t["kicker"], "bold", 1100, 64, 30)
    kw = d.textlength(t["kicker"], font=kf)
    d.rectangle((100, hh - 60, 100 + kw + 80, hh + 40), fill=p["main"] + (255,))
    _text(d, (140, hh - 10), t["kicker"], kf, (255, 255, 255, 255), "lm")
    f, lines = _wrap(d, t["title"], "serif", S - 220, 200, 2)
    y = hh + 90
    for ln in lines:
        _text(d, (100, y), ln, f, p["dark"] + (255,))
        y += f.size * 1.02
    cards = _pick(items, 4, rnd)
    cw = (S - 200 - 3 * 40) // 4
    for k, it in enumerate(cards):
        cd = _card(it, cw, S - y - 130)
        _shadow(c, cd, (100 + k * (cw + 40) + (cw - cd.width) // 2, max(y + 40, S - cd.height - 90)), blur=14, alpha=70)
    if t.get("count"):
        _count_badge(c, S - 260, 260, 180, t["count"], t["unit"], p["main"])
    return c


FUNCS = {"scene_frame": scene_frame, "arch": arch, "split": split, "flatlay": flatlay, "magazine": magazine}


# ---------------------------------------------------------------- public
def choose_layout(slug, recent):
    """A layout the shop has not used in its last products (recent: newest first)."""
    rnd = random.Random(slug)
    fresh = [l for l in LAYOUTS if l not in recent[:3]] or list(LAYOUTS)
    least = min(fresh, key=lambda l: (recent[:8].count(l), rnd.random()))
    return least


def make(layout, hero, items, *, title, kicker, count=None, unit="", features=(), palette=None, seed="x"):
    rnd = random.Random(seed)
    items = [i for i in items if i is not None] or [hero]
    if hero is None:  # no AI scene today: the product's own most photo-like picture, sharp (never blurred)
        hero = _best_photo(items)
    t = {"title": title, "kicker": kicker.upper(), "count": count, "unit": unit.upper(),
         "features": list(features) or ["Instant download", "Print or digital", "High quality"], "p": _pal(palette)}
    return FUNCS[layout](hero, items, t, rnd).convert("RGB")
