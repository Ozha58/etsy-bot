"""Loud "bundle" style first listing image (Pillow only, no image-model quota).

The look follows the best selling digital-bundle thumbnails on Etsy (e.g. "700+ GNOMES PNG BUNDLE"):
  * a SQUARE canvas fully covered with big copies of the real product items (top and bottom rows stay visible)
  * a wide centre badge with a huge outlined count, the product word and "BUNDLE" in heavy outlined type
  * a tilted tag, a round sticker and feature pills, all on the badge

Etsy crops the first photo differently per screen: the phone app grid shows a 4:5 portrait crop, desktop search
a ~4:3 landscape crop, other places a square. Everything important (text, badge, tag, sticker, pills) therefore
sits inside the SAFE box = the part of the square that survives BOTH crops; only collage items reach outside it.

The count always comes from the real number of files in the product: never inflate it.
"""
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .imgutil import fit_text, font, paste_with_shadow
from .mockups import _mix, palette_colors

W, H = 2000, 2500  # 4:5 portrait: exactly the shape of the Etsy phone app grid, shown there uncropped
WHITE = (255, 255, 255)
INK = (34, 24, 28)
GOLD_TOP, GOLD_BOTTOM = (255, 226, 120), (214, 140, 28)
# the phone grid shows the whole 4:5 image; a 4:3 desktop crop keeps y 20..80 %, a square crop y 10..90 %.
# Text and badges stay inside x 6..94 %, y 21..79 % so they survive every crop.
SAFE_X0, SAFE_X1 = int(W * 0.06), int(W * 0.94)
SAFE_Y0, SAFE_Y1 = int(H * 0.21), int(H * 0.79)


# ---------------------------------------------------------------- colours
def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _vivid(c, min_sat=0.55):
    """Push a palette colour towards a saturated, punchy version of itself."""
    import colorsys
    r, g, b = (v / 255 for v in c)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    s = max(s, min_sat)
    l = min(max(l, 0.38), 0.52)
    return tuple(int(v * 255) for v in colorsys.hls_to_rgb(h, l, s))


def scheme(palette):
    pal = palette_colors(palette)
    cols = pal["all"]
    sat = lambda c: max(c) - min(c)
    main = _vivid(max(cols, key=sat))
    others = [c for c in cols if c != max(cols, key=sat)]
    second = _vivid(max(others, key=sat)) if others else _mix(main, INK, 0.45)
    if abs(_lum(second) - _lum(main)) < 25:
        second = _mix(main, INK, 0.5)
    dark = _mix(main, INK, 0.72)
    return {"main": main, "second": second, "dark": dark, "light": _mix(main, WHITE, 0.9)}


# ---------------------------------------------------------------- text helpers
def _gradient(size, top, bottom):
    w, h = size
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
    return Image.fromarray(np.repeat(arr, w, axis=1).astype(np.uint8), "RGB").convert("RGBA")


def outlined_text(text, f, fill_top, fill_bottom, inner=WHITE, outer=INK, inner_w=None, outer_w=None, depth=None):
    """Heavy sticker-style text: gradient fill, white inner outline, dark outer outline
    and a stacked 3D extrusion. Returns an RGBA image tightly cropped."""
    size = f.size
    inner_w = inner_w if inner_w is not None else max(4, int(size * 0.06))
    outer_w = outer_w if outer_w is not None else inner_w + max(4, int(size * 0.05))
    depth = depth if depth is not None else max(3, int(size * 0.05))
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    x0, y0, x1, y1 = probe.textbbox((0, 0), text, font=f, stroke_width=outer_w)
    pad = outer_w + depth + 6
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    org = (pad - x0, pad - y0)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    # 3D extrusion (down-right)
    for k in range(depth, 0, -1):
        d.text((org[0] + k * 0.6, org[1] + k), text, font=f, fill=outer, stroke_width=outer_w, stroke_fill=outer)
    d.text(org, text, font=f, fill=outer, stroke_width=outer_w, stroke_fill=outer)
    d.text(org, text, font=f, fill=inner, stroke_width=inner_w, stroke_fill=inner)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text(org, text, font=f, fill=255)
    grad = _gradient((w, h), fill_top, fill_bottom)
    # glossy highlight on the upper half of the letters
    hl = Image.new("L", (w, h), 0)
    ImageDraw.Draw(hl).rectangle((0, 0, w, org[1] + size * 0.42), fill=70)
    grad = Image.composite(Image.new("RGBA", (w, h), WHITE + (255,)), grad, hl)
    out.paste(grad, (0, 0), mask)
    return out.crop(out.getbbox())


