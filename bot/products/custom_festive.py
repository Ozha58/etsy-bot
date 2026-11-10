"""Festive look for personalized name designs (a preset asks for it with "look": "festive").

The plain custom look is a small drawing between a big name and a line of text on beige photos. This look is made
to stop a buyer who is scrolling: the character fills the design, the name is a chunky sticker-style word that
overlaps it, the tagline sits on a ribbon, and Christmas lights, stars and snowflakes are drawn around it by code
(so they are always sharp and never contain AI text). The listing photos are square, in deep red and green.

Products without the "look" field keep the old design and photos, so listings that are already published
still deliver exactly what their photos show.

Every theme of a preset has its own SKIN (name colours and fonts, code-drawn decorations, photo backdrops), so the
trucks set does not look like the classic set with other characters. spec["skin"] picks it (presets.spec sets it to
the theme). Products made before skins have no "skin" in their spec and get "classic": exactly the look they were
listed with."""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import display_fonts as DF
from ..imgutil import font, paste_with_shadow
from . import sublimation as SB

SIZE = SB.SIZE
PHOTO = 2000
RED, GREEN, BLUE, GOLD = (200, 30, 48), (20, 116, 70), (32, 112, 176), (240, 178, 52)
WHITE, INK = (255, 255, 255), (52, 26, 22)
# per design: name colour, ribbon colour, name font, code-drawn decoration, layout (ribbon under / above)
SCHEMES = [
    (RED, GREEN, "script", "lights", "under"),
    (GREEN, RED, "rounded", "stars", "above"),
    (RED, BLUE, "script", "snow", "under"),
    (BLUE, RED, "rounded", "snow", "above"),
    (GREEN, RED, "script", "lights", "under"),
    (RED, GREEN, "rounded", "stars", "above"),
]


def _shade(c, k):
    """k < 1 darker, k > 1 lighter (towards white)."""
    if k <= 1:
        return tuple(int(v * k) for v in c)
    return tuple(int(v + (255 - v) * (k - 1)) for v in c)


def _font(kind, size):
    f = DF.get(kind, size)
    if kind == "rounded":  # Fredoka is a variable font: use its bold weight
        try:
            f.set_variation_by_axes([a["maximum"] if b"eight" in a["name"] else a["default"]
                                     for a in f.get_variation_axes()])
        except Exception:
            pass
    return f


