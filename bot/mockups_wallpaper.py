"""Listing images for phone wallpaper packs: phones showing the wallpapers (Pillow only, no image-model quota)."""
from PIL import Image, ImageDraw, ImageOps

from .imgutil import fit_text, font, paste_with_shadow
from .mockups import H, W, _mix, palette_colors
from .mockups_scenes import CREAM, GOLD, _festive_bg, _border, _pill


def _phone(art, height, angle=0):
    """A simple modern phone (black body, rounded screen, camera pill) showing the art."""
    w = int(height * 0.485)
    body = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    r = int(w * 0.17)
    d.rounded_rectangle((0, 0, w - 1, height - 1), radius=r, fill=(22, 22, 24, 255))
    d.rounded_rectangle((3, 3, w - 4, height - 4), radius=r - 3, outline=(90, 90, 96, 255), width=3)
    b = int(w * 0.035)
    sw, sh = w - 2 * b, height - 2 * b
    screen = ImageOps.fit(art.convert("RGB"), (sw, sh), Image.LANCZOS, centering=(0.5, 0.45)).convert("RGBA")
    mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw - 1, sh - 1), radius=r - b, fill=255)
    body.paste(screen, (b, b), mask)
    d = ImageDraw.Draw(body)
    pw, ph = int(w * 0.26), int(w * 0.07)
    d.rounded_rectangle(((w - pw) // 2, b + int(w * 0.04), (w + pw) // 2, b + int(w * 0.04) + ph), radius=ph // 2, fill=(10, 10, 12, 255))
    if angle:
        body = body.rotate(angle, expand=True, resample=Image.BICUBIC)
    return body


def cover(arts, title, count, palette):
    """Big title on top, three phones showing wallpapers, count badge and pills."""
    pal = palette_colors(palette)
    canvas = _festive_bg(pal)
    _border(canvas)
    d = ImageDraw.Draw(canvas)
    tf = fit_text(d, title.upper(), "serif", 1600, 150, 60)
    tw = d.textlength(title.upper(), font=tf)
    d.text(((W - tw) / 2 + 4, 119), title.upper(), font=tf, fill=(0, 0, 0, 160))
    d.text(((W - tw) / 2, 115), title.upper(), font=tf, fill=CREAM + (255,))
    sf = font("sans_bold", 54)
    sub = "PHONE WALLPAPERS"
    d.text(((W - d.textlength(sub, font=sf)) / 2, 115 + tf.size * 1.25), sub, font=sf, fill=GOLD + (255,))
    n = len(arts)
    left = _phone(arts[1 % n], 1050, 9)
    right = _phone(arts[2 % n], 1050, -9)
    mid = _phone(arts[0], 1230, 0)
    paste_with_shadow(canvas, left, (W // 2 - 760, 480), radius=24, offset=(0, 14), opacity=140)
    paste_with_shadow(canvas, right, (W // 2 + 760 - right.width, 480), radius=24, offset=(0, 14), opacity=140)
    paste_with_shadow(canvas, mid, ((W - mid.width) // 2, 400), radius=28, offset=(0, 18), opacity=160)
    d = ImageDraw.Draw(canvas)
    # count badge, left
    cx, cy, r = 580, 1000, 165
    d.ellipse((cx - r - 12, cy - r - 12, cx + r + 12, cy + r + 12), fill=CREAM + (255,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD + (255,))
    ink = _mix(pal["text"], (40, 8, 8), 0.4) + (255,)
    nf = font("sans_bold", 170)
    d.text((cx - d.textlength(str(count), font=nf) / 2, cy - 135), str(count), font=nf, fill=ink)
    lf = font("sans_bold", 38)
    d.text((cx - d.textlength("WALLPAPERS", font=lf) / 2, cy + 45), "WALLPAPERS", font=lf, fill=ink)
    pf = font("sans_bold", 48)
    dark = _mix(pal["text"], (30, 5, 5), 0.5)
    items = [("iPHONE + ANDROID + iPAD", CREAM), ("INSTANT DOWNLOAD", GOLD)]
    pad, gap = 36, 40
    widths = [d.textlength(t, font=pf) + 2 * pad for t, _ in items]
    x = (W - (sum(widths) + gap * (len(items) - 1))) / 2
    for (t, bg), wd in zip(items, widths):
        _pill(d, x + wd / 2, H - 120, t, pf, dark, bg + (255,), pad=pad)
        x += wd + gap
    return canvas.convert("RGB")


def mosaic(arts, title, count, palette):
    """All wallpapers as small phones in two rows."""
    pal = palette_colors(palette)
    canvas = _festive_bg(pal, seed=9)
    _border(canvas)
    d = ImageDraw.Draw(canvas)
    head = f"{count} WALLPAPERS INCLUDED"
    hf = fit_text(d, head, "serif", W - 500, 110, 50)
    d.text(((W - d.textlength(head, font=hf)) / 2, 100), head, font=hf, fill=CREAM + (255,))
    n = len(arts)
    per_row = 5 if n > 5 else n
    rows = [list(range(i, min(i + per_row, n))) for i in range(0, n, per_row)]
    ph = 600 if len(rows) > 1 else 1000
    pw = int(ph * 0.485)
    gap = 48
    top = 300 if len(rows) > 1 else 330
    for ri, row in enumerate(rows):
        total = len(row) * pw + (len(row) - 1) * gap
        x = (W - total) // 2
        y = top + ri * (ph + 70)
        for idx in row:
            paste_with_shadow(canvas, _phone(arts[idx], ph), (x, y), radius=16, offset=(0, 10), opacity=130)
            x += pw + gap
    return canvas.convert("RGB")