def _fit_font(text, kind, max_w, start, min_size=30):
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    return fit_text(probe, text, kind, max_w, start, min_size)


# ---------------------------------------------------------------- background collage
def _is_cutout(im):
    if im.mode != "RGBA":
        return False
    a = np.asarray(im.getchannel("A"))
    return (a < 20).mean() > 0.08


def collage_bg(items, sch, seed=3, hole=None, bottom=0):
    """Fill the canvas with BIG product items. Cells hidden behind `hole` (the title panel) are skipped,
    so the real items end up where buyers can see them, inside Etsy's centre-square crop first."""
    rnd = random.Random(seed)
    items = [im for im in items if im is not None]
    cut = sum(_is_cutout(im) for im in items) > len(items) / 2
    base = _mix(sch["light"], WHITE, 0.4) if cut else _mix(sch["light"], WHITE, 0.55)
    canvas = Image.new("RGBA", (W, H), base + (255,))
    if cut:  # sunburst behind the cut-out items
        canvas.alpha_composite(_rays((W, H), (W / 2, H * 0.42), _mix(sch["main"], WHITE, 0.72), WHITE, alpha=255, n=36))
    if not items:
        return canvas
    if not cut:
        return _masonry(canvas, items, rnd)
    # 4 x 5 big cells (500 px: ~100 px per item on the phone grid) + a second layer of smaller items in the
    # gaps, so the whole background is packed with real product detail like the best-selling bundle covers
    cols, rows = 4, 5
    cw, ch = W / cols, (H - bottom) / rows
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    if hole:
        hx0, hy0, hx1, hy1 = hole
        inset = 0.25
        cells = [(r, c) for r, c in cells
                 if not (hx0 + cw * inset < (c + 0.5) * cw < hx1 - cw * inset and hy0 + ch * inset < (r + 0.5) * ch < hy1 - ch * inset)]
    visible = lambda rc: SAFE_X0 <= (rc[1] + 0.5) * cw <= SAFE_X1 and SAFE_Y0 - ch <= (rc[0] + 0.5) * ch <= SAFE_Y1 + ch
    # cells that survive every Etsy crop get the first (unique) items
    cells.sort(key=lambda rc: (not visible(rc), rnd.random()))
    order = []
    while len(order) < len(cells) * 2:
        batch = items[:]
        rnd.shuffle(batch)
        order += batch
    # layer 1: smaller items on the cell corners (fills every gap)
    if cut:
        for k, (r, c) in enumerate(cells):
            t = order[len(cells) + k].copy()
            t.thumbnail((int(cw * 0.62), int(ch * 0.62)), Image.LANCZOS)
            t = t.rotate(rnd.uniform(-20, 20), expand=True, resample=Image.BICUBIC)
            paste_with_shadow(canvas, t, ((c + 1) * cw - t.width / 2, (r + 1) * ch - t.height / 2),
                              radius=8, offset=(3, 6), opacity=50)
    # layer 2: big items; far cells first so the visible ones overlap them nicely
    for (r, c), im in sorted(zip(cells, order), key=lambda x: visible(x[0])):
        t = im.copy()
        t.thumbnail((int(cw * 1.12), int(ch * 1.12)), Image.LANCZOS)
        t = t.rotate(rnd.uniform(-12, 12), expand=True, resample=Image.BICUBIC)
        x = c * cw + cw / 2 - t.width / 2 + rnd.uniform(-cw * 0.1, cw * 0.1)
        y = r * ch + ch / 2 - t.height / 2 + rnd.uniform(-ch * 0.1, ch * 0.1)
        paste_with_shadow(canvas, t, (x, y), radius=10, offset=(4, 8), opacity=60)
    return _punch(canvas)


