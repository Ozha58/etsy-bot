"""Personalized name coloring pages (a preset asks for it with "look": "coloring").

The buyer types a child's name; every page shows that name in big hollow letters to colour in, a line-art drawing,
a short caption and a few stars to colour. Delivered per order as two print-ready PDFs (US Letter and A4).

Same order flow as the other custom products: the line drawings are kept in the product's assets
(custom__art-N.png) and the name is written by code, so the letters are always correct and sharp.
Drawing from a buyer's photo is NOT possible here: the artwork is made once, from text, before any order."""
import io
import math
import random
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import images, mockups
from ..imgutil import font, jpeg_bytes, make_zips, paste_with_shadow, png_bytes, thumb_b64
from . import coloring, custom_festive as F
from . import sublimation as SB

LETTER, A4 = coloring.LETTER, coloring.A4
PHOTO = F.PHOTO
INK = (38, 34, 58)
WHITE = (255, 255, 255)
# photo backgrounds: bright crayon colours (inner, outer)
BG = {"yellow": ((255, 214, 92), (247, 168, 38)), "blue": ((96, 190, 240), (36, 120, 200)),
      "coral": ((255, 138, 120), (226, 78, 82)), "mint": ((120, 214, 176), (36, 150, 124)),
      "purple": ((170, 140, 240), (104, 76, 190))}
CRAYONS = [(232, 62, 72), (255, 150, 40), (250, 204, 50), (70, 180, 100), (60, 140, 220), (150, 100, 210), (240, 110, 170)]


# ---------------------------------------------------------------- the printable page
def lineart(im):
    """An AI drawing -> pure black lines on white (mode L), cut to the drawing itself."""
    g = im.convert("L")
    bw = g.point(lambda v: 255 if v > 165 else 0)
    box = bw.point(lambda v: 255 - v).getbbox()
    return bw.crop(box) if box else bw


