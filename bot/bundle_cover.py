"""Loud "bundle" style first listing image (Pillow only, no image-model quota).

The look follows the best selling digital-bundle thumbnails on Etsy:
  * the whole canvas is a dense collage of the real product items
  * a big centre badge with a huge outlined count ("15", "120+"), the product word
    ("CLIPART PNG") and "BUNDLE" in heavy outlined type
  * a diagonal corner ribbon, a round sticker and a bottom feature strip

The count always comes from the real number of files in the product: never inflate it.
"""
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .imgutil import fit_text, font, paste_with_shadow
from .mockups import H, W, _mix, palette_colors

WHITE = (255, 255, 255)
INK = (34, 24, 28)
GOLD_TOP, GOLD_BOTTOM = (255, 226, 120), (214, 140, 28)
SAFE_X0, SAFE_X1 = (W - H) // 2 + 20, (W + H) // 2 - 20  # centre square that survives Etsy's square crop


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


def collage_bg(items, sch, seed=3):
    """Fill the whole canvas with the product items (edge to edge, slightly rotated)."""
    rnd = random.Random(seed)
    items = [im for im in items if im is not None]
    cut = sum(_is_cutout(im) for im in items) > len(items) / 2
    base = _mix(sch["light"], WHITE, 0.4) if cut else _mix(sch["dark"], INK, 0.2)
    canvas = Image.new("RGBA", (W, H), base + (255,))
    if cut:  # sunburst behind the cut-out items
        canvas.alpha_composite(_rays((W, H), (W / 2, H * 0.42), _mix(sch["main"], WHITE, 0.72), WHITE, alpha=255, n=36))
    if not items:
        return canvas
    # enough cells to cover the canvas; repeat items only when there are too few
    target = max(len(items), 35 if cut else 20)
    cols = max(4, round(math.sqrt(target * W / H)))
    rows = math.ceil(target / cols)
    cw, ch = W / cols, H / rows
    order = []
    while len(order) < cols * rows:
        batch = items[:]
        rnd.shuffle(batch)
        order += batch
    k = 0
    for r in range(rows):
        for c in range(cols):
            im = order[k]
            k += 1
            if cut:
                t = im.copy()
                t.thumbnail((int(cw * 1.4), int(ch * 1.4)), Image.LANCZOS)
                ang = rnd.uniform(-12, 12)
                t = t.rotate(ang, expand=True, resample=Image.BICUBIC)
                x = c * cw + cw / 2 - t.width / 2 + rnd.uniform(-cw * 0.12, cw * 0.12)
                y = r * ch + ch / 2 - t.height / 2 + rnd.uniform(-ch * 0.12, ch * 0.12)
                paste_with_shadow(canvas, t, (x, y), radius=10, offset=(4, 8), opacity=60)
            else:
                t = ImageOps.fit(im.convert("RGB"), (int(cw * 1.02), int(ch * 1.02)), Image.LANCZOS)
                t = ImageOps.expand(t, border=max(6, int(cw * 0.02)), fill=WHITE).convert("RGBA")
                ang = rnd.uniform(-5, 5)
                t = t.rotate(ang, expand=True, resample=Image.BICUBIC)
                paste_with_shadow(canvas, t, (c * cw + cw / 2 - t.width / 2, r * ch + ch / 2 - t.height / 2),
                                  radius=12, offset=(4, 10), opacity=90)
    # punchier colours, like the best-selling thumbnails
    rgb = ImageEnhance.Color(canvas.convert("RGB")).enhance(1.35)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
    return rgb.convert("RGBA")


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


def _feature_strip(canvas, features, sch):
    strip_h = 150
    y0 = H - strip_h
    layer = Image.new("RGBA", (W, strip_h), sch["dark"] + (245,))
    d = ImageDraw.Draw(layer)
    d.line((0, 0, W, 0), fill=GOLD_BOTTOM + (255,), width=8)
    # Etsy's phone/search views crop to the centre square (x SAFE_X0..SAFE_X1): keep the text inside it
    n = len(features)
    seg = (SAFE_X1 - SAFE_X0) / n
    f = _fit_font(max(features, key=len), "sans_bold", seg - 90, 50, 24)
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
    canvas = collage_bg(items, sch)
    strip_h = 150

    # ---- build the badge contents first, then size the panel around them
    pw = int(W * 0.56)
    inner_w = pw - 160
    parts = []  # (image, gap_after)
    if top_word:
        parts.append((_pill_img(top_word.upper(), WHITE, INK), 4))
    num = f"{count:,}{'+' if plus else ''}"
    nf = _fit_font(num, "sans_bold", inner_w * 0.95, 430, 120)
    parts.append((_shrink(outlined_text(num, nf, _mix(sch["main"], WHITE, 0.25), sch["main"], outer=sch["dark"]), inner_w), 0))
    kf = _fit_font(kind_word.upper(), "sans_bold", inner_w * 0.98, 160, 50)
    parts.append((_shrink(outlined_text(kind_word.upper(), kf, (70, 70, 80), INK, inner=WHITE, outer=WHITE, inner_w=0,
                                        outer_w=max(4, kf.size // 14), depth=max(2, kf.size // 30)), inner_w), 10))
    parts.append((_shrink(_banner(bundle_word, sch), inner_w), 14))
    if title:
        parts.append((_title_img(title, inner_w * 0.95, sch["dark"]), 0))

    pad_y = 80
    content_h = sum(im.height + g for im, g in parts)
    ph = min(content_h + 2 * pad_y, H - strip_h - 120)
    px = (W - pw) // 2
    py = int((H - strip_h - ph) / 2)

    # glowing coloured burst behind the panel so it pops off the collage
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).rounded_rectangle((px - 50, py - 50, px + pw + 50, py + ph + 50), radius=150, fill=210)
    glow = glow.filter(ImageFilter.GaussianBlur(55))
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

    if ribbon:
        _corner_ribbon(canvas, ribbon.upper(), sch["second"])
    if sticker:
        r = 165
        _sticker(canvas, min(SAFE_X1 - r, px + pw - 30), py + 30, r, *sticker, sch)
    _feature_strip(canvas, features or ["INSTANT DOWNLOAD", "300 DPI", "COMMERCIAL USE"], sch)
    return canvas.convert("RGB")

