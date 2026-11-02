"""Eye-catching listing images for scene packs (Pillow only, no image-model quota)."""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .imgutil import fit_text, font, paste_with_shadow
from .mockups import H, W, _mix, palette_colors

GOLD = (222, 186, 102)
CREAM = (250, 244, 232)


def _festive_bg(pal, seed=4):
    base = _mix(pal["text"], (60, 10, 14), 0.55)
    glow = _mix(base, (255, 255, 255), 0.18)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.sqrt(((xx - W / 2) / (W * 0.65)) ** 2 + ((yy - H / 2) / (H * 0.65)) ** 2).clip(0, 1)[..., None]
    arr = np.array(glow, np.float32) * (1 - dist) + np.array(base, np.float32) * dist
    img = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(110):
        x, y, r = rnd.randrange(W), rnd.randrange(H), rnd.randrange(3, 12)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randrange(50, 150)))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.3)))
    return img


def _border(canvas):
    d = ImageDraw.Draw(canvas)
    d.rectangle((34, 34, W - 35, H - 35), outline=GOLD + (255,), width=6)
    d.rectangle((58, 58, W - 59, H - 59), outline=GOLD + (140,), width=2)


def _square(im, size, border=14, angle=0):
    t = ImageOps.fit(im.convert("RGB"), (size, size), Image.LANCZOS)
    t = ImageOps.expand(t, border=border, fill=CREAM)
    t = t.convert("RGBA")
    if angle:
        t = t.rotate(angle, expand=True, resample=Image.BICUBIC)
    return t


def _pill(d, cx, cy, text, f, fg, bg, pad=44):
    tw = d.textlength(text, font=f)
    h = f.size + 36
    d.rounded_rectangle((cx - tw / 2 - pad, cy - h / 2, cx + tw / 2 + pad, cy + h / 2), radius=int(h / 2), fill=bg)
    d.text((cx - tw / 2, cy - f.size * 0.62), text, font=f, fill=fg)