def _hollow(text, max_w, max_h, start):
    """The name in fat hollow letters (black outline, white inside) on white, 1 or 2 lines, as large as fits."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    best = None
    for lines in ([text], SB._lines(text, 2)):
        size = start
        while size > 90:
            f = F._font("rounded", size)
            line = max(6, size // 22)
            boxes = [probe.textbbox((0, 0), ln, font=f, stroke_width=line) for ln in lines]
            w = max(b[2] - b[0] for b in boxes)
            h = sum(b[3] - b[1] for b in boxes) + int(size * 0.10) * (len(lines) - 1)
            if w <= max_w and h <= max_h:
                break
            size -= max(8, size // 20)
        if best is None or size > best[0]:
            best = (size, lines)
        if len(lines) == 1 and size >= start * 0.55:
            break
    size, lines = best
    f = F._font("rounded", size)
    line, gap = max(6, size // 22), int(size * 0.10)
    boxes = [probe.textbbox((0, 0), ln, font=f, stroke_width=line) for ln in lines]
    w = max(b[2] - b[0] for b in boxes) + 8
    h = sum(b[3] - b[1] for b in boxes) + gap * (len(lines) - 1) + 8
    out = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(out)
    y = 4
    for ln, b in zip(lines, boxes):
        d.text(((w - (b[2] - b[0])) / 2 - b[0], y - b[1]), ln, font=f, fill=255, stroke_width=line, stroke_fill=0)
        y += b[3] - b[1] + gap
    return out


def _star_outline(d, cx, cy, r, width):
    pts = [(cx + math.cos(math.pi / 5 * i - math.pi / 2) * (r if i % 2 == 0 else r * 0.46),
            cy + math.sin(math.pi / 5 * i - math.pi / 2) * (r if i % 2 == 0 else r * 0.46)) for i in range(10)]
    d.polygon(pts, fill=255)
    d.line(pts + pts[:2], fill=0, width=width, joint="curve")


def page_framed(art, name, caption, k, size=LETTER):
    """First layout (products made before "page_style": "bubble"): a framed page, straight name, small caption."""
    pw, ph = size
    pg = Image.new("L", size, 255)
    d = ImageDraw.Draw(pg)
    m = int(pw * 0.045)
    lw = max(8, pw // 260)
    d.rounded_rectangle((m, m, pw - m, ph - m), radius=int(pw * 0.04), outline=0, width=lw)
    inner = int(pw * 0.085)
    box_w, box_h = pw - 2 * inner, ph - 2 * inner
    nm = _hollow(name, box_w - 2 * int(pw * 0.10), int(ph * 0.21), int(ph * 0.20))
    cap = None
    if caption:
        f = font("sans_bold", int(pw * 0.034))
        cap = caption.upper()
        while d.textlength(cap, font=f) > box_w * 0.8 and f.size > 40:
            f = font("sans_bold", f.size - 4)
    cap_h = int(pw * 0.06) if cap else 0
    gap = int(ph * 0.018)
    a = art.convert("L")
    room = box_h - nm.height - cap_h - 2 * gap
    s = min(box_w / a.width, room / a.height)
    a = a.resize((max(1, int(a.width * s)), max(1, int(a.height * s))), Image.LANCZOS).point(lambda v: 255 if v > 150 else 0)
    total = nm.height + gap + a.height + (gap + cap_h if cap else 0)
    y = inner + (box_h - total) // 2
    top = k % 2 == 0
    order = ["name", "art", "cap"] if top else ["art", "name", "cap"]
    for part in order:
        if part == "name":
            x = (pw - nm.width) // 2
            pg.paste(nm, (x, y))
            r = int(pw * 0.034)  # two stars to colour beside the name, when there is room
            if x - inner > r * 3:
                rnd = random.Random(31 + k)
                for sx in (inner + r * 1.4, pw - inner - r * 1.4):
                    _star_outline(d, sx, y + nm.height * rnd.uniform(0.35, 0.65), r, lw)
            y += nm.height + gap
        elif part == "art":
            pg.paste(a, ((pw - a.width) // 2, y))
            y += a.height + gap
        elif cap:
            tw = d.textlength(cap, font=f)
            d.text((pw / 2, y + cap_h / 2), cap, font=f, fill=0, anchor="mm")
            r = int(cap_h * 0.30)
            for sx in (pw / 2 - tw / 2 - r * 2.4, pw / 2 + tw / 2 + r * 2.4):
                _star_outline(d, sx, y + cap_h / 2, r, max(5, lw // 2))
            y += cap_h + gap
    return pg


# ---------------------------------------------------------------- bubble layout ("page_style": "bubble")
# Hand-lettered feel: fat bubble letters that touch and merge, the name on an arch or tilted, an optional line
# above it ("HAPPY BIRTHDAY"), no frame, and the free space filled with little stars, hearts, clouds and balloons.
def _bubble_line(text, size, bend=0.0):
    """One line of bubble letters -> (picture L, mask L). bend = total arch angle in radians (0 = straight)."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    f = F._font("rounded", size)
    line = max(7, size // 15)
    track = -int(size * 0.035) if size > 260 else int(size * 0.02)  # big letters overlap a little and merge, small ones stay apart
    adv = [probe.textlength(ch, font=f) + track for ch in text]
    total = max(1, sum(adv))
    radius = total / bend if bend else 0
    rise = int(radius * (1 - math.cos(bend / 2))) if bend else 0
    pad = int(size * 1.3)
    w, h = int(total + 2 * pad), int(size * 1.9 + rise + 2 * line)
    stroke, fill = Image.new("L", (w, h), 0), Image.new("L", (w, h), 0)
    tile = int(size * 2.4)
    x = 0.0
    for ch, a in zip(text, adv):
        xc = x + (a - track) / 2
        x += a
        if not ch.strip():
            continue
        ts, tf = Image.new("L", (tile, tile), 0), Image.new("L", (tile, tile), 0)
        for t, sw in ((ts, line), (tf, 0)):
            ImageDraw.Draw(t).text((tile / 2, tile * 0.62), ch, font=f, fill=255, anchor="ms", stroke_width=sw, stroke_fill=255)
        px, py = pad + xc, line + size * 1.25
        if bend:
            ang = (xc / total - 0.5) * bend
            px = pad + total / 2 + radius * math.sin(ang)
            py += radius * (1 - math.cos(ang))
            ts, tf = (t.rotate(-math.degrees(ang), resample=Image.BICUBIC) for t in (ts, tf))
        at = (int(px - tile / 2), int(py - tile * 0.62))
        for layer, t in ((stroke, ts), (fill, tf)):
            layer.paste(255, at, t)
    box = stroke.getbbox() or (0, 0, 1, 1)
    stroke, fill = stroke.crop(box), fill.crop(box)
    pic = Image.new("L", stroke.size, 255)
    pic.paste(0, (0, 0), stroke)
    pic.paste(255, (0, 0), fill)
    return pic, stroke


def bubble(text, max_w, max_h, start, bend=0.0, tilt=0):
    """Bubble lettering as large as fits (1 or 2 lines) -> (picture, mask)."""
    best = None
    for lines in ([text], SB._lines(text, 2)):
        size = start
        while True:
            parts = [_bubble_line(ln, size, bend if len(lines) == 1 else bend * 0.6) for ln in lines]
            w = max(p[0].width for p in parts)
            h = sum(p[0].height for p in parts) - int(size * 0.12) * (len(parts) - 1)
            if (w <= max_w and h <= max_h) or size <= 80:
                break
            size -= max(8, size // 14)
        if best is None or size > best[0]:
            best = (size, parts, w, h)
        if len(lines) == 1 and size >= start * 0.5:
            break
    size, parts, w, h = best
    pic, mask = Image.new("L", (w, h), 255), Image.new("L", (w, h), 0)
    y = 0
    for p, m in parts:
        pic.paste(p, ((w - p.width) // 2, y), m)
        mask.paste(255, ((w - p.width) // 2, y), m)
        y += p.height - int(size * 0.12)
    if tilt:
        pic = pic.rotate(tilt, resample=Image.BICUBIC, expand=True, fillcolor=255)
        mask = mask.rotate(tilt, resample=Image.BICUBIC, expand=True, fillcolor=0)
    return pic, mask


def _heart(d, cx, cy, r, w):
    pts = []
    for i in range(40):
        t = math.pi * 2 * i / 40
        pts.append((cx + r * 0.062 * 16 * math.sin(t) ** 3,
                    cy - r * 0.062 * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))))
    d.polygon(pts, fill=255)
    d.line(pts + pts[:2], fill=0, width=w, joint="curve")


def _cloud(d, cx, cy, r, w):
    blobs = [(-0.65, 0.15, 0.48), (-0.15, -0.22, 0.62), (0.48, 0.0, 0.52), (0.0, 0.28, 0.5), (-0.4, 0.32, 0.4), (0.45, 0.3, 0.4)]
    for grow, col in ((w, 0), (0, 255)):
        for bx, by, br in blobs:
            d.ellipse((cx + bx * r - br * r - grow, cy + by * r - br * r - grow, cx + bx * r + br * r + grow, cy + by * r + br * r + grow), fill=col)


def _balloon(d, cx, cy, r, w):
    d.ellipse((cx - r * 0.62, cy - r, cx + r * 0.62, cy + r * 0.5), fill=255, outline=0, width=w)
    d.polygon([(cx - r * 0.12, cy + r * 0.5), (cx + r * 0.12, cy + r * 0.5), (cx, cy + r * 0.66)], fill=0)
    d.line([(cx + math.sin(i / 3) * r * 0.08, cy + r * 0.66 + i * r * 0.07) for i in range(6)], fill=0, width=max(3, w // 2))


def _ring(d, cx, cy, r, w):
    d.ellipse((cx - r * 0.4, cy - r * 0.4, cx + r * 0.4, cy + r * 0.4), fill=255, outline=0, width=w)


DOODLES = {"star": _star_outline, "heart": _heart, "cloud": _cloud, "balloon": _balloon, "dot": _ring}


def _doodles(pg, kinds, seed, lw, count=26):
    """Little shapes to colour in the free space of the page (never on top of the drawing or the letters)."""
    pw, ph = pg.size
    q = 24
    gw, gh = pw // q, ph // q
    busy = pg.resize((gw, gh), Image.BOX).point(lambda v: 255 if v < 252 else 0).filter(ImageFilter.MaxFilter(5))
    bd = ImageDraw.Draw(busy)
    d = ImageDraw.Draw(pg)
    rnd = random.Random(seed)
    kinds = [k for k in kinds or [] if k in DOODLES] or ["star", "heart", "cloud", "dot"]
    m, placed = int(pw * 0.05), 0
    for _ in range(900):
        if placed >= count:
            break
        kind = rnd.choice(kinds)
        r = int(pw * rnd.uniform(0.022, 0.04) * (1.5 if kind in ("cloud", "balloon") else 1))
        cx, cy = rnd.randint(m + r, pw - m - r), rnd.randint(m + r, ph - m - r)
        reach = r * (1.9 if kind == "balloon" else 1.35)
        cell = (int((cx - reach) / q), int((cy - reach) / q), int((cx + reach) / q) + 1, int((cy + reach) / q) + 1)
        if busy.crop(cell).getbbox():
            continue
        DOODLES[kind](d, cx, cy, r, max(6, lw - 2))
        bd.rectangle((cell[0] - 1, cell[1] - 1, cell[2] + 1, cell[3] + 1), fill=255)
        placed += 1


def page_bubble(art, name, caption, k, size=LETTER, above="", doodles=None):
    """One finished page in the bubble layout (mode L, black on white)."""
    pw, ph = size
    pg = Image.new("L", size, 255)
    lw = max(8, pw // 260)
    m = int(pw * 0.06)
    box_w, box_h = pw - 2 * m, ph - 2 * m
    top = k % 2 == 0                       # even pages: name over the drawing, odd pages: under it
    bend = (1.15, 0.0, 0.85, 0.0)[k % 4]   # arch on the pages with the name on top
    tilt = (0, -5, 0, 4)[k % 4]
    nm = bubble(name, box_w * (0.96 if bend else 0.90), ph * 0.25, int(ph * 0.19), bend, tilt)
    ab = bubble(above.upper(), box_w * 0.82, ph * 0.09, int(ph * 0.075)) if above else None
    cp = bubble(caption.upper(), box_w * 0.88, ph * 0.085, int(ph * 0.062)) if caption else None
    gap = int(ph * 0.012)
    fixed = nm[0].height + sum(x[0].height + gap for x in (ab, cp) if x)
    a = art.convert("L")
    room = box_h - fixed - 2 * gap
    sc = min(box_w * 0.92 / a.width, room / a.height)
    a = a.resize((max(1, int(a.width * sc)), max(1, int(a.height * sc))), Image.LANCZOS).point(lambda v: 255 if v > 150 else 0)
    order = [ab, nm, "art", cp] if top else [ab, "art", nm, cp]
    y = m + (box_h - fixed - a.height - 2 * gap) // 2
    for part in order:
        if part is None:
            continue
        if part == "art":
            pg.paste(a, ((pw - a.width) // 2, y), a.point(lambda v: 255 if v < 128 else 0).filter(ImageFilter.MaxFilter(3)))
            y += a.height + gap
        else:
            pic, mask = part
            pg.paste(pic, ((pw - pic.width) // 2, y), mask)
            y += pic.height + gap
    _doodles(pg, doodles, 500 + k, lw)
    return pg.point(lambda v: 255 if v > 140 else 0)


def page(art, name, spec, k, size=LETTER):
    """One finished page in the product's own layout."""
    d = (spec.get("designs") or [{}] * (k + 1))
    ds = d[k] if k < len(d) else {}
    if spec.get("page_style") == "bubble":
        return page_bubble(art, name, _caption(spec, k), k, size, str(ds.get("above") or spec.get("above") or "")[:24],
                           spec.get("doodles"))
    return page_framed(art, name, _caption(spec, k), k, size)


def _caption(spec, k):
    d = spec.get("designs") or []
    return re.sub(r"\s+", " ", str((d[k] if k < len(d) else {}).get("tagline", "")).strip())[:30]


def _pdf(pages):
    b = io.BytesIO()
    one = [p.convert("1") for p in pages]
    one[0].save(b, "PDF", save_all=True, append_images=one[1:], resolution=300)
    return b.getvalue()


def render(p, name, clean, download):
    """An order: all pages with the buyer's name -> [(file name, bytes)] (two PDFs)."""
    name = clean(name)
    safe = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "name"
    spec = p.get("spec", p)
    arts = []
    for k in range(p.get("custom_count", 6)):
        try:
            arts.append((k, Image.open(io.BytesIO(download(p["id"], f"custom__art-{k + 1}.png"))).convert("L")))
        except Exception as e:
            print(f"[custom] çizim {k + 1} indirilemedi: {e}")
    if not arts:
        return []
    return [(f"{safe}-coloring-pages-US-Letter.pdf", _pdf([page(a, name, spec, k, LETTER) for k, a in arts])),
            (f"{safe}-coloring-pages-A4.pdf", _pdf([page(a, name, spec, k, A4) for k, a in arts]))]


# ---------------------------------------------------------------- listing photos (2000 x 2000)
def backdrop(colour, seed=1):
    inner, outer = BG[colour]
    yy, xx = np.mgrid[0:PHOTO, 0:PHOTO].astype(np.float32)
    t = np.clip(np.hypot(xx - PHOTO / 2, yy - PHOTO * 0.48) / (PHOTO * 0.80), 0, 1)[..., None] ** 1.5
    img = Image.fromarray((np.array(inner) * (1 - t) + np.array(outer) * t).astype(np.uint8)).convert("RGBA")
    rnd = random.Random(seed)
    deco = Image.new("RGBA", (PHOTO, PHOTO), (0, 0, 0, 0))
    d = ImageDraw.Draw(deco)
    for _ in range(40):  # confetti dots and little stars
        x, y, r = rnd.randint(0, PHOTO), rnd.randint(0, PHOTO), rnd.choice([10, 14, 20, 28])
        if rnd.random() < 0.5:
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randint(50, 110)))
        else:
            pts = [(x + math.cos(math.pi / 4 * i) * (r * 2 if i % 2 == 0 else r * 0.6),
                    y + math.sin(math.pi / 4 * i) * (r * 2 if i % 2 == 0 else r * 0.6)) for i in range(8)]
            d.polygon(pts, fill=(255, 255, 255, rnd.randint(60, 120)))
    img.alpha_composite(deco)
    return img


def _heading(c, text, y, size=170, fill=WHITE):
    F._heading(c, text, y, size=size, fill=fill)


def _sheet(pg, h, colored=None):
    """A page as a sheet of paper (RGBA) of height h; `colored` puts the coloured-in example on it instead."""
    src = (colored or pg).convert("RGB")
    w = int(h * src.width / src.height)
    return src.resize((w, h), Image.LANCZOS).convert("RGBA")


def _crayon(length, col, thick=64):
    im = Image.new("RGBA", (length, thick), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    tip = int(thick * 1.1)
    d.rounded_rectangle((0, 0, length - tip, thick - 1), radius=10, fill=col + (255,))
    d.rectangle((int(length * 0.16), 0, int(length * 0.62), thick - 1), fill=F._shade(col, 0.78) + (255,))
    d.polygon([(length - tip, 4), (length - 2, thick // 2), (length - tip, thick - 5)], fill=F._shade(col, 1.25) + (255,))
    d.rectangle((0, int(thick * 0.12), length - tip, int(thick * 0.26)), fill=F._shade(col, 1.35) + (160,))
    return im


def _crayons(c, x, y, seed):
    rnd = random.Random(seed)
    for i, col in enumerate(rnd.sample(CRAYONS, 3)):
        paste_with_shadow(c, _crayon(520, col), (x + i * 34, y + i * 96), radius=12, offset=(0, 10), opacity=90,
                          angle=rnd.uniform(-16, 16))


def _colored(pg, palette, seed):
    """The page with many areas coloured in (shows a buyer what the finished page can look like)."""
    cols = [tuple(c) for c in CRAYONS]
    small = pg.convert("L").copy()
    small.thumbnail((1100, 1100))
    bw = small.point(lambda v: 255 if v > 150 else 0).convert("RGB")
    w, h = bw.size
    rnd = random.Random(seed)
    ImageDraw.floodfill(bw, (2, 2), (255, 255, 254), thresh=0)          # outside the frame stays white
    if bw.getpixel((w // 2, int(h * 0.062))) == (255, 255, 255):       # the paper inside the frame too
        ImageDraw.floodfill(bw, (w // 2, int(h * 0.062)), (255, 255, 253), thresh=0)
    for _ in range(420):
        x, y = rnd.randrange(w), rnd.randrange(h)
        if bw.getpixel((x, y)) == (255, 255, 255):
            ImageDraw.floodfill(bw, (x, y), F._shade(rnd.choice(cols), 1.25), thresh=0)
    return bw


def cover(pages, colored, n):
    c = backdrop("yellow", 5)
    _heading(c, "CUSTOM NAME", 170, size=250, fill=INK)
    _heading(c, "COLORING PAGES", 400, size=250, fill=WHITE)
    for i, x, y, ang in ((4, 20, 800, 13), (2, 1250, 800, -13), (3, 280, 700, 6), (1, 1010, 700, -6)):
        paste_with_shadow(c, _sheet(pages[i % n], 980), (x, y), radius=26, offset=(0, 20), opacity=110, angle=ang)
    front = _sheet(pages[0], 1200, colored)
    paste_with_shadow(c, front, ((PHOTO - front.width) // 2, 590), radius=32, offset=(0, 26), opacity=130)
    c.alpha_composite(F._burst((f"{n}", "PAGES"), 210, fill=(232, 62, 72)), (70, 540))
    _crayons(c, 1440, 1500, 3)
    F._pill(c, "TYPE ANY NAME  ·  PRINT AT HOME", 1900, ink=INK, size=66)
    return c.convert("RGB")


def all_pages(pages, n):
    c = backdrop("blue", 11)
    _heading(c, f"{n} PAGES  ·  ALL WITH YOUR NAME", 150)
    cols, h = 3, 760
    w = int(h * pages[0].width / pages[0].height)
    gx = (PHOTO - cols * w) // (cols + 1)
    for i, pg in enumerate(pages):
        paste_with_shadow(c, _sheet(pg, h), (gx + (i % cols) * (w + gx), 300 + (i // cols) * (h + 60)),
                          radius=20, offset=(0, 16), opacity=110)
    return c.convert("RGB")


def any_name(make, names):
    c = backdrop("coral", 21)
    _heading(c, "ANY NAME YOU LIKE", 150, size=210)
    h = 760
    sheets = [_sheet(make(i, nm), h) for i, nm in enumerate(names[:3])]
    gx = (PHOTO - sum(s.width for s in sheets)) // 4
    x = gx
    for s in sheets:
        paste_with_shadow(c, s, (x, 290), radius=20, offset=(0, 16), opacity=110)
        x += s.width + gx
    d = ImageDraw.Draw(c)
    steps = ["Type the name in the personalization box", "We write it on every page", "Download and print within 24 hours"]
    f, fn = font("sans_bold", 74), F.DF.get("bold", 120)
    for i, t in enumerate(steps):
        y = 1250 + i * 240
        d.ellipse((150, y - 88, 326, y + 88), fill=(255, 214, 92, 255), outline=WHITE + (255,), width=10)
        d.text((238, y + 6), str(i + 1), font=fn, fill=INK + (255,), anchor="mm")
        d.text((400, y), t, font=f, fill=WHITE + (255,), anchor="lm")
    return c.convert("RGB")


def color_it(pages, colored, n):
    c = backdrop("mint", 31)
    _heading(c, "COLOR IT YOUR WAY", 150, size=210)
    paste_with_shadow(c, _sheet(pages[0], 1180), (90, 420), radius=26, offset=(0, 20), opacity=110, angle=4)
    paste_with_shadow(c, _sheet(pages[0], 1180, colored), (1000, 420), radius=26, offset=(0, 20), opacity=110, angle=-4)
    F._pill(c, "CRAYONS  ·  MARKERS  ·  PENCILS", 1880, ink=INK, size=66)
    return c.convert("RGB")


def _list_photo(colour, seed, title, lines, sheet, n):
    c = backdrop(colour, seed)
    _heading(c, title, 150, size=210)
    paste_with_shadow(c, sheet, (PHOTO - sheet.width - 110, 520), radius=26, offset=(0, 20), opacity=110, angle=-4)
    d = ImageDraw.Draw(c)
    f = font("sans_bold", 76)
    for i, t in enumerate(lines):
        y = 520 + i * 270
        F._star(d, 180, y, 66, (255, 214, 92))
        d.multiline_text((290, y), t, font=f, fill=WHITE + (255,), anchor="lm", spacing=12)
    return c.convert("RGB")


def photos(pages, colored, n, make, names):
    return [("00-cover.jpg", cover(pages, colored, n)),
            ("01-all.jpg", all_pages(pages, n)),
            ("02-order.jpg", any_name(make, names)),
            ("03-color.jpg", color_it(pages, colored, n)),
            ("04-what.jpg", _list_photo("purple", 41, "WHAT YOU GET",
                                        [f"{n} coloring pages\nwith your name", "US Letter + A4\nPDF files",
                                         "Bold lines, easy\nfor little hands", "Print as often\nas you like", "Sent within\n24 hours"],
                                        _sheet(pages[2 % n], 1120), n)),
            ("05-ideas.jpg", _list_photo("blue", 51, "KIDS LOVE IT FOR",
                                         ["Birthday parties\nand party favors", "Rainy days and\nquiet time", "Classroom and\npreschool fun",
                                          "A gift with their\nown name on it", "Road trips and\nrestaurants"],
                                         _sheet(pages[3 % n], 1120), n))]


# ---------------------------------------------------------------- the product
def _instructions_pdf(title, n):
    pg = Image.new("RGB", LETTER, (252, 250, 246))
    d = ImageDraw.Draw(pg)
    d.text((1275, 420), "Thank you for your order!", font=font("serif", 130), fill=(60, 50, 45), anchor="mm")
    lines = [title, "", "Your personalized coloring pages are made for you.",
             f"You will receive {n} pages with the name you entered", "as PDF files (US Letter and A4)",
             "within 24 hours (at the latest 3 days) here on Etsy:", "Purchases and reviews > this order > Download files.", "",
             "Please check the spelling you entered at checkout.", "If anything should change, just send us a message.", "",
             "Print at home as often as you like. Personal use only;", "please do not share or resell the files."]
    y = 700
    for ln in lines:
        d.text((1275, y), ln, font=font("sans", 60), fill=(70, 65, 60), anchor="mm")
        y += 108
    b = io.BytesIO()
    pg.save(b, "PDF", resolution=300)
    return b.getvalue()


def build(spec, slug, clean, count):
    palette = spec.get("palette", [])
    sample = clean(spec.get("sample_name") or "Olivia")
    arts = []
    for ds in spec.get("designs", [])[:count]:
        im = images.try_generate(f"{ds['prompt']}. One clear subject that fills the picture. {coloring._suffix('kids')}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is None:
            continue
        arts.append(lineart(im.resize((2048, 2048), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))))
    images.need(len(arts), count, ratio=0.8)
    n = len(arts)
    make = lambda i, nm: page(arts[i % n], nm, spec, i % n)
    pages = [make(k, sample) for k in range(n)]
    colored = _colored(pages[0], palette, seed=len(slug))

    wm = mockups.grid([p.convert("RGB") for p in pages], f"{n} pages with YOUR name", palette, cols=3).convert("RGB")
    wm.thumbnail((900, 900))
    wd = ImageDraw.Draw(wm, "RGBA")
    for y in range(80, wm.height, 260):
        wd.text((wm.width / 2, y), "SAMPLE", font=font("sans_bold", 90), fill=(120, 120, 120, 90), anchor="mm")
    files = [("HOW-TO-RECEIVE-YOUR-PAGES.pdf", _instructions_pdf(spec["title"], n)), ("preview-sample.jpg", jpeg_bytes(wm, 80))]
    readme = (f"{spec['title']}\n\nThank you! This listing is personalized: your {n} coloring pages with the name you entered "
              "are sent to you on Etsy within 24 hours (at the latest 3 days).\n")
    names = [clean(x) for x in spec.get("sample_names") or []] or [sample, "Noah", "Emma"]
    mock = photos(pages, colored, n, make, names)
    return {
        "delivery": make_zips(slug, files, readme),
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "own_cover": True,
        "extra_assets": {f"custom__art-{k + 1}.png": png_bytes(a) for k, a in enumerate(arts)},
        "product_extra": {"custom_count": n},
        "listing": {"is_personalizable": True, "personalization_is_required": True,
                    "personalization_char_count_max": 40,
                    "personalization_instructions": spec.get("personalization_instructions")
                    or f"Name exactly as it should appear (e.g. {sample}). Your pages are sent within 24 hours."},
        "included": [f"{n} coloring pages personalized with your name", "2 PDF files: US Letter (8.5 x 11 in) and A4, 300 DPI",
                     "Sent to you on Etsy within 24 hours"],
        "details": ["Made to order: enter the name in the personalization box at checkout",
                    "Bold black line art on a white page, easy for little hands",
                    "This is a digital file, nothing is shipped"],
        "usage": ["Print at home or at a print shop, as often as you like",
                  "Birthday parties, party favors, classrooms, rainy days and gifts"],
        "license": "Personal use only. Do not share or resell the files.",
        "taxonomy": ["Coloring Books", "Coloring Pages", "Digital Prints"],
        "taxonomy_fallback_id": 2078,
        "is_supply": False,
        "skip_attributes": ["room"],
        "count": n,
    }