def _punch(canvas):
    """Punchier colours, like the best-selling thumbnails."""
    rgb = ImageEnhance.Color(canvas.convert("RGB")).enhance(1.3)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
    return rgb.convert("RGBA")


def _flat(im):
    """RGB copy; transparent pieces go on white, never on black."""
    if im.mode in ("RGBA", "LA", "P"):
        im = Image.alpha_composite(Image.new("RGBA", im.size, WHITE + (255,)), im.convert("RGBA"))
    return im.convert("RGB")


def _detail_pool(items, rnd, want=16):
    """Full items first, then close-up detail crops of them, so a product with only a few files still fills the
    cover with varied, real detail instead of the same picture repeated."""
    full = [_flat(im) for im in items]
    pool = full[:]
    k = 0
    while len(pool) < want and full:
        im = full[k % len(full)]
        z = rnd.choice((0.55, 0.42, 0.33))
        cw, ch = int(im.width * z), int(im.height * z)
        x, y = rnd.randint(0, im.width - cw), rnd.randint(0, im.height - ch)
        pool.append(im.crop((x, y, x + cw, y + ch)))
        k += 1
    return pool


def _masonry(canvas, items, rnd, gutter=22, row_h=440):
    """Neat justified rows (no rotation, aspect ratios kept, equal gutters), filled from the top and from the
    bottom so the rows buyers see above and below the title panel show the full items first."""
    pool = _detail_pool(items, rnd)
    full_n = min(len(items), len(pool))
    seq, last = [], None

    def take():
        nonlocal seq, last
        if not seq:
            seq = list(range(len(pool)))
            head, tail = seq[:full_n], seq[full_n:]
            rnd.shuffle(head)
            rnd.shuffle(tail)
            seq = head + tail
        i = seq.pop(0)
        if i == last and seq:  # never the same picture twice in a row
            seq.append(i)
            i = seq.pop(0)
        last = i
        return pool[i]

    def build_row():
        row, width = [], gutter
        while width < W * 0.98 or len(row) < 2:
            im = take()
            ratio = max(0.45, min(2.4, im.width / im.height))
            row.append((im, ratio))
            width += ratio * row_h + gutter
            if len(row) >= 5:
                break
        s = (W - gutter * (len(row) + 1)) / sum(r * row_h for _, r in row)
        return row, row_h * s

    def draw_row(row, h, y):
        x = gutter
        for im, ratio in row:
            w = int(round(ratio * h))
            tile = ImageOps.fit(im, (max(2, w - 12), max(2, int(h) - 12)), Image.LANCZOS)
            tile = ImageOps.expand(tile, border=6, fill=WHITE).convert("RGBA")
            paste_with_shadow(canvas, tile, (x, y), radius=10, offset=(0, 8), opacity=70)
            x += w + gutter

    top, bottom = gutter, H - gutter
    first_bottom = True
    while top < bottom:
        row, h = build_row()
        draw_row(row, h, top)
        top += h + gutter
        if top >= bottom:
            break
        if first_bottom:  # the bottom row also starts with the full items
            seq, first_bottom = [], False
        row, h = build_row()
        draw_row(row, h, bottom - h)
        bottom -= h + gutter
    return _punch(canvas)


