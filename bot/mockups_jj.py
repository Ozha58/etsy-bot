"""Listing images for junk journal kits (Pillow only). Key content stays inside the centre
square (x 300-2100) because Etsy's phone/search views crop to it."""
import random

from PIL import Image, ImageDraw, ImageFilter

from . import ephemera as E
from .imgutil import fit_text, font
from .mockups import H, W

DARK = (46, 36, 28)
CREAM = (246, 238, 220)
GOLD = (196, 160, 92)
INK = (70, 48, 30)


def _desk(seed=1):
    """Dark vintage desk background."""
    bg = E.aged_paper(W, H, (88, 66, 48), seed=seed, stains=False)
    shade = Image.new("RGBA", (W, H), (20, 14, 10, 70))
    out = bg.convert("RGBA")
    out.alpha_composite(shade)
    return out


def _scatter(canvas, pieces, boxes, rnd):
    for p, (x, y, w, h, ang) in zip(pieces, boxes):
        p = p.convert("RGBA").copy()
        p.thumbnail((w, h), Image.LANCZOS)
        p = p.rotate(ang, expand=True, resample=Image.BICUBIC)
        E.shadow_paste(canvas, p, (x - p.width // 2, y - p.height // 2), opacity=120)


def _panel(canvas, title, count, sub):
    d = ImageDraw.Draw(canvas)
    pw, ph = 1360, 520
    px, py = (W - pw) // 2, H - ph - 150
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((px, py + 16, px + pw, py + ph + 16), 46, fill=(0, 0, 0, 130))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(20)))
    paper = E.aged_paper(pw, ph, CREAM, seed=9, stains=False).convert("RGBA")
    m = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, pw - 1, ph - 1), 46, fill=255)
    paper.putalpha(m)
    canvas.alpha_composite(paper, (px, py))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((px + 18, py + 18, px + pw - 18, py + ph - 18), 34, outline=GOLD + (255,), width=4)
    # badge
    cx, cy, r = W // 2, py, 128
    d.ellipse((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10), fill=CREAM + (255,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD + (255,))
    nf = font("sans_bold", 120 if count < 100 else 96)
    d.text((cx - d.textlength(str(count), font=nf) / 2, cy - 98), str(count), font=nf, fill=DARK + (255,))
    lf = font("sans_bold", 36)
    d.text((cx - d.textlength("PIECES", font=lf) / 2, cy + 36), "PIECES", font=lf, fill=DARK + (255,))
    sf = font("serif_italic", 60)
    d.text((W / 2 - d.textlength("printable junk journal kit", font=sf) / 2, py + 150), "printable junk journal kit",
           font=sf, fill=INK + (255,))
    t = title.upper()
    tf = fit_text(d, t, "serif", pw - 160, 130, 52)
    d.text((W / 2 - d.textlength(t, font=tf) / 2, py + 235), t, font=tf, fill=DARK + (255,))
    bf = fit_text(d, sub, "sans_bold", pw - 200, 40, 26)
    d.text((W / 2 - d.textlength(sub, font=bf) / 2, py + ph - 110), sub, font=bf, fill=INK + (255,))


def cover(parts, title, count):
    rnd = random.Random(len(title))
    canvas = _desk(seed=3)
    pieces = [parts["pages"][0], parts["cards"][0], parts["tags"][0], parts["stamps"][0], parts["stickers"][0],
              parts["papers"][0], parts["cards"][1], parts["stamps"][1], parts["tags"][1], parts["stickers"][1],
              parts["stamps"][2], parts["pages"][1]]
    boxes = [(560, 560, 700, 900, -6), (1220, 420, 560, 640, 4), (1880, 560, 420, 760, 8), (900, 300, 300, 330, -10),
             (1560, 820, 440, 440, -5), (240, 900, 520, 520, 6), (2160, 1100, 520, 640, -7), (1520, 300, 280, 310, 12),
             (330, 1450, 380, 700, -12), (2080, 1530, 420, 420, 9), (700, 1080, 260, 290, 7), (1800, 1500, 560, 720, 3)]
    _scatter(canvas, pieces, boxes, rnd)
    _panel(canvas, title, count, "PAGES • CARDS • TAGS • STAMPS • STICKERS • PAPERS")
    return canvas.convert("RGB")


def inside(parts, counts):
    """What's included: one labelled tile per group."""
    canvas = Image.new("RGBA", (W, H), CREAM + (255,))
    canvas = E.aged_paper(W, H, CREAM, seed=21, stains=False).convert("RGBA")
    d = ImageDraw.Draw(canvas)
    hf = font("serif", 96)
    head = "WHAT'S INSIDE"
    d.text((W / 2 - d.textlength(head, font=hf) / 2, 90), head, font=hf, fill=DARK + (255,))
    d.line((W / 2 - 200, 220, W / 2 + 200, 220), fill=GOLD + (255,), width=5)
    groups = [("pages", "Journal pages"), ("cards", "Journaling cards"), ("tags", "Tags"), ("stamps", "Postage stamps"),
              ("stickers", "Stickers"), ("cutouts", "Cutouts PNG"), ("papers", "Digital papers"), ("sheets", "Printable sheets")]
    groups = [g for g in groups if counts.get(g[0])]
    cols = 4
    cw, ch = 440, 600
    x0 = (W - cols * cw) // 2
    lf = font("sans_bold", 40)
    nf = font("serif", 60)
    for i, (key, label) in enumerate(groups):
        cx = x0 + (i % cols) * cw + cw // 2
        cy = 300 + (i // cols) * (ch + 40)
        src = parts.get(key) or parts["pages"]
        im = src[0].convert("RGBA").copy()
        im.thumbnail((cw - 90, ch - 210), Image.LANCZOS)
        E.shadow_paste(canvas, im, (cx - im.width // 2, cy + (ch - 210 - im.height) // 2), opacity=90)
        d = ImageDraw.Draw(canvas)
        n = str(counts[key])
        d.text((cx - d.textlength(n, font=nf) / 2, cy + ch - 190), n, font=nf, fill=GOLD + (255,))
        d.text((cx - d.textlength(label, font=lf) / 2, cy + ch - 110), label, font=lf, fill=DARK + (255,))
    return canvas.convert("RGB")


def showcase(pieces, heading, sub, seed=5, cols=None):
    """A flat lay of one group of pieces on the desk with a heading."""
    canvas = _desk(seed=seed)
    d = ImageDraw.Draw(canvas)
    hf = font("serif", 92)
    d.text((W / 2 - d.textlength(heading, font=hf) / 2, 80), heading, font=hf, fill=CREAM + (255,))
    sf = font("sans", 42)
    d.text((W / 2 - d.textlength(sub, font=sf) / 2, 200), sub, font=sf, fill=GOLD + (255,))
    n = len(pieces)
    cols = cols or min(4, n)
    rows = (n + cols - 1) // cols
    area_w, area_h = 1760, H - 360
    cw, ch = area_w // cols, area_h // rows
    x0 = (W - area_w) // 2
    rnd = random.Random(seed)
    for i, p in enumerate(pieces):
        p = p.convert("RGBA").copy()
        p.thumbnail((int(cw * 0.88), int(ch * 0.88)), Image.LANCZOS)
        p = p.rotate(rnd.uniform(-4, 4), expand=True, resample=Image.BICUBIC)
        cx = x0 + (i % cols) * cw + cw // 2
        cy = 300 + (i // cols) * ch + ch // 2
        E.shadow_paste(canvas, p, (cx - p.width // 2, cy - p.height // 2), opacity=120)
    return canvas.convert("RGB")