# ---------------------------------------------------------------- pieces of a design
def sticker_text(text, kind, fill, max_w, max_h, start=1100):
    """The name as a sticker: gradient letters, a thick white edge, a dark rim and a solid drop below it."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    best = None
    for lines in ([text], SB._lines(text, 2)):
        size = start
        while size > 110:
            f = _font(kind, size)
            edge = int(size * 0.075) + int(size * 0.04)
            boxes = [probe.textbbox((0, 0), ln, font=f) for ln in lines]
            w = max(b[2] - b[0] for b in boxes) + 2 * edge
            h = sum(b[3] - b[1] for b in boxes) + int(size * 0.12) * (len(lines) - 1) + 2 * edge + int(size * 0.07)
            if w <= max_w and h <= max_h:
                break
            size -= max(10, size // 18)
        if best is None or size > best[0]:
            best = (size, lines)
        if len(lines) == 1 and size >= start * 0.6:
            break  # one line is already big, no need to wrap
    size, lines = best
    f = _font(kind, size)
    white, rim, drop, gap = int(size * 0.075), int(size * 0.04), int(size * 0.07), int(size * 0.12)
    edge = white + rim
    boxes = [probe.textbbox((0, 0), ln, font=f) for ln in lines]
    w = max(b[2] - b[0] for b in boxes) + 2 * edge
    h = sum(b[3] - b[1] for b in boxes) + gap * (len(lines) - 1) + 2 * edge + drop
    spots, y = [], edge
    for ln, b in zip(lines, boxes):
        spots.append(((w - (b[2] - b[0])) / 2 - b[0], y - b[1], ln))
        y += b[3] - b[1] + gap
    dark = _shade(fill, 0.42)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    for dy in range(drop, -1, -max(1, drop // 6)):  # dark rim, pulled down a little: a solid 3D drop
        for x, yy, ln in spots:
            d.text((x, yy + dy), ln, font=f, fill=dark + (255,), stroke_width=edge, stroke_fill=dark + (255,))
    for x, yy, ln in spots:
        d.text((x, yy), ln, font=f, fill=WHITE + (255,), stroke_width=white, stroke_fill=WHITE + (255,))
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    for x, yy, ln in spots:
        md.text((x, yy), ln, font=f, fill=255)
    ramp = np.linspace(0, 1, h - drop)[:, None, None]
    top, bottom = np.array(_shade(fill, 1.22)), np.array(_shade(fill, 0.80))
    grad = np.zeros((h, w, 3), np.uint8)
    grad[:h - drop] = np.broadcast_to(top + (bottom - top) * ramp, (h - drop, w, 3)).astype(np.uint8)
    out.paste(Image.fromarray(grad), (0, 0), mask)
    return out


def ribbon(text, fill, max_w, size=250):
    """The tagline on a banner with folded tails."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    while True:
        f = DF.get("bold", size)
        tw = probe.textlength(text, font=f)
        bh = int(size * 1.45)
        tail = int(bh * 0.62)
        if tw + size * 1.2 + 2 * tail <= max_w or size <= 110:
            break
        size -= 12
    bw = int(tw + size * 1.2)
    drop, edge = int(bh * 0.22), max(10, size // 16)
    w, h = bw + 2 * tail + 2 * edge, bh + drop + 2 * edge
    shape = Image.new("L", (w, h), 0)  # silhouette: used for the white keyline
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d, s = ImageDraw.Draw(body), ImageDraw.Draw(shape)
    x0, x1, y0 = edge + tail, edge + tail + bw, edge
    back, fold = _shade(fill, 0.74), _shade(fill, 0.5)
    notch = int(tail * 0.42)
    for side in (-1, 1):
        ox = x0 if side < 0 else x1  # the tail starts under the banner edge
        far = ox + side * tail
        pts = [(ox - side * notch * 2, y0 + drop), (far, y0 + drop), (far - side * notch, y0 + drop + bh / 2),
               (far, y0 + drop + bh), (ox - side * notch * 2, y0 + drop + bh)]
        d.polygon(pts, fill=back + (255,))
        s.polygon(pts, fill=255)
        d.polygon([(ox, y0 + bh), (ox - side * notch * 2, y0 + bh), (ox - side * notch * 2, y0 + bh + drop)],
                  fill=fold + (255,))
    d.rounded_rectangle((x0, y0, x1, y0 + bh), radius=bh // 7, fill=fill + (255,))
    s.rounded_rectangle((x0, y0, x1, y0 + bh), radius=bh // 7, fill=255)
    lite = _shade(fill, 1.28) + (255,)
    for yy in (y0 + bh * 0.13, y0 + bh * 0.87):  # stitched lines
        for x in range(int(x0 + bh * 0.3), int(x1 - bh * 0.3), int(size * 0.22)):
            d.line((x, yy, x + size * 0.11, yy), fill=lite, width=max(5, size // 40))
    d.text(((x0 + x1) / 2, y0 + bh / 2 + size * 0.03), text, font=f, fill=WHITE + (255,), anchor="mm")
    key = shape.filter(ImageFilter.MaxFilter(2 * (edge // 2) + 1))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (w, h), WHITE + (255,)), (0, 0), key)
    out.alpha_composite(body)
    return out


def _star(d, cx, cy, r, fill):
    def pts(rad):
        return [(cx + math.cos(math.pi / 4 * i) * (rad if i % 2 == 0 else rad * 0.30),
                 cy + math.sin(math.pi / 4 * i) * (rad if i % 2 == 0 else rad * 0.30)) for i in range(8)]
    d.polygon(pts(r + max(8, r * 0.13)), fill=WHITE + (255,))
    d.polygon(pts(r), fill=fill + (255,))
    d.ellipse((cx - r * 0.13, cy - r * 0.13, cx + r * 0.13, cy + r * 0.13), fill=_shade(fill, 1.6) + (255,))


def _snowflake(d, cx, cy, r, fill):
    for width, col in ((int(r * 0.30), WHITE), (int(r * 0.15), fill)):
        for i in range(6):
            a = math.pi / 3 * i
            ex, ey = cx + math.cos(a) * r, cy + math.sin(a) * r
            d.line((cx, cy, ex, ey), fill=col + (255,), width=max(4, width))
            bx, by = cx + math.cos(a) * r * 0.58, cy + math.sin(a) * r * 0.58
            for s in (-1, 1):
                b = a + s * math.pi / 4
                d.line((bx, by, bx + math.cos(b) * r * 0.32, by + math.sin(b) * r * 0.32),
                       fill=col + (255,), width=max(4, width))
        d.ellipse((cx - width * 0.7, cy - width * 0.7, cx + width * 0.7, cy + width * 0.7), fill=col + (255,))


def _heart(d, cx, cy, r, fill):
    for rad, col in ((r + max(8, r * 0.13), WHITE), (r, fill)):
        k = rad / 100
        d.ellipse((cx - 98 * k, cy - 70 * k, cx + 4 * k, cy + 26 * k), fill=col + (255,))
        d.ellipse((cx - 4 * k, cy - 70 * k, cx + 98 * k, cy + 26 * k), fill=col + (255,))
        d.polygon([(cx - 92 * k, cy - 4 * k), (cx + 92 * k, cy - 4 * k), (cx, cy + 96 * k)], fill=col + (255,))
    d.ellipse((cx - r * 0.62, cy - r * 0.52, cx - r * 0.34, cy - r * 0.24), fill=_shade(fill, 1.6) + (255,))


def _paw(d, cx, cy, r, fill):
    toes = [(-0.62, -0.42, 0.24), (-0.22, -0.78, 0.26), (0.22, -0.78, 0.26), (0.62, -0.42, 0.24)]
    for grow, col in ((max(8, r * 0.13), WHITE), (0, fill)):
        d.ellipse((cx - r * 0.58 - grow, cy - r * 0.18 - grow, cx + r * 0.58 + grow, cy + r * 0.72 + grow), fill=col + (255,))
        for tx, ty, tr in toes:
            d.ellipse((cx + (tx - tr) * r - grow, cy + (ty - tr) * r - grow, cx + (tx + tr) * r + grow,
                       cy + (ty + tr) * r + grow), fill=col + (255,))


def _dot(d, cx, cy, r, fill):
    r *= 0.55
    d.ellipse((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10), fill=WHITE + (255,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill + (255,))
    d.ellipse((cx - r * 0.55, cy - r * 0.6, cx - r * 0.1, cy - r * 0.15), fill=_shade(fill, 1.6) + (255,))


def _leaf(d, cx, cy, r, fill):
    """A holly sprig: two pointed leaves and three berries."""
    berry = RED if fill != RED else GOLD
    for grow, col in ((max(8, r * 0.13), WHITE), (0, None)):
        for side in (-1, 1):
            pts = [(cx, cy), (cx + side * r * 0.35, cy - r * 0.55), (cx + side * r * 0.95, cy - r * 0.62),
                   (cx + side * r * 0.75, cy - r * 0.15), (cx + side * r * 0.98, cy + r * 0.2), (cx + side * r * 0.4, cy + r * 0.12)]
            if grow:
                mx = sum(x for x, _ in pts) / len(pts)
                my = sum(y for _, y in pts) / len(pts)
                pts = [(mx + (x - mx) * (1 + grow / r), my + (y - my) * (1 + grow / r)) for x, y in pts]
            d.polygon(pts, fill=(col or fill) + (255,))
        for bx, by in ((-0.16, 0.18), (0.16, 0.18), (0, -0.06)):
            br = r * 0.2 + grow
            d.ellipse((cx + bx * r - br, cy + by * r - br, cx + bx * r + br, cy + by * r + br), fill=(col or berry) + (255,))


SHAPES = {"stars": _star, "hearts": _heart, "paws": _paw, "dots": _dot, "holly": _leaf}


def _skin(schemes, accent, bulbs, backdrops, sub, deco_cols):
    return {"schemes": schemes, "accent": accent, "bulbs": bulbs, "backdrops": backdrops, "sub": sub,
            "deco_cols": deco_cols, "sub_col": _shade(accent, 1.45), "tee": _shade(schemes[0][0], 0.88)}


PINK, LILAC, MINT, PLUM = (232, 84, 142), (150, 110, 205), (70, 190, 160), (120, 40, 110)
YELLOW, NAVY, ORANGE, LIME = (250, 196, 30), (30, 52, 120), (240, 120, 30), (120, 186, 40)
TEAL, CORAL, BROWN, CREAM = (20, 140, 150), (240, 98, 84), (140, 84, 44), (246, 232, 204)
FOREST, MUSTARD = (36, 96, 60), (214, 160, 40)
# per theme: SCHEMES-style rows (name colour, ribbon colour, name font, decoration, layout), the accent (badges,
# numbers), the light bulb colours, the photo backdrops (inner, outer) used in turn, the cover's second line and
# the colours of each decoration. "classic" is the original look and must never change: published listings use it.
SKINS = {
    "classic": _skin(SCHEMES, GOLD, [RED, GOLD, GREEN, BLUE],
                     [((190, 30, 46), (88, 8, 22)), ((30, 124, 78), (6, 52, 34)), ((40, 118, 176), (12, 44, 84))],
                     "Christmas designs with YOUR name",
                     {"stars": [GOLD, GOLD, RED], "snow": [BLUE, _shade(BLUE, 1.35), GOLD], "lights": [GOLD, GOLD, GREEN]}),
    "woodland": _skin([(FOREST, BROWN, "retro", "holly", "under"), (BROWN, FOREST, "serif", "snow", "above"),
                       (FOREST, MUSTARD, "retro", "stars", "under"), (BROWN, RED, "serif", "holly", "above"),
                       (FOREST, BROWN, "retro", "snow", "under"), (RED, FOREST, "serif", "stars", "above")],
                      MUSTARD, [MUSTARD, RED, CREAM, FOREST],
                      [((92, 70, 46), (38, 26, 16)), ((44, 104, 70), (10, 40, 24)), ((86, 108, 110), (28, 40, 44))],
                      "Woodland Christmas with YOUR name",
                      {"stars": [MUSTARD, CREAM, MUSTARD], "snow": [(150, 180, 190), CREAM, MUSTARD],
                       "holly": [FOREST, (60, 130, 70), FOREST]}),
    "trucks": _skin([(RED, NAVY, "bold", "stars", "under"), (NAVY, YELLOW, "bold", "dots", "above"),
                     (YELLOW, RED, "bold", "snow", "under"), (RED, NAVY, "bold", "dots", "above"),
                     (NAVY, RED, "bold", "stars", "under"), (YELLOW, NAVY, "bold", "snow", "above")],
                    YELLOW, [RED, YELLOW, BLUE, GREEN],
                    [((44, 70, 150), (12, 20, 60)), ((70, 74, 84), (22, 24, 30)), ((196, 42, 40), (90, 12, 14))],
                    "Christmas trucks with YOUR name",
                    {"stars": [YELLOW, YELLOW, RED], "snow": [(120, 170, 225), WHITE, YELLOW], "dots": [RED, YELLOW, BLUE]}),
    "ballerina": _skin([(PINK, LILAC, "script", "hearts", "under"), (LILAC, PINK, "retro", "stars", "above"),
                        (PINK, MINT, "script", "snow", "under"), (PLUM, PINK, "retro", "hearts", "above"),
                        (PINK, LILAC, "script", "stars", "under"), (LILAC, PINK, "retro", "snow", "above")],
                       GOLD, [PINK, GOLD, LILAC, MINT],
                       [((214, 110, 160), (110, 34, 80)), ((132, 96, 186), (52, 30, 92)), ((228, 150, 170), (140, 60, 92))],
                       "Sweet Christmas with YOUR name",
                       {"stars": [GOLD, (255, 220, 236), GOLD], "snow": [LILAC, (230, 210, 250), GOLD],
                        "hearts": [PINK, (255, 160, 196), GOLD]}),
    "dino": _skin([(LIME, ORANGE, "rounded", "dots", "under"), (ORANGE, TEAL, "retro", "stars", "above"),
                   (TEAL, ORANGE, "rounded", "snow", "under"), (LIME, PLUM, "retro", "dots", "above"),
                   (ORANGE, LIME, "rounded", "stars", "under"), (TEAL, LIME, "retro", "snow", "above")],
                  ORANGE, [LIME, ORANGE, TEAL, YELLOW],
                  [((92, 140, 40), (28, 56, 12)), ((30, 128, 120), (6, 48, 46)), ((200, 96, 30), (90, 36, 8))],
                  "Dino Christmas with YOUR name",
                  {"stars": [YELLOW, ORANGE, YELLOW], "snow": [TEAL, (160, 220, 210), YELLOW], "dots": [LIME, ORANGE, TEAL]}),
    "pets": _skin([(TEAL, CORAL, "rounded", "paws", "under"), (CORAL, NAVY, "script", "hearts", "above"),
                   (NAVY, MUSTARD, "rounded", "snow", "under"), (CORAL, TEAL, "script", "paws", "above"),
                   (TEAL, NAVY, "rounded", "hearts", "under"), (NAVY, CORAL, "script", "snow", "above")],
                  MUSTARD, [CORAL, MUSTARD, TEAL, WHITE],
                  [((26, 130, 140), (6, 50, 56)), ((226, 100, 86), (110, 32, 28)), ((44, 64, 130), (14, 22, 58))],
                  "Furry Christmas with YOUR name",
                  {"paws": [BROWN, CORAL, NAVY], "hearts": [CORAL, (255, 170, 160), MUSTARD],
                   "snow": [(120, 180, 200), WHITE, MUSTARD]}),
}


SKINS["classic"].update(sub_col=(255, 226, 150), tee=(176, 30, 44))  # the original listing photos, unchanged


def skin(name):
    return SKINS.get(str(name or "classic").lower(), SKINS["classic"])


def _lights(c, x0, x1, y, sag, rnd, cols=None):
    """A string of Christmas lights hanging between two points."""
    d = ImageDraw.Draw(c)
    curve = [(x0 + (x1 - x0) * t / 60, y + sag * 4 * (t / 60) * (1 - t / 60)) for t in range(61)]
    d.line(curve, fill=WHITE + (255,), width=46, joint="curve")
    d.line(curve, fill=(24, 70, 46, 255), width=22, joint="curve")
    cols = list(cols or [RED, GOLD, GREEN, BLUE])
    n = max(5, int((x1 - x0) / 400))
    for i in range(n):
        t = (i + 0.5) / n
        bx, by = x0 + (x1 - x0) * t, y + sag * 4 * t * (1 - t)
        col = cols[(i + rnd.randrange(4)) % 4] if i == 0 else cols[(cols.index(prev) + 1) % 4]
        prev = col
        bw, bh = 120, 180
        bulb = Image.new("RGBA", (bw * 3, bh * 3), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bulb)
        ox, oy = bw, bh * 0.8
        bd.ellipse((ox - 16, oy - 16, ox + bw + 16, oy + bh + 16), fill=WHITE + (255,))
        bd.rounded_rectangle((ox + bw * 0.22, oy - 56, ox + bw * 0.78, oy + 22), radius=14, fill=(24, 70, 46, 255))
        bd.ellipse((ox, oy, ox + bw, oy + bh), fill=col + (255,))
        bd.ellipse((ox + bw * 0.18, oy + bh * 0.14, ox + bw * 0.46, oy + bh * 0.46), fill=_shade(col, 1.7) + (255,))
        bulb = bulb.rotate(rnd.uniform(-22, 22), resample=Image.BICUBIC)
        c.alpha_composite(bulb, (int(bx - bulb.width / 2), int(by - bh * 0.62)))


def _sprinkle(c, kind, zones, rnd, sk=None):
    """Stars, snowflakes, hearts, paws, dots or holly in the free space left and right of the character."""
    d = ImageDraw.Draw(c)
    sk = sk or SKINS["classic"]
    cols = sk["deco_cols"].get(kind) or SKINS["classic"]["deco_cols"].get(kind) or [GOLD, GOLD, RED]
    shape = SHAPES.get(kind, _star)
    for x0, y0, x1, y1 in zones:
        if x1 - x0 < 170:
            continue
        placed = []
        for _ in range(60):
            r = rnd.choice([70, 90, 110, 150]) * min(1.0, (x1 - x0) / 420)
            cx, cy = rnd.uniform(x0 + r, x1 - r), rnd.uniform(y0 + r, y1 - r)
            if any((cx - px) ** 2 + (cy - py) ** 2 < (r + pr + 60) ** 2 for px, py, pr in placed):
                continue
            placed.append((cx, cy, r))
            col = rnd.choice(cols)
            if kind == "snow" and rnd.random() < 0.7:
                _snowflake(d, cx, cy, r, col)
            elif kind in ("snow", "lights"):
                _star(d, cx, cy, r, col)
            else:
                shape(d, cx, cy, r, col)
            if len(placed) >= 5:
                break


def compose(art, name, tagline, k, skin_name=None):
    """One finished 3600 px transparent design in the festive look, in the theme's skin."""
    sk = skin(skin_name)
    fill, band, kind, deco, layout = sk["schemes"][k % len(sk["schemes"])]
    rnd = random.Random(7000 + k)
    c = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    nm = sticker_text(name, kind, fill, SIZE * 0.94, 860)
    rb = ribbon(tagline.upper(), band, SIZE * 0.92) if tagline else None
    top = 400 if deco == "lights" else 60
    gap = 40
    room = SIZE - top - 60 - (rb.height + gap if rb else 0)
    a = art.copy()
    a.thumbnail((int(SIZE * 0.84), int((room - nm.height) / 0.88)), Image.LANCZOS)
    lap = int(min(a.height * 0.12, nm.height * 0.34))  # the name overlaps the character's feet
    block = a.height + nm.height - lap
    y = top + (room - block) // 2
    if rb and layout == "above":
        c.alpha_composite(rb, ((SIZE - rb.width) // 2, y))
        y += rb.height + gap
    ax = (SIZE - a.width) // 2
    if deco == "lights":
        _lights(c, SIZE * 0.04, SIZE * 0.96, max(40, y - 370), 110, rnd, sk["bulbs"])
    _sprinkle(c, deco, [(60, y, ax - 40, y + int(a.height * 0.8)),
                        (ax + a.width + 40, y, SIZE - 60, y + int(a.height * 0.8))], rnd, sk)
    c.alpha_composite(a, (ax, y))
    c.alpha_composite(nm, ((SIZE - nm.width) // 2, y + a.height - lap))
    if rb and layout == "under":
        c.alpha_composite(rb, ((SIZE - rb.width) // 2, y + block + gap))
    return c


# ---------------------------------------------------------------- listing photos (2000 x 2000)
def backdrop(colour, seed=1):
    """Deep red / green (or a skin's own (inner, outer) pair) with a soft glow, out-of-focus lights and a little snow."""
    named = dict(zip(("red", "green", "blue"), SKINS["classic"]["backdrops"]))
    inner, outer = named[colour] if isinstance(colour, str) else colour
    yy, xx = np.mgrid[0:PHOTO, 0:PHOTO].astype(np.float32)
    t = np.clip(np.hypot(xx - PHOTO / 2, yy - PHOTO * 0.46) / (PHOTO * 0.78), 0, 1)[..., None] ** 1.4
    img = Image.fromarray((np.array(inner) * (1 - t) + np.array(outer) * t).astype(np.uint8)).convert("RGBA")
    rnd = random.Random(seed)
    glow = Image.new("RGBA", (PHOTO, PHOTO), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for _ in range(46):
        r = rnd.randint(40, 170)
        x, y = rnd.randint(0, PHOTO), rnd.choice([rnd.randint(0, 520), rnd.randint(1480, PHOTO), rnd.randint(0, PHOTO)])
        col = rnd.choice([(255, 214, 120), (255, 240, 200), (255, 255, 255)])
        gd.ellipse((x - r, y - r, x + r, y + r), fill=col + (rnd.randint(16, 46),))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(9)))
    snow = Image.new("RGBA", (PHOTO, PHOTO), (0, 0, 0, 0))
    sd = ImageDraw.Draw(snow)
    for _ in range(130):
        r = rnd.choice([3, 4, 5, 7, 10])
        x, y = rnd.randint(0, PHOTO), rnd.randint(0, PHOTO)
        sd.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randint(70, 190)))
    img.alpha_composite(snow)
    return img


def _fit(dsg, size):
    s = dsg.copy()
    s.thumbnail((size, size), Image.LANCZOS)
    return s


def _card(dsg, size, checker=False, pad=0.06):
    """A design on a white (or transparent-checker) rounded card."""
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    face = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    if checker:
        fd, q = ImageDraw.Draw(face), max(18, size // 22)
        for yy in range(0, size, q):
            for xx in range(0, size, q):
                if (xx // q + yy // q) % 2:
                    fd.rectangle((xx, yy, xx + q, yy + q), fill=(226, 228, 232, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 12, fill=255)
    card.paste(face, (0, 0), mask)
    s = _fit(dsg, int(size * (1 - 2 * pad)))
    card.alpha_composite(s, ((size - s.width) // 2, (size - s.height) // 2))
    return card


def _heading(c, text, y, size=150, fill=WHITE, kind="bold", max_w=PHOTO - 160):
    d = ImageDraw.Draw(c)
    f = DF.fit(d, text, kind, max_w, size, 60)
    d.text((PHOTO / 2 + 5, y + 7), text, font=f, fill=(0, 0, 0, 90), anchor="mm")
    d.text((PHOTO / 2, y), text, font=f, fill=fill + (255,), anchor="mm")


def _burst(lines, r, fill=GOLD):
    """A round starburst badge with two lines of text."""
    b = Image.new("RGBA", (2 * r + 20, 2 * r + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    cx = cy = r + 10
    pts = [(cx + math.cos(math.pi / 14 * i) * (r if i % 2 == 0 else r * 0.86),
            cy + math.sin(math.pi / 14 * i) * (r if i % 2 == 0 else r * 0.86)) for i in range(28)]
    d.polygon(pts, fill=fill + (255,))
    d.ellipse((cx - r * 0.76, cy - r * 0.76, cx + r * 0.76, cy + r * 0.76), outline=WHITE + (255,), width=max(4, r // 28))
    f1 = DF.fit(d, lines[0], "bold", r * 1.2, int(r * 0.78), 30)
    f2 = DF.fit(d, lines[1], "bold", r * 1.2, int(r * 0.34), 20)
    d.text((cx, cy - r * 0.12), lines[0], font=f1, fill=INK + (255,), anchor="mm")
    d.text((cx, cy + r * 0.40), lines[1], font=f2, fill=INK + (255,), anchor="mm")
    return b.rotate(-10, resample=Image.BICUBIC)


def _pill(c, text, y, fill=WHITE, ink=INK, size=74):
    d = ImageDraw.Draw(c)
    f = font("sans_bold", size)
    while d.textlength(text, font=f) > PHOTO - 260 and size > 36:
        size -= 3
        f = font("sans_bold", size)
    tw = d.textlength(text, font=f)
    box = (PHOTO / 2 - tw / 2 - size, y - size * 0.95, PHOTO / 2 + tw / 2 + size, y + size * 0.95)
    d.rounded_rectangle((box[0] + 6, box[1] + 10, box[2] + 6, box[3] + 10), radius=int(size), fill=(0, 0, 0, 70))
    d.rounded_rectangle(box, radius=int(size), fill=fill + (255,))
    d.text((PHOTO / 2, y), text, font=f, fill=ink + (255,), anchor="mm")


def _on_tee(dsg, colour, w):
    t = SB._tee(colour, w, int(w * 1.09))
    s = _fit(dsg, int(t.width * 0.50))
    t.alpha_composite(s, ((t.width - s.width) // 2, int(t.height * 0.19)))
    return t


def _mug(dsg, mw=1000):
    """A white 11 oz mug drawn by code, the design curved by soft side shading."""
    mh = int(mw * 1.04)
    body = Image.new("RGB", (mw, mh), (252, 252, 252))
    s = _fit(dsg, int(mw * 0.70))
    body.paste(s, ((mw - s.width) // 2, (mh - s.height) // 2 + 20), s)
    a = np.asarray(body).astype(np.float32)
    xs = np.arange(mw)
    theta = np.arcsin(np.clip((xs - mw / 2) / (mw / 2), -0.999, 0.999))
    shade = 0.72 + 0.28 * np.cos(theta)
    hl = np.exp(-((xs - mw * 0.28) / (mw * 0.05)) ** 2) * 30
    a = np.clip(a * shade[None, :, None] + hl[None, :, None], 0, 255).astype(np.uint8)
    mug = Image.new("RGBA", (int(mw * 1.40), mh + 80), (0, 0, 0, 0))
    md = ImageDraw.Draw(mug)
    md.rounded_rectangle((mw - 60, mh * .22, mw * 1.34, mh * .78), radius=int(mw * 0.18), outline=(236, 236, 236, 255),
                         width=int(mw * 0.085))
    bimg = Image.fromarray(a).convert("RGBA")
    mask = Image.new("L", (mw, mh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mw - 1, mh - 1), radius=50, fill=255)
    bimg.putalpha(mask)
    mug.alpha_composite(bimg, (0, 40))
    md.ellipse((0, 0, mw, 86), fill=(238, 238, 238, 255), outline=(214, 214, 214, 255), width=6)
    return mug


def _disc(d_size, ring=GOLD):
    disc = Image.new("RGBA", (d_size, d_size), (0, 0, 0, 0))
    dd = ImageDraw.Draw(disc)
    dd.ellipse((0, 0, d_size - 1, d_size - 1), fill=ring + (255,))
    w = max(8, d_size // 46)
    dd.ellipse((w, w, d_size - 1 - w, d_size - 1 - w), fill=(255, 252, 246, 255))
    return disc


def _bg(sk, which, seed):
    """which: 0 = the skin's first backdrop (classic: red), 1 = second (green), 2 = third (blue)."""
    return backdrop(sk["backdrops"][which % len(sk["backdrops"])], seed)


def cover(dsgs, arts, n, kind, sk=None):
    """First photo: one design very large (readable as a thumbnail), the others around it, on a shirt and a mug."""
    sk = sk or SKINS["classic"]
    c = _bg(sk, 0, 11)
    _heading(c, f"CUSTOM {kind.upper()} NAME", 150, size=250)
    d = ImageDraw.Draw(c)
    f = DF.fit(d, sk["sub"], "script", PHOTO - 420, 104, 50)
    d.text((PHOTO / 2, 322), sk["sub"], font=f, fill=sk["sub_col"] + (255,), anchor="mm")
    disc = _disc(1180, sk["accent"])
    hero = _fit(dsgs[0], 900)
    disc.alpha_composite(hero, ((disc.width - hero.width) // 2, (disc.height - hero.height) // 2 + 10))
    paste_with_shadow(c, disc, (60, 440), radius=34, offset=(0, 28), opacity=120)
    tee = _on_tee(dsgs[1 % n], (250, 248, 244), 760)
    paste_with_shadow(c, tee, (1210, 400), radius=30, offset=(0, 24), opacity=110, angle=-6)
    mug = _mug(dsgs[2 % n], 520)
    paste_with_shadow(c, mug, (1270, 1160), radius=28, offset=(0, 22), opacity=120)
    rest = [k for k in range(n) if k != 0][-3:]
    for i, k in enumerate(rest):  # the other characters as small round chips
        chip = _disc(300, sk["accent"])
        a = _fit(arts[k], 236)
        chip.alpha_composite(a, ((300 - a.width) // 2, (300 - a.height) // 2))
        paste_with_shadow(c, chip, (90 + i * 330, 1540), radius=18, offset=(0, 14), opacity=110)
    b = _burst((f"{n}", "DESIGNS"), 210, sk["accent"])
    c.alpha_composite(b, (930, 400))
    _pill(c, "TYPE ANY NAME  ·  WE MAKE IT FOR YOU", 1900, size=64)
    return c.convert("RGB")


def all_designs(dsgs, n, sk=None):
    c = _bg(sk or SKINS["classic"], 1, 21)
    _heading(c, f"{n} DESIGNS  ·  ALL WITH YOUR NAME", 150, size=170)
    cols = 3
    rows = math.ceil(n / cols)
    size = 590
    gx = (PHOTO - cols * size) // (cols + 1)
    y0 = 300 + (PHOTO - 300 - 60 - rows * size - (rows - 1) * gx) // 2
    for i, dsg in enumerate(dsgs):
        x, y = gx + (i % cols) * (size + gx), y0 + (i // cols) * (size + gx)
        paste_with_shadow(c, _card(dsg, size), (x, y), radius=22, offset=(0, 18), opacity=120)
    return c.convert("RGB")


def any_name(make, names, sk=None):
    """The same design with three different names + how to order."""
    sk = sk or SKINS["classic"]
    c = _bg(sk, 0, 31)
    _heading(c, "ANY NAME YOU LIKE", 150, size=210)
    size = 590
    gx = (PHOTO - 3 * size) // 4
    for i, nm in enumerate(names[:3]):
        paste_with_shadow(c, _card(make(i, nm), size), (gx + i * (size + gx), 310), radius=22, offset=(0, 18), opacity=120)
    d = ImageDraw.Draw(c)
    steps = ["Type the name in the personalization box", "We write it into every design",
             "Download your files within 24 hours"]
    size = 78
    while max(d.textlength(t, font=font("sans_bold", size)) for t in steps) > PHOTO - 410 - 110:
        size -= 2
    f, fn = font("sans_bold", size), DF.get("bold", 130)
    for i, t in enumerate(steps):
        y = 1190 + i * 270
        d.ellipse((150, y - 95, 340, y + 95), fill=sk["accent"] + (255,), outline=WHITE + (255,), width=10)
        d.text((245, y + 6), str(i + 1), font=fn, fill=INK + (255,), anchor="mm")
        d.text((410, y), t, font=f, fill=WHITE + (255,), anchor="lm")
    return c.convert("RGB")


def shirts(dsgs, n, sk=None):
    sk = sk or SKINS["classic"]
    c = _bg(sk, 1, 41)
    _heading(c, "SHIRTS  ·  PAJAMAS  ·  SWEATSHIRTS", 150, size=160)
    paste_with_shadow(c, _on_tee(dsgs[2 % n], (250, 248, 244), 1000), (30, 400), radius=32, offset=(0, 26), opacity=120, angle=5)
    paste_with_shadow(c, _on_tee(dsgs[1 % n], sk["tee"], 1000), (800, 560), radius=32, offset=(0, 26), opacity=120, angle=-6)
    _pill(c, "WHITE EDGE: PRINTS ON LIGHT & DARK FABRIC", 1890, size=60)
    return c.convert("RGB")


def mugs(dsgs, n, sk=None):
    c = _bg(sk or SKINS["classic"], 0, 51)
    _heading(c, "11 OZ MUG WRAPS INCLUDED", 150, size=180)
    paste_with_shadow(c, _mug(dsgs[3 % n], 840), (120, 520), radius=32, offset=(0, 26), opacity=130)
    paste_with_shadow(c, _mug(dsgs[4 % n], 620), (1120, 980), radius=30, offset=(0, 24), opacity=130)
    _pill(c, "READY TO PRESS  ·  NO EDITING NEEDED", 1890, size=64)
    return c.convert("RGB")


def transparent(dsgs, n, sk=None):
    c = _bg(sk or SKINS["classic"], 2, 61)
    _heading(c, "TRANSPARENT BACKGROUND PNG", 150, size=170)
    size = 760
    gx = (PHOTO - 2 * size) // 3
    for i, dsg in enumerate(dsgs[:4]):
        paste_with_shadow(c, _card(dsg, size, checker=True), (gx + (i % 2) * (size + gx), 320 + (i // 2) * (size + gx // 2 + 30)),
                          radius=22, offset=(0, 18), opacity=120)
    return c.convert("RGB")


def what_you_get(dsgs, n, sk=None):
    sk = sk or SKINS["classic"]
    c = _bg(sk, 1, 71)
    _heading(c, "WHAT YOU GET", 150, size=210)
    paste_with_shadow(c, _card(dsgs[5 % n], 860), (1060, 560), radius=24, offset=(0, 20), opacity=120, angle=-4)
    d = ImageDraw.Draw(c)
    lines = [f"{n} PNG designs\nwith your name", "3600 x 3600 px\n300 DPI", f"{n} ready 11 oz\nmug wraps", "Transparent\nbackground",
             "Sent within\n24 hours"]
    f = font("sans_bold", 80)
    for i, t in enumerate(lines):
        y = 480 + i * 290
        _star(d, 190, y, 70, sk["accent"])
        d.multiline_text((310, y), t, font=f, fill=WHITE + (255,), anchor="lm", spacing=14)
    return c.convert("RGB")


def photos(dsgs, arts, n, kind, make, names, skin_name=None):
    """Listing photos, all square, in the theme's skin: [(file name, image)]."""
    sk = skin(skin_name)
    return [("00-cover.jpg", cover(dsgs, arts, n, kind, sk)),
            ("01-all.jpg", all_designs(dsgs, n, sk)),
            ("02-order.jpg", any_name(make, names, sk)),
            ("03-shirts.jpg", shirts(dsgs, n, sk)),
            ("04-mug.jpg", mugs(dsgs, n, sk)),
            ("05-transparent.jpg", transparent(dsgs, n, sk)),
            ("06-what.jpg", what_you_get(dsgs, n, sk))]