def hero_cover(ims, title, count, palette):
    """One big hero scene + four smaller ones, big title, count badge, feature pills."""
    pal = palette_colors(palette)
    canvas = _festive_bg(pal)
    _border(canvas)
    d = ImageDraw.Draw(canvas)
    n = len(ims)
    pick = lambda i: ims[i % n]
    # title
    tf = fit_text(d, title.upper(), "serif", W - 520, 160, 70)
    tw = d.textlength(title.upper(), font=tf)
    d.text(((W - tw) / 2, 95), title.upper(), font=tf, fill=CREAM + (255,))
    d.line((W / 2 - 260, 95 + tf.size * 1.25, W / 2 + 260, 95 + tf.size * 1.25), fill=GOLD + (255,), width=6)
    # hero + 2x2
    hero = _square(pick(0), 1020, 16, -2)
    paste_with_shadow(canvas, hero, (140, 390), radius=30, offset=(14, 28), opacity=170)
    pos = [(1290, 395, 3), (1810, 395, -2), (1290, 925, -3), (1810, 925, 2)]
    for k, (x, y, a) in enumerate(pos, 1):
        t = _square(pick(k), 470, 12, a)
        paste_with_shadow(canvas, t, (x, y), radius=22, offset=(10, 20), opacity=160)
    # count badge
    cx, cy, r = 1150, 430, 150
    d.ellipse((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10), fill=CREAM + (255,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD + (255,))
    nf = font("sans_bold", 140)
    d.text((cx - d.textlength(str(count), font=nf) / 2, cy - 112), str(count), font=nf, fill=_mix(pal["text"], (40, 8, 8), 0.4) + (255,))
    lf = font("sans_bold", 52)
    d.text((cx - d.textlength("JPG", font=lf) / 2, cy + 38), "JPG", font=lf, fill=_mix(pal["text"], (40, 8, 8), 0.4) + (255,))
    # pills, laid out left to right with equal gaps
    pf = font("sans_bold", 50)
    dark = _mix(pal["text"], (30, 5, 5), 0.5)
    items = [("4096 x 4096 px", CREAM), ("300 DPI  PRINT READY", CREAM), ("INSTANT DOWNLOAD", GOLD)]
    pad, gap = 36, 40
    widths = [d.textlength(t, font=pf) + 2 * pad for t, _ in items]
    x = (W - (sum(widths) + gap * (len(items) - 1))) / 2
    for (t, bg), w in zip(items, widths):
        _pill(d, x + w / 2, 1595, t, pf, dark, bg + (255,), pad=pad)
        x += w + gap
    return canvas.convert("RGB")


def mosaic(ims, title, count, palette):
    """Edge-to-edge wall of scenes with a title band: shows the whole pack at a glance."""
    pal = palette_colors(palette)
    canvas = _festive_bg(pal, seed=8)
    cols = 5
    rows = math.ceil(min(len(ims), 15) / cols)
    cell = W // cols
    n = len(ims)
    for i in range(rows * cols):
        r, c = divmod(i, cols)
        t = ImageOps.fit(ims[i % n].convert("RGB"), (cell, cell), Image.LANCZOS).convert("RGBA")
        canvas.alpha_composite(t, (c * cell, r * cell))
    d = ImageDraw.Draw(canvas)
    y0 = rows * cell
    d.rectangle((0, y0, W, H), fill=_mix(pal["text"], (60, 10, 14), 0.55) + (255,))
    d.line((0, y0, W, y0), fill=GOLD + (255,), width=8)
    tf = fit_text(d, f"{count} ILLUSTRATIONS  •  {title.upper()}", "serif", W - 200, 96, 46)
    text = f"{count} ILLUSTRATIONS  •  {title.upper()}"
    d.text(((W - d.textlength(text, font=tf)) / 2, y0 + (H - y0) / 2 - tf.size * 0.7), text, font=tf, fill=CREAM + (255,))
    sf = font("sans_medium", 44)
    sub = "Instant download  •  4096 x 4096 px  •  300 DPI"
    d.text(((W - d.textlength(sub, font=sf)) / 2, y0 + (H - y0) / 2 + 40), sub, font=sf, fill=GOLD + (255,))
    return canvas.convert("RGB")


def single_cover(ims, title, count, palette):
    """One big full-bleed scene as the cover, with a dark fade at the bottom for title and pills."""
    pal = palette_colors(palette)
    canvas = ImageOps.fit(ims[0].convert("RGB"), (W, H), Image.LANCZOS, centering=(0.5, 0.40)).convert("RGBA")
    ys = np.arange(H, dtype=np.float32)[:, None]
    alpha = (np.clip((ys - H * 0.50) / (H * 0.50), 0, 1) ** 1.2 * 240).astype(np.uint8)
    shade = Image.new("RGBA", (W, H), _mix(pal["text"], (25, 5, 8), 0.7) + (255,))
    shade.putalpha(Image.fromarray(np.repeat(alpha, W, axis=1)))
    canvas.alpha_composite(shade)
    d = ImageDraw.Draw(canvas)
    d.rectangle((34, 34, W - 35, H - 35), outline=GOLD + (255,), width=6)
    # title
    tf = fit_text(d, title.upper(), "serif", W - 360, 170, 70)
    tw = d.textlength(title.upper(), font=tf)
    ty = H - 450
    d.text(((W - tw) / 2 + 4, ty + 4), title.upper(), font=tf, fill=(0, 0, 0, 160))
    d.text(((W - tw) / 2, ty), title.upper(), font=tf, fill=CREAM + (255,))
    d.line((W / 2 - 280, ty + tf.size * 1.3, W / 2 + 280, ty + tf.size * 1.3), fill=GOLD + (255,), width=6)
    # count badge, top right
    cx, cy, r = W - 280, 280, 190
    d.ellipse((cx - r - 12, cy - r - 12, cx + r + 12, cy + r + 12), fill=CREAM + (255,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD + (255,))
    ink = _mix(pal["text"], (40, 8, 8), 0.4) + (255,)
    nf = font("sans_bold", 190)
    d.text((cx - d.textlength(str(count), font=nf) / 2, cy - 150), str(count), font=nf, fill=ink)
    lf = font("sans_bold", 66)
    d.text((cx - d.textlength("JPG", font=lf) / 2, cy + 50), "JPG", font=lf, fill=ink)
    # pills
    pf = font("sans_bold", 50)
    dark = _mix(pal["text"], (30, 5, 5), 0.5)
    items = [("4096 x 4096 px", CREAM), ("300 DPI  PRINT READY", CREAM), ("INSTANT DOWNLOAD", GOLD)]
    pad, gap = 36, 40
    widths = [d.textlength(t, font=pf) + 2 * pad for t, _ in items]
    x = (W - (sum(widths) + gap * (len(items) - 1))) / 2
    for (t, bg), w in zip(items, widths):
        _pill(d, x + w / 2, H - 125, t, pf, dark, bg + (255,), pad=pad)
        x += w + gap
    return canvas.convert("RGB")
