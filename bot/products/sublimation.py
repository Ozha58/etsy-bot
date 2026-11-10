"""Sublimation / shirt PNG designs: 8 finished designs (AI illustration + a short phrase set in real fonts by code,
so the words are never misspelled) as transparent PNG, plus a ready 11 oz mug wrap of each.
Honest size: 3600 x 3600 px canvas, 300 DPI (12 in); the illustration itself is upscaled from the AI image,
so we sell it for mugs, tumblers, tote bags and light shirts up to about 10 in."""
import random
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import display_fonts as DF
from .. import images, mockups
from ..bundle_cover import bundle_cover
from ..imgutil import color_to_alpha_background, hex2rgb, jpeg_bytes, make_zips, paste_with_shadow, png_bytes, thumb_b64, trim_alpha

COUNT = 8
SIZE = 3600
LABEL_TR = f"Sublimation / tişört tasarımı ({COUNT} PNG tasarım + kupa şablonları)"
SPEC_FIELDS = f"""
  "set_name": "short set name, 2-4 words (e.g. 'Cozy Christmas Vibes')",
  "subject": "the set's main subject in 1-3 words",
  "designs": [ exactly {COUNT} objects {{"name": "short name", "phrase": "the words printed on the design: 1-4 short English words, upbeat, family friendly, no brand, song, movie or famous quote (e.g. 'Merry and Bright', 'Hot Cocoa Season')", "prompt": "English prompt for ONE isolated illustration that fits the phrase (a cute scene or object group), no text in the picture"}} ]
"""
SUFFIX = ("isolated illustration for a t-shirt print, centered composition, clean outline, vibrant colors, "
          "pure plain white background, no shadow, no ground, no text, no letters, no words, no border, no frame")
LAYOUTS = ("script_top", "bold_bottom", "split", "elegant_top")
TEXT_OK = re.compile(r"^[A-Za-z0-9 '&!.,-]{2,28}$")


def _ink(palette, k):
    """A dark, readable text colour from the palette (light colours are darkened)."""
    cols = [hex2rgb(c) for c in palette] or [(180, 40, 50), (30, 90, 60)]
    lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    out = []
    for c in cols:
        while lum(c) > 120:
            c = tuple(int(v * 0.82) for v in c)
        out.append(c)
    return out[k % len(out)]


def _lines(text, n):
    words = text.split()
    if n == 1 or len(words) < 2:
        return [text]
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1]


