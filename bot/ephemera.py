"""Vintage junk-journal pieces made with Pillow from a few AI images (no extra image quota).

Every function returns a PIL image at print size (300 DPI).
"""
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from . import config

PAPER = (236, 224, 198)
CLEAN_PAPER = (250, 247, 241)


def vintage():
    try:
        return bool(config.settings().get("vintage_look", False))
    except Exception:
        return False
INK = (92, 64, 40)
SEPIA = (112, 78, 46)


# ---------------- paper & edges ----------------

def _noise(w, h, scale, rnd):
    small = np.array([[rnd.random() for _ in range(max(2, w // scale))] for _ in range(max(2, h // scale))], np.float32)
    return np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255


def aged_paper(w, h, tint=PAPER, seed=1, stains=True):
    rnd = random.Random(seed)
    if not vintage():
        if tint == PAPER:
            tint = CLEAN_PAPER
        stains = False
    base = np.ones((h, w, 3), np.float32) * np.array(tint, np.float32)
    blot = _noise(w, h, max(60, w // 6), rnd) - 0.5
    grain = np.random.default_rng(seed).normal(0, 1, (h, w)).astype(np.float32)
    shade = blot * 14 + grain * 4
    if not vintage():
        shade = blot * 5 + grain * 2
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    vig = np.sqrt(((xx - w / 2) / (w * 0.62)) ** 2 + ((yy - h / 2) / (h * 0.62)) ** 2)
    shade -= np.clip(vig - 0.55, 0, 1) * (70 if vintage() else 18)
    arr = base + shade[..., None] * np.array([1.0, 0.92, 0.78], np.float32)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if stains:
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for _ in range(rnd.randint(2, 5)):
            r = rnd.randint(w // 14, w // 5)
            x, y = rnd.randint(0, w), rnd.randint(0, h)
            d.ellipse((x - r, y - r, x + r, y + r), outline=(120, 80, 40, rnd.randint(18, 40)), width=max(3, r // 18))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(140, 100, 50, rnd.randint(6, 14)))
        img = Image.alpha_composite(img.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(max(2, w // 500)))).convert("RGB")
    return img


def tinted(color, w, h, seed):
    mix = tuple(int(c * 0.55 + p * 0.45) for c, p in zip(color, PAPER))
    return aged_paper(w, h, mix, seed, stains=False)


def deckle_mask(w, h, depth=None, seed=1):
    """Soft torn/deckled edge mask (L)."""
    rnd = random.Random(seed)
    depth = depth or max(6, min(w, h) // 45)
    pts = []
    step = max(6, depth)
    for x in range(0, w + step, step):
        pts.append((min(x, w), rnd.randint(0, depth)))
    for y in range(0, h + step, step):
        pts.append((w - rnd.randint(0, depth), min(y, h)))
    for x in range(w, -step, -step):
        pts.append((max(x, 0), h - rnd.randint(0, depth)))
    for y in range(h, -step, -step):
        pts.append((rnd.randint(0, depth), max(y, 0)))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m.filter(ImageFilter.GaussianBlur(1.2))


def sepia_print(img, amount=0.35):
    """Make an AI illustration look like an old print: warm, slightly faded, fine grain."""
    rgb = img.convert("RGB")
    if not vintage():
        return rgb
    g = ImageOps.grayscale(rgb)
    sep = ImageOps.colorize(g, (60, 40, 25), (250, 238, 210))
    out = Image.blend(rgb, sep, amount)
    arr = np.asarray(out, np.float32)
    arr = arr * 0.94 + np.array(PAPER, np.float32) * 0.06
    arr += np.random.default_rng(3).normal(0, 3, arr.shape[:2])[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def shadow_paste(canvas, piece, xy, blur=None, offset=None, opacity=90):
    """piece: RGBA. Pastes with a soft drop shadow."""
    blur = blur or max(4, piece.width // 60)
    offset = offset or (max(3, piece.width // 120), max(4, piece.width // 90))
    a = piece.split()[-1]
    sh = Image.new("RGBA", piece.size, (40, 25, 10, 0))
    sh.putalpha(a.point(lambda v: v * opacity // 255))
    pad = blur * 3
    big = Image.new("RGBA", (piece.width + pad * 2, piece.height + pad * 2), (0, 0, 0, 0))
    big.paste(sh, (pad, pad), sh)
    big = big.filter(ImageFilter.GaussianBlur(blur))
    x, y = int(xy[0]), int(xy[1])
    canvas.alpha_composite(big, (max(0, x - pad + offset[0]), max(0, y - pad + offset[1])))
    canvas.alpha_composite(piece, (x, y))


def _fit(img, w, h, centering=(0.5, 0.5)):
    return ImageOps.fit(img.convert("RGB"), (w, h), Image.LANCZOS, centering=centering)


def _frame_lines(d, box, color, width, gap):
    x0, y0, x1, y1 = box
    d.rectangle((x0, y0, x1, y1), outline=color, width=width)
    d.rectangle((x0 + gap, y0 + gap, x1 - gap, y1 - gap), outline=color, width=max(1, width // 2))


def _corner_ornaments(d, box, color, size):
    x0, y0, x1, y1 = box
    for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line((cx, cy + sy * size, cx, cy, cx + sx * size, cy), fill=color, width=max(2, size // 10))
        d.ellipse((cx + sx * size // 3 - size // 8, cy + sy * size // 3 - size // 8,
                   cx + sx * size // 3 + size // 8, cy + sy * size // 3 + size // 8), fill=color)


# ---------------- pieces ----------------

def page(scene, size=(2550, 3300), seed=1, layout=0, accent=SEPIA):
    """Full journal page (US Letter @300 DPI)."""
    w, h = size
    canvas = aged_paper(w, h, seed=seed).convert("RGBA")
    d = ImageDraw.Draw(canvas)
    m = int(w * 0.06)
    _frame_lines(d, (m, m, w - m, h - m), accent + (150,), 6, 22)
    if layout % 2 == 0:  # big print in the middle, deckled edge
        pw, ph = int(w * 0.74), int(w * 0.74)
        art = sepia_print(_fit(scene, pw, ph), 0.25).convert("RGBA")
        art.putalpha(deckle_mask(pw, ph, seed=seed))
        shadow_paste(canvas, art.rotate((seed % 5 - 2) * 0.8, expand=True, resample=Image.BICUBIC), ((w - pw) // 2, int(h * 0.16)))
        y = int(h * 0.16) + ph + int(h * 0.07)
        d.line((w * 0.3, y, w * 0.7, y), fill=accent + (180,), width=5)
        d.line((w * 0.38, y + 26, w * 0.62, y + 26), fill=accent + (120,), width=3)
    else:  # full faded background illustration
        art = sepia_print(_fit(scene, w - 2 * m - 60, h - 2 * m - 60), 0.55).convert("RGBA")
        art.putalpha(art.split()[-1].point(lambda v: int(v * 0.42)))
        canvas.alpha_composite(art, (m + 30, m + 30))
        bw, bh = int(w * 0.5), int(h * 0.12)
        label = aged_paper(bw, bh, seed=seed + 7, stains=False).convert("RGBA")
        label.putalpha(deckle_mask(bw, bh, seed=seed + 3))
        shadow_paste(canvas, label, ((w - bw) // 2, int(h * 0.72)))
        ld = ImageDraw.Draw(canvas)
        for i in range(3):
            yy = int(h * 0.72) + int(bh * (0.32 + i * 0.2))
            ld.line((w * 0.3, yy, w * 0.7, yy), fill=accent + (110,), width=3)
    return canvas.convert("RGB")


def card(scene, size=(900, 1200), seed=1, accent=SEPIA):
    """3x4 inch journaling card."""
    w, h = size
    canvas = aged_paper(w, h, seed=seed + 50).convert("RGBA")
    d = ImageDraw.Draw(canvas)
    m = int(w * 0.07)
    iw, ih = w - 2 * m, int(h * 0.62)
    art = sepia_print(_fit(scene, iw, ih, centering=(0.5, 0.4)), 0.2)
    canvas.paste(art, (m, m))
    d.rectangle((m, m, m + iw, m + ih), outline=accent + (200,), width=4)
    box = (m // 2, m // 2, w - m // 2, h - m // 2)
    _frame_lines(d, box, accent + (150,), 3, 10)
    _corner_ornaments(d, (m, m + ih + 30, w - m, h - m), accent + (170,), 28)
    for i in range(3):  # journaling lines
        yy = m + ih + 90 + i * int((h - m - ih - 140) / 3)
        d.line((m + 40, yy, w - m - 40, yy), fill=accent + (110,), width=2)
    return canvas.convert("RGB")


def tag(art, size=(750, 1500), seed=1, accent=SEPIA, is_object=False):
    """Shipping tag with hole and reinforcement ring (RGBA)."""
    w, h = size
    cut = int(w * 0.22)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.polygon([(cut, 0), (w - cut, 0), (w, cut), (w, h), (0, h), (0, cut)], fill=255)
    hx, hy, hr = w // 2, int(cut * 0.85), int(w * 0.06)
    md.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=0)
    body = aged_paper(w, h, seed=seed + 90).convert("RGBA")
    if is_object:
        obj = art.copy()
        obj.thumbnail((int(w * 0.8), int(h * 0.55)), Image.LANCZOS)
        shadow_paste(body, obj, ((w - obj.width) // 2, int(h * 0.3) + (int(h * 0.55) - obj.height) // 2), opacity=60)
    else:
        iw, ih = int(w * 0.78), int(h * 0.56)
        pic = sepia_print(_fit(art, iw, ih), 0.25).convert("RGBA")
        pic.putalpha(deckle_mask(iw, ih, seed=seed + 4))
        shadow_paste(body, pic, ((w - iw) // 2, int(h * 0.3)))
    d = ImageDraw.Draw(body)
    d.ellipse((hx - hr - 26, hy - hr - 26, hx + hr + 26, hy + hr + 26), fill=(205, 182, 140, 255), outline=accent + (200,), width=4)
    d.line((int(w * 0.18), int(h * 0.92), int(w * 0.82), int(h * 0.92)), fill=accent + (150,), width=3)
    d.polygon([(cut, 6), (w - cut, 6), (w - 6, cut), (w - 6, h - 6), (6, h - 6), (6, cut)], outline=accent + (160,))
    body.putalpha(mask)
    return body


def stamp(art, size=(600, 720), seed=1, color=(170, 60, 50), is_object=False):
    """Postage stamp with perforated edge (RGBA, no text)."""
    w, h = size
    r = max(10, w // 36)
    body = aged_paper(w, h, (246, 238, 220), seed=seed + 120, stains=False).convert("RGBA")
    m = int(w * 0.11)
    inner = (m, m, w - m, h - m)
    if is_object:
        bg = tinted(color, inner[2] - inner[0], inner[3] - inner[1], seed).convert("RGBA")
        obj = art.copy()
        obj.thumbnail((int(bg.width * 0.82), int(bg.height * 0.82)), Image.LANCZOS)
        bg.alpha_composite(obj, ((bg.width - obj.width) // 2, (bg.height - obj.height) // 2))
        body.alpha_composite(bg, inner[:2])
    else:
        body.paste(sepia_print(_fit(art, inner[2] - inner[0], inner[3] - inner[1]), 0.3), inner[:2])
    d = ImageDraw.Draw(body)
    d.rectangle(inner, outline=color + (255,), width=max(4, w // 90))
    d.rectangle((inner[0] - 14, inner[1] - 14, inner[2] + 14, inner[3] + 14), outline=color + (150,), width=2)
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    for x in range(0, w + 1, r * 3):
        md.ellipse((x - r, -r, x + r, r), fill=0)
        md.ellipse((x - r, h - r, x + r, h + r), fill=0)
    for y in range(0, h + 1, r * 3):
        md.ellipse((-r, y - r, r, y + r), fill=0)
        md.ellipse((w - r, y - r, w + r, y + r), fill=0)
    body.putalpha(mask)
    return body


def sticker(obj, outline=None):
    """Die-cut sticker: object with a white border and soft shadow (RGBA)."""
    outline = outline or max(14, obj.width // 40)
    pad = outline * 3
    a = obj.split()[-1]
    big = Image.new("L", (obj.width + pad * 2, obj.height + pad * 2), 0)
    big.paste(a, (pad, pad))
    grown = big.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(outline * 2 + 1)).filter(ImageFilter.GaussianBlur(1.5))
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    sh = Image.new("RGBA", big.size, (40, 30, 20, 0))
    sh.putalpha(grown.point(lambda v: v * 70 // 255).filter(ImageFilter.GaussianBlur(outline // 2 + 2)))
    out.alpha_composite(sh, (outline // 3, outline // 2))
    white = Image.new("RGBA", big.size, (255, 253, 248, 0))
    white.putalpha(grown)
    out.alpha_composite(white)
    out.alpha_composite(obj, (pad, pad))
    return out


def sticker_sheet(stickers, size=(2550, 3300), seed=1):
    """Printable sheet (US Letter) with the stickers laid out."""
    w, h = size
    sheet = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    cols = 2 if len(stickers) <= 4 else 3
    rows = math.ceil(len(stickers) / cols)
    cw, ch = (w - 300) // cols, (h - 300) // rows
    for i, s in enumerate(stickers):
        s = s.copy()
        s.thumbnail((int(cw * 0.86), int(ch * 0.86)), Image.LANCZOS)
        cx = 150 + (i % cols) * cw + (cw - s.width) // 2
        cy = 150 + (i // cols) * ch + (ch - s.height) // 2
        sheet.alpha_composite(s, (cx, cy))
    return sheet.convert("RGB")


def tossed_paper(objs, size=3600, seed=1, tint=PAPER, scale=0.13):
    """Seamless digital paper: objects scattered with wrap-around on aged paper."""
    rnd = random.Random(seed)
    base = aged_paper(size, size, tint, seed=seed + 200, stains=False).convert("RGBA")
    # seamless background: blend edges by offset trick
    base = Image.blend(base, ImageChops.offset(base, size // 2, size // 2), 0.5)
    n = 18
    cells = int(math.sqrt(n)) + 1
    cell = size / cells
    for i in range(cells * cells):
        o = objs[i % len(objs)].copy()
        target = int(size * scale * rnd.uniform(0.8, 1.15))
        o.thumbnail((target, target), Image.LANCZOS)
        o = o.rotate(rnd.uniform(-25, 25), expand=True, resample=Image.BICUBIC)
        x = int((i % cells) * cell + rnd.uniform(0, cell * 0.5) + ((i // cells) % 2) * cell * 0.5)
        y = int((i // cells) * cell + rnd.uniform(0, cell * 0.4))
        for dx in (-size, 0, size):
            for dy in (-size, 0, size):
                xx, yy = x + dx, y + dy
                if xx + o.width < 0 or yy + o.height < 0 or xx >= size or yy >= size:
                    continue
                l, t = max(0, -xx), max(0, -yy)
                piece = o.crop((l, t, min(o.width, size - xx), min(o.height, size - yy)))
                base.alpha_composite(piece, (max(0, xx), max(0, yy)))
    return base.convert("RGB")


def stripe_paper(color, size=3600, seed=1, kind="stripes"):
    base = aged_paper(size, size, seed=seed + 300, stains=False)
    base = Image.blend(base, ImageChops.offset(base, size // 2, size // 2), 0.5).convert("RGBA")
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = color + (95,)
    if kind == "stripes":
        step = size // 24
        for x in range(0, size, step):
            d.rectangle((x, 0, x + step // 3, size), fill=col)
    elif kind == "dots":
        step = size // 18
        r = step // 6
        for yi, y in enumerate(range(0, size, step)):
            off = step // 2 if yi % 2 else 0
            for x in range(off, size + step, step):
                d.ellipse((x - r, y - r, x + r, y + r), fill=col)
    else:  # gingham
        step = size // 20
        for x in range(0, size, step * 2):
            d.rectangle((x, 0, x + step, size), fill=color + (55,))
        for y in range(0, size, step * 2):
            d.rectangle((0, y, size, y + step), fill=color + (55,))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1)))
    return base.convert("RGB")