# ---------------------------------------------------------------- decorations
def _corner_ribbon(canvas, text, bg, fg=WHITE):
    band_h = 150
    band = Image.new("RGBA", (1100, band_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(band)
    d.rectangle((0, 0, 1100, band_h), fill=bg + (255,))
    d.line((0, 14, 1100, 14), fill=WHITE + (200,), width=4)
    d.line((0, band_h - 15, 1100, band_h - 15), fill=WHITE + (200,), width=4)
    f = _fit_font(text, "sans_bold", 560, 96, 40)
    tw = d.textlength(text, font=f)
    d.text(((1100 - tw) / 2, band_h / 2 - f.size * 0.66), text, font=f, fill=fg + (255,))
    r = band.rotate(45, expand=True, resample=Image.BICUBIC)
    # centre of the band sits on the diagonal near the top-left corner
    cx, cy = 250, 250
    paste_with_shadow(canvas, r, (cx - r.width / 2, cy - r.height / 2), radius=14, offset=(6, 10), opacity=110)


def _sticker(canvas, cx, cy, radius, top, mid, bottom, sch):
    """Round starburst sticker, e.g. '300 DPI' / 'COMMERCIAL USE'."""
    size = radius * 2 + 40
    st = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(st)
    c = size / 2
    pts = []
    spikes = 28
    for i in range(spikes * 2):
        ang = math.pi * i / spikes
        rr = radius if i % 2 == 0 else radius * 0.9
        pts.append((c + rr * math.cos(ang), c + rr * math.sin(ang)))
    d.polygon(pts, fill=sch["second"] + (255,))
    d.ellipse((c - radius * 0.8, c - radius * 0.8, c + radius * 0.8, c + radius * 0.8), outline=WHITE + (255,), width=6)
    y = c - radius * 0.52
    for txt, kind, sz in ((top, "sans_medium", 0.2), (mid, "sans_bold", 0.42), (bottom, "sans_bold", 0.2)):
        if not txt:
            continue
        f = _fit_font(txt, kind, radius * (1.25 if kind == "sans_bold" and sz > 0.3 else 1.05), int(radius * sz), 18)
        tw = d.textlength(txt, font=f)
        d.text((c - tw / 2, y), txt, font=f, fill=WHITE + (255,))
        y += f.size * 1.12
    st = st.rotate(-12, resample=Image.BICUBIC)
    paste_with_shadow(canvas, st, (cx - size / 2, cy - size / 2), radius=16, offset=(6, 12), opacity=120)


def _feature_strip(canvas, features, sch, strip_h=150):
    y0 = H - strip_h
    layer = Image.new("RGBA", (W, strip_h), sch["dark"] + (245,))
    d = ImageDraw.Draw(layer)
    d.line((0, 0, W, 0), fill=GOLD_BOTTOM + (255,), width=8)
    # Etsy's phone/search views crop to the centre square (x SAFE_X0..SAFE_X1): keep the text inside it
    n = len(features)
    seg = (SAFE_X1 - SAFE_X0) / n
    f = _fit_font(max(features, key=len), "sans_bold", seg - 90, 60, 24)
    for i, feat in enumerate(features):
        cx = SAFE_X0 + seg * i + seg / 2
        tw = d.textlength(feat, font=f)
        d.ellipse((cx - tw / 2 - 52, strip_h / 2 - 14, cx - tw / 2 - 24, strip_h / 2 + 14), fill=GOLD_TOP + (255,))
        d.text((cx - tw / 2, strip_h / 2 - f.size * 0.68), feat, font=f, fill=WHITE + (255,))
        if i:
            lx = SAFE_X0 + seg * i
            d.line((lx, 35, lx, strip_h - 35), fill=WHITE + (90,), width=3)
    canvas.alpha_composite(layer, (0, y0))


def _rays(size, center, c1, c2, alpha=255, n=32):
    """Sunburst: alternating wedges of c1/c2 radiating from center (RGBA layer)."""
    w, h = size
    cx, cy = center
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = np.arctan2(yy - cy, xx - cx)
    stripe = ((ang + math.pi) / (2 * math.pi) * n).astype(np.int32) % 2
    a = np.array(c1, np.float32)
    b = np.array(c2, np.float32)
    rgb = np.where(stripe[..., None] == 1, a, b)
    # fade out towards the edges
    dist = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    al = np.clip(1.15 - dist * 1.3, 0, 1) * alpha
    out = np.dstack([rgb, al]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _sparkles(canvas, box, color, seed=5):
    """Four-point star sparkles around a box (e.g. the big number)."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    spots = [(x0 - 30, y0 + 40), (x1 + 25, y0 + 20), (x1 + 10, y1 - 60), (x0 - 10, y1 - 30),
             (x0 + (x1 - x0) * 0.35, y0 - 25), (x0 + (x1 - x0) * 0.8, y0 - 10)]
    for sx, sy in spots:
        r = rnd.randint(28, 52)
        k = r * 0.22
        pts = [(sx, sy - r), (sx + k, sy - k), (sx + r, sy), (sx + k, sy + k),
               (sx, sy + r), (sx - k, sy + k), (sx - r, sy), (sx - k, sy - k)]
        d.polygon(pts, fill=color + (255,))
        d.ellipse((sx - k, sy - k, sx + k, sy + k), fill=WHITE + (255,))
    glow = layer.filter(ImageFilter.GaussianBlur(10))
    canvas.alpha_composite(glow)
    canvas.alpha_composite(layer)


def _shrink(img, max_w):
    if img.width <= max_w:
        return img
    s = max_w / img.width
    return img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)


def _banner(word, sch):
    bun = outlined_text(word.upper(), font("sans_bold", 120), GOLD_TOP, GOLD_BOTTOM, inner=WHITE, outer=sch["dark"])
    bw_, bh_ = bun.width + 200, bun.height + 40
    banner = Image.new("RGBA", (bw_ + 120, bh_), (0, 0, 0, 0))
    bd = ImageDraw.Draw(banner)
    tail = _mix(sch["second"], INK, 0.35) + (255,)
    bd.polygon([(0, 20), (90, 20), (90, bh_ - 1), (0, bh_ - 1), (40, bh_ / 2 + 10)], fill=tail)
    bd.polygon([(bw_ + 119, 20), (bw_ + 29, 20), (bw_ + 29, bh_ - 1), (bw_ + 119, bh_ - 1), (bw_ + 79, bh_ / 2 + 10)], fill=tail)
    bd.rounded_rectangle((60, 0, bw_ + 60, bh_ - 20), radius=24, fill=sch["second"] + (255,))
    banner.alpha_composite(bun, (int(60 + (bw_ - bun.width) / 2), int((bh_ - 20 - bun.height) / 2)))
    return banner


def _pill_img(text, fg, bg, size=60):
    f = font("sans_bold", size)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    tw = probe.textlength(text, font=f)
    h = int(size * 1.7)
    im = Image.new("RGBA", (int(tw + size * 1.6), h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, h - 1), radius=h // 2, fill=bg + (255,))
    d.text((size * 0.8, h / 2 - size * 0.68), text, font=f, fill=fg + (255,))
    return im


def _title_img(title, max_w, color):
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    f = fit_text(probe, title, "serif_italic", max_w, 96, 40)
    x0, y0, x1, y1 = probe.textbbox((0, 0), title, font=f)
    im = Image.new("RGBA", (x1 - x0 + 8, y1 - y0 + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - x0, 4 - y0), title, font=f, fill=color + (255,))
    return im


# ---------------------------------------------------------------- main
def bundle_cover(items, count, kind_word, title, palette, *, bundle_word="BUNDLE", plus=False,
                 ribbon="MEGA PACK", sticker=("HIGH RES", "300", "DPI"), features=None, top_word=None):
    """
    items      – the real product images (cut-out PNGs or full pages / papers / prints)
    count      – real number of files in the product (never inflate it)
    kind_word  – what they are, e.g. "CLIPART PNG", "DIGITAL PAPERS", "COLORING PAGES"
    title      – collection name, shown in an elegant italic line
    top_word   – optional pill above the number, e.g. "SET OF"
    """
    sch = scheme(palette)

    # ---- build the badge contents first, then size the panel around them.
    # Wide and low (like the gnome bundle covers): two rows of product items stay visible above and below it.
    pw = int(W * 0.80)
    inner_w = pw - 140
    parts = []  # (image, gap_after)
    if top_word:
        parts.append((_pill_img(top_word.upper(), WHITE, INK, size=56), 0))
    num = f"{count:,}{'+' if plus else ''}"
    nf = _fit_font(num, "sans_bold", inner_w * 0.95, 400, 120)
    parts.append((_shrink(outlined_text(num, nf, _mix(sch["main"], WHITE, 0.25), sch["main"], outer=sch["dark"]), inner_w), 0))
    kf = _fit_font(kind_word.upper(), "sans_bold", inner_w * 0.98, 170, 50)
    parts.append((_shrink(outlined_text(kind_word.upper(), kf, (70, 70, 80), INK, inner=WHITE, outer=WHITE, inner_w=0,
                                        outer_w=max(4, kf.size // 14), depth=max(2, kf.size // 30)), inner_w), 6))
    parts.append((_shrink(_banner(bundle_word, sch), inner_w * 0.8), 8))
    if title:
        parts.append((_title_img(title, inner_w * 0.92, sch["dark"]), 0))

    pad_y = 55
    content_h = sum(im.height + g for im, g in parts)
    pills_h = 120
    ph = min(content_h + 2 * pad_y, SAFE_Y1 - SAFE_Y0 - pills_h - 120)
    px = (W - pw) // 2
    py = int((H - ph - pills_h * 0.6) / 2)
    canvas = collage_bg(items, sch, hole=(px, py, px + pw, py + ph))

    # tight glow behind the panel so it pops off the collage without hiding the items
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).rounded_rectangle((px - 25, py - 25, px + pw + 25, py + ph + 25), radius=120, fill=200)
    glow = glow.filter(ImageFilter.GaussianBlur(30))
    canvas = Image.composite(Image.new("RGBA", (W, H), _mix(sch["main"], WHITE, 0.15) + (255,)), canvas, glow)

    panel = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((0, 0, pw - 1, ph - 1), radius=90, fill=GOLD_BOTTOM + (255,))
    pd.rounded_rectangle((10, 10, pw - 11, ph - 11), radius=82, fill=sch["main"] + (255,))
    pd.rounded_rectangle((30, 30, pw - 31, ph - 31), radius=66, fill=WHITE + (255,))
    inner = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(inner).rounded_rectangle((30, 30, pw - 31, ph - 31), radius=66, fill=255)
    burst = _rays((pw, ph), (pw / 2, ph * 0.36), _mix(sch["main"], WHITE, 0.82), WHITE, alpha=255, n=28)
    burst = Image.alpha_composite(Image.new("RGBA", (pw, ph), WHITE + (255,)), burst)  # opaque
    panel.paste(burst, (0, 0), inner)
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((46, 46, pw - 47, ph - 47), radius=54, outline=GOLD_BOTTOM + (255,), width=5)
    paste_with_shadow(canvas, panel, (px, py), radius=40, offset=(0, 26), opacity=160)

    y = py + (ph - content_h) / 2
    for k, (im, gap) in enumerate(parts):
        x = int(W / 2 - im.width / 2)
        if k == (1 if top_word else 0):  # the big number: soft coloured glow + sparkles
            g = Image.new("RGBA", im.size, sch["main"] + (0,))
            g.putalpha(im.getchannel("A").point(lambda v: v * 0.55))
            pad = 60
            gl = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
            gl.alpha_composite(g, (pad, pad))
            canvas.alpha_composite(gl.filter(ImageFilter.GaussianBlur(28)), (x - pad, int(y) - pad))
            canvas.alpha_composite(im, (x, int(y)))
            _sparkles(canvas, (x, int(y), x + im.width, int(y) + im.height), GOLD_TOP)
        else:
            canvas.alpha_composite(im, (x, int(y)))
        y += im.height + gap

    if ribbon:  # tilted tag on the panel's top-left corner: stays inside Etsy's square crop
        tag = _pill_img(ribbon.upper(), WHITE, sch["second"], size=60).rotate(8, expand=True, resample=Image.BICUBIC)
        paste_with_shadow(canvas, tag, (max(SAFE_X0, px - tag.width * 0.35), py - tag.height * 0.55),
                          radius=12, offset=(4, 10), opacity=120)
    if sticker:
        r = 150
        _sticker(canvas, min(SAFE_X1 - r, px + pw - 20), py + 20, r, *sticker, sch)
    # feature pills hanging under the panel (inside the safe box, readable on a phone)
    feats = (features or ["INSTANT DOWNLOAD", "300 DPI", "COMMERCIAL USE"])[:3]
    pills = [_pill_img(f, WHITE, sch["dark"], size=50) for f in feats]
    gap = 24
    total = sum(p.width for p in pills) + gap * (len(pills) - 1)
    if total > pw - 40:
        s = (pw - 40) / total
        pills = [p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS) for p in pills]
        total = sum(p.width for p in pills) + gap * (len(pills) - 1)
    x = (W - total) / 2
    for p in pills:
        paste_with_shadow(canvas, p, (x, py + ph - p.height * 0.35), radius=10, offset=(0, 8), opacity=110)
        x += p.width + gap
    return canvas.convert("RGB")