def _text_img(text, kind, max_w, size, fill, max_h=1250):
    """Words as a transparent image (1 or 2 lines, whichever is bigger) with a white keyline for dark fabric."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    best = None
    for n in (1, 2):
        lines = _lines(text, n)
        if len(lines) < n:
            continue
        f = DF.fit(probe, max(lines, key=len), kind, max_w, size, 90)
        while True:
            boxes = [probe.textbbox((0, 0), ln, font=f, stroke_width=14) for ln in lines]
            h = sum(b[3] - b[1] for b in boxes) + 40 * (len(lines) - 1)
            if h <= max_h or f.size <= 100 or all(probe.textlength(ln, font=f) <= max_w for ln in lines) and h <= max_h:
                break
            f = DF.get(kind, f.size - 20)
        if h > max_h:
            continue
        if best is None or f.size > best[0].size:
            best = (f, lines, boxes)
    if best is None:
        f = DF.fit(probe, text, kind, max_w, size, 90)
        best = (f, [text], [probe.textbbox((0, 0), text, font=f, stroke_width=14)])
    f, lines, boxes = best
    w = max(b[2] - b[0] for b in boxes) + 40
    h = sum(b[3] - b[1] for b in boxes) + 40 * len(lines)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = 20
    for ln, b in zip(lines, boxes):
        lw = b[2] - b[0]
        d.text(((w - lw) / 2 - b[0], y - b[1]), ln, font=f, fill=fill + (255,), stroke_width=14, stroke_fill=(255, 255, 255, 255))
        y += b[3] - b[1] + 40
    return im


def design(art, phrase, layout, ink):
    c = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    a = art.copy()
    if layout == "split":
        words = phrase.split()
        top, bottom = " ".join(words[:max(1, len(words) // 2)]), " ".join(words[max(1, len(words) // 2):])
        t1 = _text_img(top.upper(), "bold", SIZE * 0.9, 900, ink, max_h=800)
        t2 = _text_img(bottom.upper(), "bold", SIZE * 0.9, 900, ink, max_h=800) if bottom else None
        room = SIZE - t1.height - (t2.height if t2 else 0) - 260
        a.thumbnail((int(SIZE * 0.86), room), Image.LANCZOS)
        y = (SIZE - (t1.height + a.height + (t2.height if t2 else 0) + 120)) // 2
        c.alpha_composite(t1, ((SIZE - t1.width) // 2, y))
        c.alpha_composite(a, ((SIZE - a.width) // 2, y + t1.height + 60))
        if t2:
            c.alpha_composite(t2, ((SIZE - t2.width) // 2, y + t1.height + a.height + 120))
        return c
    kind = {"script_top": "script", "bold_bottom": "bold", "elegant_top": "elegant"}[layout]
    t = _text_img(phrase if kind != "bold" else phrase.upper(), kind, SIZE * 0.92, 1000 if kind != "bold" else 900, ink)
    a.thumbnail((int(SIZE * 0.80), SIZE - t.height - 300), Image.LANCZOS)
    gap = 40
    total = t.height + gap + a.height
    y = (SIZE - total) // 2
    if layout == "bold_bottom":
        c.alpha_composite(a, ((SIZE - a.width) // 2, y))
        c.alpha_composite(t, ((SIZE - t.width) // 2, y + a.height + gap))
    else:
        c.alpha_composite(t, ((SIZE - t.width) // 2, y))
        c.alpha_composite(a, ((SIZE - a.width) // 2, y + t.height + gap))
    return c


# ---------------------------------------------------------------- retro screen-print look ("look": "retro")
RETRO_INK, RETRO_PAPER = (38, 26, 24), (250, 240, 220)
DARK_TEE = (24, 62, 50)  # forest green shirt in the retro mockups: shows the cream edge of the print
RETRO_FONTS = ("rounded", "retro", "serif", "bold")
RETRO_PATTERNS = ("gingham", "stripes", "dots", "solid", "checks")


def _retro_font(kind, size):
    f = DF.get(kind, size)
    if kind == "rounded":  # Fredoka is a variable font: use its heaviest weight
        try:
            f.set_variation_by_axes([a["maximum"] if b"eight" in a["name"] else a["default"]
                                     for a in f.get_variation_axes()])
        except Exception:
            pass
    return f


def _pattern(kind, w, h, col, cell):
    """A flat fill for one letter: plaid gingham, candy stripes, polka dots, checkerboard or the plain colour."""
    im = Image.new("RGB", (w, h), col)
    d = ImageDraw.Draw(im)
    cream = RETRO_PAPER
    mid = tuple((a + b) // 2 for a, b in zip(col, cream))
    if kind == "gingham":
        im.paste(cream, (0, 0, w, h))
        for x in range(0, w, 2 * cell):
            d.rectangle((x, 0, x + cell - 1, h), fill=mid)
        for y in range(0, h, 2 * cell):
            for x in range(0, w, cell):
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=col if (x // cell) % 2 == 0 else mid)
    elif kind == "stripes":
        im.paste(cream, (0, 0, w, h))
        for x in range(-h, w + h, 2 * cell):
            d.polygon([(x, 0), (x + cell, 0), (x + cell + h, h), (x + h, h)], fill=col)
    elif kind == "dots":
        r = max(4, cell // 3)
        for j, y in enumerate(range(cell // 2, h + cell, cell)):
            for x in range(cell // 2 + (cell // 2 if j % 2 else 0), w + cell, cell):
                d.ellipse((x - r, y - r, x + r, y + r), fill=cream)
    elif kind == "checks":
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                if (x // cell + y // cell) % 2:
                    d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=cream)
    return im


def _retro_text(text, kind, max_w, max_h, fill, block, fills=None, k=0):
    """Words like an old screen print: flat fill, thick dark outline, a solid offset block in a second colour and a
    cream edge around everything (so it also reads on dark fabric). No blur, no gradient.
    fills: colours for patterned letters (every letter its own colour and pattern, like hand-cut applique letters);
    None keeps one flat colour."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    best = None
    for n in (1, 2):
        lines = _lines(text, n)
        if len(lines) < n:
            continue
        size = 1000
        while size > 110:
            f = _retro_font(kind, size)
            line, off = max(8, int(size * 0.035)), int(size * 0.07)
            edge = line + max(10, int(size * 0.045))
            boxes = [probe.textbbox((0, 0), ln, font=f) for ln in lines]
            gap = int(size * 0.10)
            w = max(b[2] - b[0] for b in boxes) + 2 * edge + off
            h = sum(b[3] - b[1] for b in boxes) + gap * (len(lines) - 1) + 2 * edge + off
            if w <= max_w and h <= max_h:
                break
            size -= max(10, size // 18)
        if best is None or size > best[0]:
            best = (size, lines, f, line, off, edge, boxes, gap, int(w), int(h))
    size, lines, f, line, off, edge, boxes, gap, w, h = best
    spots, y = [], edge
    for ln, b in zip(lines, boxes):
        spots.append(((w - off - (b[2] - b[0])) / 2 - b[0], y - b[1], ln))
        y += b[3] - b[1] + gap
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x, yy, ln in spots:  # cream edge under everything
        for dx, dy in ((0, 0), (off, off)):
            d.text((x + dx, yy + dy), ln, font=f, fill=RETRO_PAPER + (255,), stroke_width=edge, stroke_fill=RETRO_PAPER + (255,))
    steps = range(off, 0, -2)  # solid block, bottom right: dark silhouette first, colour inside it
    for step in steps:
        for x, yy, ln in spots:
            d.text((x + step, yy + step), ln, font=f, fill=RETRO_INK + (255,), stroke_width=line, stroke_fill=RETRO_INK + (255,))
    for step in steps:
        for x, yy, ln in spots:
            d.text((x + step, yy + step), ln, font=f, fill=block + (255,))
    for x, yy, ln in spots:
        d.text((x, yy), ln, font=f, fill=fill + (255,), stroke_width=line, stroke_fill=RETRO_INK + (255,))
    if fills:
        cell, i = max(18, size // 9), 0
        for x, yy, ln in spots:
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).text((x, yy), ln, font=f, fill=255)
            for j, ch in enumerate(ln):  # one colour + pattern per letter, cut at the letter's own column
                if ch.isspace():
                    continue
                x0, x1 = int(x + probe.textlength(ln[:j], font=f)), int(x + probe.textlength(ln[:j + 1], font=f)) + 1
                band = Image.new("L", (w, h), 0)
                band.paste(mask.crop((x0, 0, min(w, x1), h)), (x0, 0))
                pat = _pattern(RETRO_PATTERNS[(i + k) % len(RETRO_PATTERNS)], w, h, fills[(i + k) % len(fills)], cell)
                im.paste(pat, (0, 0), band)
                i += 1
    return im


def _ornaments(c, cols, rnd, count=22):
    """Fills the empty space around the drawing and the words with small code-drawn stars, snowflakes, holly and
    dots (flat colour + dark outline), so the design reads as one full square print instead of a small picture."""
    import math
    g = 120
    cell = SIZE // g
    occ = np.asarray(c.getchannel("A").resize((g, g), Image.BILINEAR).filter(ImageFilter.MaxFilter(5))) > 8
    occ = occ.copy()
    d = ImageDraw.Draw(c)
    ink = RETRO_INK + (255,)

    def star(cx, cy, r, col):
        pts = [(cx + math.cos(math.pi / 4 * i - math.pi / 2) * (r if i % 2 == 0 else r * 0.34),
                cy + math.sin(math.pi / 4 * i - math.pi / 2) * (r if i % 2 == 0 else r * 0.34)) for i in range(8)]
        d.polygon(pts, fill=col + (255,))
        d.line(pts + pts[:2], fill=ink, width=max(8, int(r * 0.11)), joint="curve")

    def flake(cx, cy, r, col):
        for wd, cc in ((int(r * 0.30), ink), (int(r * 0.14), col + (255,))):
            for i in range(6):
                a = math.pi / 3 * i
                d.line((cx, cy, cx + math.cos(a) * r, cy + math.sin(a) * r), fill=cc, width=max(6, wd))
                bx, by = cx + math.cos(a) * r * 0.6, cy + math.sin(a) * r * 0.6
                for sgn in (-1, 1):
                    b = a + sgn * math.pi / 4
                    d.line((bx, by, bx + math.cos(b) * r * 0.3, by + math.sin(b) * r * 0.3), fill=cc, width=max(6, wd))

    def holly(cx, cy, r, col):
        lw = max(8, int(r * 0.1))
        for sgn in (-1, 1):
            pts = [(cx, cy + r * 0.1), (cx + sgn * r * 0.3, cy - r * 0.55), (cx + sgn * r * 0.55, cy - r * 0.3),
                   (cx + sgn * r * 0.95, cy - r * 0.5), (cx + sgn * r * 0.8, cy - r * 0.05), (cx + sgn * r * 0.98, cy + r * 0.3),
                   (cx + sgn * r * 0.5, cy + r * 0.25), (cx + sgn * r * 0.3, cy + r * 0.5)]
            d.polygon(pts, fill=(28, 110, 86, 255))
            d.line(pts + pts[:2], fill=ink, width=lw, joint="curve")
        for bx, by in ((-0.2, 0.2), (0.2, 0.2), (0, -0.12)):
            br = r * 0.24
            d.ellipse((cx + bx * r - br, cy + by * r - br, cx + bx * r + br, cy + by * r + br), fill=(196, 40, 44, 255),
                      outline=ink, width=lw)

    def dot(cx, cy, r, col):
        r *= 0.5
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (255,), outline=ink, width=max(8, int(r * 0.2)))

    shapes = (star, flake, holly, star, dot)
    placed = 0
    for size in [5] * 40 + [4] * 60 + [3] * 80 + [2] * 80:  # big ones first (radius in grid cells)
        if placed >= count:
            break
        gx, gy = rnd.randrange(size + 1, g - size - 1), rnd.randrange(size + 1, g - size - 1)
        if occ[gy - size - 1:gy + size + 2, gx - size - 1:gx + size + 2].any():
            continue
        # only near the design: something of the design within reach, so nothing floats alone in a corner
        if not occ[max(0, gy - size - 9):gy + size + 10, max(0, gx - size - 9):gx + size + 10].any():
            continue
        occ[gy - size - 2:gy + size + 3, gx - size - 2:gx + size + 3] = True
        shapes[rnd.randrange(len(shapes))]((gx + 0.5) * cell, (gy + 0.5) * cell, size * cell * 0.9,
                                           cols[rnd.randrange(len(cols))])
        placed += 1


def distress(im, seed=0, amount=1.0):
    """Worn screen-print texture: small flecks, a few bigger worn patches and fine scratches are knocked out of the
    design (alpha only, so it stays a clean transparent PNG). Deterministic per seed."""
    rng = np.random.default_rng(seed)
    w, h = im.size
    q = 4  # texture is made at 1/4 size: a fleck is a few print pixels wide
    sw, sh = w // q, h // q
    fleck = rng.random((sh, sw)) < 0.010 * amount
    soft = np.asarray(Image.fromarray((rng.random((sh // 6, sw // 6)) * 255).astype(np.uint8))
                      .resize((sw, sh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))).astype(np.float32) / 255
    worn = (soft > 0.58) & (rng.random((sh, sw)) < 0.07 * amount)  # patches where more ink is gone
    hole = Image.fromarray(((fleck | worn) * 255).astype(np.uint8))
    hd = ImageDraw.Draw(hole)
    for _ in range(int(14 * amount)):  # scratches
        x, y = int(rng.integers(0, sw)), int(rng.integers(0, sh))
        ln, ang = int(rng.integers(20, 110)), float(rng.uniform(-0.5, 0.5)) + (np.pi / 2 if rng.random() < 0.5 else 0)
        hd.line((x, y, x + ln * np.cos(ang), y + ln * np.sin(ang)), fill=255, width=1)
    hole = hole.resize((w, h), Image.BICUBIC).point(lambda v: 255 if v > 120 else 0)
    a = np.asarray(im.getchannel("A")).copy()
    a[np.asarray(hole) > 0] = 0
    out = im.copy()
    out.putalpha(Image.fromarray(a))
    return out


def retro_design(art, phrase, k, palette, seed=0):
    """One finished design in the retro look: a big drawing with the phrase laid over its edge (above, below or split
    around it), patterned applique letters on every other design, small ornaments filling the square, then the worn
    print texture over everything."""
    cols = [hex2rgb(c) for c in palette] or [(196, 40, 44), (28, 110, 86), (30, 126, 140), (226, 164, 44)]
    lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    strong = [c for c in cols if 40 < lum(c) < 185] or [(196, 40, 44), (28, 110, 86)]
    fill, block = strong[k % len(strong)], strong[(k + 1) % len(strong)]
    kind = RETRO_FONTS[k % len(RETRO_FONTS)]
    fills = strong if kind in ("rounded", "bold") else None  # letter patterns need upright, separate letters
    text = phrase.upper() if kind in ("bold", "rounded") else phrase
    layout = ("top", "bottom", "split")[k % 3]
    words = text.split()
    rnd = random.Random(seed * 100 + k)
    c = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    a = art.copy()
    if layout == "split" and len(words) >= 3:
        half = max(1, len(words) // 2)
        t1 = _retro_text(" ".join(words[:half]), kind, SIZE * 0.96, 820, fill, block, fills, k)
        t2 = _retro_text(" ".join(words[half:]), kind, SIZE * 0.96, 820, block, fill, fills, k + 3)
        lap = 130
        a.thumbnail((int(SIZE * 0.96), SIZE - t1.height - t2.height + 2 * lap - 40), Image.LANCZOS)
        y = (SIZE - (t1.height + a.height + t2.height - 2 * lap)) // 2
        c.alpha_composite(a, ((SIZE - a.width) // 2, y + t1.height - lap))
        c.alpha_composite(t1, ((SIZE - t1.width) // 2, y))
        c.alpha_composite(t2, ((SIZE - t2.width) // 2, y + t1.height + a.height - 2 * lap))
    else:
        t = _retro_text(text, kind, SIZE * 0.96, 1300, fill, block, fills, k)
        lap = 150  # the words sit over the edge of the drawing, like one printed badge
        a.thumbnail((int(SIZE * 0.96), SIZE - t.height + lap - 40), Image.LANCZOS)
        y = (SIZE - (t.height + a.height - lap)) // 2
        if layout == "top":
            c.alpha_composite(a, ((SIZE - a.width) // 2, y + t.height - lap))
            c.alpha_composite(t, ((SIZE - t.width) // 2, y))
        else:
            c.alpha_composite(a, ((SIZE - a.width) // 2, y))
            c.alpha_composite(t, ((SIZE - t.width) // 2, y + a.height - lap))
    _ornaments(c, strong, rnd)
    return distress(c, seed=seed * 100 + k)


def mug_wrap(d):
    """11 oz mug template, 2700 x 1100 px (9 x 3.7 in at 300 DPI): the design on both sides of the handle."""
    w, h = 2700, 1100
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    s = d.copy()
    s.thumbnail((int(w * 0.40), int(h * 0.92)), Image.LANCZOS)
    for cx in (w * 0.25, w * 0.75):
        c.alpha_composite(s, (int(cx - s.width / 2), (h - s.height) // 2))
    return c


# ---------------------------------------------------------------- code-drawn mockups (no stock photos)
def _tee(color, w=1100, h=1200):
    """A flat-lay t-shirt drawn by code: neckline, shoulders, sleeves, soft light and folds."""
    import math
    P = lambda x, y: (w * x, h * y)
    neck = [P(0.5 + 0.12 * math.cos(a), 0.055 + 0.075 * math.sin(a)) for a in [i * math.pi / 16 for i in range(17)]]
    body = [P(0.38, 0.055), P(0.17, 0.11), P(0.02, 0.33), P(0.14, 0.44), P(0.25, 0.36), P(0.24, 0.98), P(0.76, 0.98),
            P(0.75, 0.36), P(0.86, 0.44), P(0.98, 0.33), P(0.83, 0.11), P(0.62, 0.055)] + neck
    t = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(t).polygon(body, fill=color + (255,))
    alpha = np.asarray(t.split()[-1]).astype(np.float32) / 255
    a = np.asarray(t.convert("RGB")).astype(np.float32)
    xs = np.linspace(-1, 1, w)[None, :, None]
    ys = np.linspace(0, 1, h)[:, None, None]
    light = 1.03 - 0.07 * xs - 0.04 * ys
    folds = 1 - 0.035 * np.exp(-((xs - 0.35) / 0.05) ** 2) - 0.03 * np.exp(-((xs + 0.42) / 0.06) ** 2)
    a = np.clip(a * light * folds, 0, 255)
    out = Image.fromarray(a.astype(np.uint8)).convert("RGBA")
    out.putalpha(Image.fromarray((alpha * 255).astype(np.uint8)))
    d = ImageDraw.Draw(out)
    d.line(neck, fill=tuple(int(v * 0.86) for v in color) + (255,), width=18, joint="curve")
    return out


def tee_mock(dsg, palette, label, scale=.42, second=(212, 194, 182)):
    """scale: width of the print on the shirt (0.42 = a chest print, 0.6 = a big front print)."""
    pal = mockups.palette_colors(palette)
    c = mockups._bg(pal)
    for col, x in (((240, 237, 230), 90), (second, mockups.W - 1190)):
        t = _tee(col)
        s = dsg.copy()
        s.thumbnail((int(t.width * scale), int(t.height * scale)), Image.LANCZOS)
        t.alpha_composite(s, ((t.width - s.width) // 2, int(t.height * (.19 if scale < .5 else .15))))
        paste_with_shadow(c, t, (x, 230), radius=30, offset=(0, 22), opacity=70)
    d = ImageDraw.Draw(c)
    f = mockups.font("sans_bold", 64)
    d.text(((mockups.W - d.textlength(label, font=f)) / 2, 90), label, font=f, fill=pal["text"] + (255,))
    return c.convert("RGB")


def mug_mock(dsg, palette):
    pal = mockups.palette_colors(palette)
    c = mockups._bg(pal)
    mw, mh = 1100, 1150
    body = Image.new("RGB", (mw, mh), (250, 250, 250))
    s = dsg.copy()
    s.thumbnail((int(mw * .62), int(mh * .62)), Image.LANCZOS)
    body.paste(s, ((mw - s.width) // 2, (mh - s.height) // 2 + 20), s)
    a = np.asarray(body).astype(np.float32)
    xs = np.arange(mw)
    theta = np.arcsin(np.clip((xs - mw / 2) / (mw / 2), -0.999, 0.999))
    shade = 0.74 + 0.26 * np.cos(theta)
    hl = np.exp(-((xs - mw * 0.30) / (mw * 0.05)) ** 2) * 35
    a = np.clip(a * shade[None, :, None] + hl[None, :, None], 0, 255).astype(np.uint8)
    mug = Image.new("RGBA", (mw + 420, mh + 80), (0, 0, 0, 0))
    md = ImageDraw.Draw(mug)
    md.rounded_rectangle((mw - 60, mh * .22, mw + 360, mh * .78), radius=200, outline=(232, 232, 232, 255), width=90)
    bimg = Image.fromarray(a).convert("RGBA")
    mask = Image.new("L", (mw, mh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mw - 1, mh - 1), radius=50, fill=255)
    bimg.putalpha(mask)
    mug.alpha_composite(bimg, (0, 40))
    md.ellipse((0, 0, mw, 90), fill=(236, 236, 236, 255), outline=(220, 220, 220, 255), width=6)
    paste_with_shadow(c, mug, ((mockups.W - mug.width) // 2, (mockups.H - mug.height) // 2), radius=30, offset=(24, 30), opacity=80)
    d = ImageDraw.Draw(c)
    f = mockups.font("sans_bold", 60)
    t = "11 OZ MUG WRAP INCLUDED"
    d.text(((mockups.W - d.textlength(t, font=f)) / 2, 90), t, font=f, fill=pal["text"] + (255,))
    return c.convert("RGB")


# ---------------------------------------------------------------- the print on a photographed shirt
PHOTO_SHIRTS = {
    "flatlay": "flat lay product photo taken from directly above of one plain blank forest green cotton t-shirt, neatly "
               "laid flat and centered on a light oak wooden table, the whole shirt visible, completely blank front, "
               "soft natural daylight, realistic photography, no print, no logo, no text, no letters",
    "worn": "realistic photo of a woman wearing a plain blank cream crewneck sweatshirt, cropped from the chin to the "
            "waist, face not visible, straight front view, centered, hands in jeans pockets, softly blurred cozy "
            "living room with a Christmas tree and warm lights behind her, completely blank sweatshirt front, "
            "no print, no logo, no text, no letters",
}


def _shirt_box(a):
    """Where the shirt front is in a photo (H x W x 3 float array): the area around the centre that has the colour of
    the centre. Returns (x0, y0, x1, y1); a safe middle box when the picture gives no clear answer."""
    h, w = a.shape[:2]
    patch = a[int(h * .45):int(h * .65), int(w * .40):int(w * .60)].reshape(-1, 3)
    col = np.median(patch, axis=0)
    same = np.sqrt(((a - col) ** 2).sum(axis=2)) < 62

    def run(frac, mid, need):
        lo = hi = mid
        while lo > 0 and frac[lo - 1] >= need:
            lo -= 1
        while hi < len(frac) - 1 and frac[hi + 1] >= need:
            hi += 1
        return lo, hi

    x0, x1 = run(same[int(h * .35):int(h * .80)].mean(axis=0), w // 2, 0.5)
    y0, y1 = run(same[:, x0:x1 + 1].mean(axis=1), int(h * .55), 0.55)
    if x1 - x0 < w * .25 or y1 - y0 < h * .25:
        return int(w * .28), int(h * .22), int(w * .72), int(h * .90)
    return x0, y0, x1, y1


def photo_mock(dsg, kind):
    """The design printed on an AI photographed blank shirt (1 image): it follows the light and folds of the fabric.
    None when no photo could be made; the caller then uses the code-drawn shirt."""
    im = images.try_generate(PHOTO_SHIRTS[kind], 1024, 1024)
    if im is None:
        return None
    S = 2000
    photo = im.convert("RGB").resize((S, S), Image.LANCZOS)
    a = np.asarray(photo).astype(np.float32)
    x0, y0, x1, y1 = _shirt_box(a)
    s = dsg.copy()
    s.thumbnail((int((x1 - x0) * .80), int((y1 - y0) * .66)), Image.LANCZOS)
    px, py = (x0 + x1) // 2 - s.width // 2, y0 + int((y1 - y0) * (.20 if kind == "flatlay" else .14))
    py = min(py, S - s.height - 10)
    # fabric light: the print gets darker in the folds and lighter on the highlights of the shirt under it
    lum = a[py:py + s.height, px:px + s.width].mean(axis=2)
    lum = np.asarray(Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(5))).astype(np.float32)
    shade = np.clip(lum / max(1.0, float(np.median(lum))), 0.55, 1.12)[..., None]
    d = np.asarray(s).astype(np.float32)
    d[..., :3] = np.clip(d[..., :3] * shade, 0, 255)
    d[..., 3] *= 0.96
    printed = Image.fromarray(d.astype(np.uint8), "RGBA")
    out = photo.convert("RGBA")
    out.alpha_composite(printed, (px, py))
    return out.convert("RGB")


def product_cover(dsgs, n, name, palette, title=None, scale=.46, second=(214, 196, 184)):
    """First photo: the designs ON products (a big shirt, a mug and a tote), so a buyer sees at once what they get."""
    pal = mockups.palette_colors(palette)
    S = 2000
    c = Image.new("RGBA", (S, S), (244, 239, 231, 255))
    d = ImageDraw.Draw(c)
    for y in range(S):  # soft warm gradient, a little darker at the bottom like a table
        k = y / S
        d.line((0, y, S, y), fill=(int(246 - 18 * k), int(241 - 20 * k), int(233 - 22 * k), 255))
    # big shirt, centre left
    t = _tee((247, 245, 240), 1240, 1350)
    s = dsgs[0].copy()
    s.thumbnail((int(t.width * scale), int(t.height * scale)), Image.LANCZOS)
    t.alpha_composite(s, ((t.width - s.width) // 2, int(t.height * (.2 if scale < .5 else .15))))
    paste_with_shadow(c, t, (90, 470), radius=34, offset=(0, 26), opacity=75)
    # second shirt (other colour) peeking behind on the right
    t2 = _tee(second, 820, 900)
    s2 = dsgs[1 % n].copy()
    s2.thumbnail((int(t2.width * (scale - .02)), int(t2.height * (scale - .02))), Image.LANCZOS)
    t2.alpha_composite(s2, ((t2.width - s2.width) // 2, int(t2.height * (.2 if scale < .5 else .15))))
    paste_with_shadow(c, t2, (1120, 430), radius=30, offset=(0, 22), opacity=65)
    # mug, bottom right, in front
    mug = mug_mock(dsgs[2 % n], palette)
    m = mug.crop((int(mug.width * .18), int(mug.height * .14), int(mug.width * .86), int(mug.height * .94)))
    m.thumbnail((760, 760), Image.LANCZOS)
    mm = Image.new("L", m.size, 0)
    ImageDraw.Draw(mm).rounded_rectangle((0, 0, m.width - 1, m.height - 1), radius=40, fill=255)
    mr = m.convert("RGBA"); mr.putalpha(mm)
    paste_with_shadow(c, mr, (S - m.width - 70, S - m.height - 70), radius=30, offset=(0, 20), opacity=70)
    # title band on top
    d = ImageDraw.Draw(c)
    band = pal["accent"]
    while 0.299 * band[0] + 0.587 * band[1] + 0.114 * band[2] > 105:  # dark enough for white text
        band = tuple(int(v * 0.85) for v in band)
    d.rounded_rectangle((60, 50, S - 60, 400), radius=40, fill=band + (255,))
    title = title or f"{n} SUBLIMATION PNG DESIGNS"
    f1 = DF.fit(d, title, "bold", S - 220, 170, 70)
    d.text((S / 2, 175), title, font=f1, fill=(255, 255, 255), anchor="mm")
    f2 = DF.fit(d, name, "script", S - 300, 120, 60)
    d.text((S / 2, 310), name, font=f2, fill=(255, 246, 230), anchor="mm")
    # small badges bottom left
    fb = mockups.font("sans_bold", 46)
    for i, txt in enumerate(("SHIRTS", "MUGS", "TUMBLERS")):
        x, y = 90 + i * 300, S - 150
        d.rounded_rectangle((x, y, x + 270, y + 80), radius=40, fill=(255, 255, 255, 235))
        d.text((x + 135, y + 40), txt, font=fb, fill=(60, 50, 45), anchor="mm")
    return c.convert("RGB")


def build(spec, slug):
    style = spec.get("style", "cute illustration")
    palette = spec.get("palette", [])
    rnd = random.Random(slug)
    want = spec.get("count") if isinstance(spec.get("count"), int) else COUNT  # a preset may ask for a bigger bundle
    retro = spec.get("look") == "retro"
    seed = sum(ord(ch) for ch in slug)
    out = []
    for k, ds in enumerate(spec["designs"][:want]):
        phrase = re.sub(r"\s+", " ", str(ds.get("phrase", "")).strip())[:28]
        if not TEXT_OK.match(phrase or ""):
            phrase = spec.get("set_name", "Happy Days")[:28]
        im = images.try_generate(f"{ds['prompt']}, {style}, color palette {', '.join(palette)}, {SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is None:
            continue
        art = trim_alpha(color_to_alpha_background(im))
        art = art.resize((art.width * 3, art.height * 3), Image.LANCZOS)
        layout = LAYOUTS[(k + rnd.randrange(4)) % len(LAYOUTS)]
        dsg = retro_design(art, phrase, k, palette, seed) if retro else design(art, phrase, layout, _ink(palette, k))
        out.append((ds.get("name", phrase), phrase, dsg))
    images.need(len(out), want, ratio=0.75)

    n = len(out)
    safe = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "design"
    files = []
    for i, (nm, ph, dsg) in enumerate(out, 1):
        files.append((f"Designs-3600px/{i:02d}-{safe(ph)}.png", png_bytes(dsg)))
        files.append((f"Mug-Wrap-11oz/{i:02d}-{safe(ph)}-mug.png", png_bytes(mug_wrap(dsg))))
    name = spec.get("set_name", "Sublimation Designs")
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n"
              f"- {n} PNG designs, transparent background, 3600 x 3600 px (12 x 12 in at 300 DPI)\n"
              f"- {n} ready 11 oz mug wraps, 2700 x 1100 px\n\n"
              "BEST FOR: mugs, tumblers, tote bags, pillows and light colored shirts up to about 10 inches wide.\n"
              "Sublimation: print mirrored on sublimation paper. DTF / print on demand: upload the PNG as it is.\n\n"
              "LICENSE: personal use and small business commercial use on up to 500 physical products. "
              "You may not resell, share or redistribute the digital files.\n")
    delivery = make_zips(slug, files, readme)
    dsgs = [d for _, _, d in out]
    tumbler_wrap = Image.new("RGB", (2790, 2460), (255, 255, 255))
    t = dsgs[0].copy()
    t.thumbnail((1250, 2200), Image.LANCZOS)  # the visible front of the tumbler = the middle of the wrap
    tumbler_wrap.paste(t, (1395 - t.width // 2, (2460 - t.height) // 2), t)
    # retro look: the first photos show the print on real-looking shirts (2 extra images); without them (quota) the
    # code-drawn shirts are used
    flat = photo_mock(dsgs[0], "flatlay") if retro else None
    worn = photo_mock(dsgs[1 % n], "worn") if retro else None
    drawn_cover = product_cover(dsgs, n, name, palette, **({"scale": .62, "second": DARK_TEE} if retro else {}))
    mock = [
        ("00-cover.jpg", flat or drawn_cover),
        ("01-bundle.jpg", bundle_cover(dsgs, n, "Sublimation PNG", name, palette, bundle_word="DESIGNS",
                                       sticker=("MUG", "WRAPS", "INCLUDED"),
                                       features=["TRANSPARENT PNG", "COMMERCIAL USE", "SHIRTS & MUGS", "INSTANT DOWNLOAD"])),
        ("02-all.jpg", mockups.grid(dsgs, f"{n} Designs Included", palette, cols=4)),
        ("03-shirts.jpg", worn or tee_mock(dsgs[1 % n], palette, "PERFECT FOR SHIRTS & SWEATSHIRTS",
                                           **({"scale": .62, "second": DARK_TEE} if retro else {}))),
        ("04-mug.jpg", mug_mock(dsgs[2 % n], palette)),
        ("05-tumbler.jpg", mockups.tumbler_mockup(tumbler_wrap, palette, label="TUMBLERS & MORE")),
        ("06-transparent.jpg", mockups.grid(dsgs[:4], "Transparent Background PNG", palette, cols=2, checker=True)),
        ("07-what.jpg", mockups.info_card("WHAT YOU GET", [f"{n} PNG designs, 3600 x 3600 px", f"{n} ready 11 oz mug wraps",
                                                           "Transparent background, 300 DPI", "Instant download (ZIP)"], palette, dsgs[3 % n])),
        ("08-license.jpg", mockups.info_card("COMMERCIAL USE", ["Personal and small business use", "Up to 500 physical products",
                                                                "No reselling of the digital files"], palette, dsgs[4 % n])),
    ]
    if flat is not None:  # the drawn overview (shirt + mug) stays in the listing, after the photo cover
        mock.insert(3, ("02b-products.jpg", drawn_cover))
        mock = mock[:10]  # Etsy shows at most 10 photos
    return {
        "own_cover": True,
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [f"{n} PNG designs with transparent background (3600 x 3600 px, 300 DPI)",
                     f"{n} ready-to-print 11 oz mug wraps (2700 x 1100 px)", "Delivered as ZIP"],
        "details": ["Best for mugs, tumblers, tote bags and light shirts up to about 10 inches wide",
                    "Worn vintage print texture is part of every design" if retro else
                    "Words set in clean fonts, no spelling mistakes"],
        "usage": ["Sublimation (print mirrored), DTF transfers and print on demand",
                  "Unzip the file on a computer before use"],
        "license": "Personal and small business commercial use on up to 500 physical products. Reselling or sharing the digital files is not allowed.",
        "taxonomy": ["Clip Art & Image Files", "Digital Prints"],
        "taxonomy_fallback_id": 6844,
        "is_supply": True,
        "skip_attributes": ["room"],
        "count": n,
    }
