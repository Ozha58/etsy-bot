"""Big eye-catching cover for coloring page packs (Pillow only, no image-model quota)."""
from PIL import Image, ImageDraw, ImageOps

from .imgutil import font, paste_with_shadow
from .mockups import H, W, _mix, palette_colors

GOLD = (222, 186, 102)
CREAM = (250, 244, 232)


def _page_card(im, height, angle):
    w = int(height * 0.775)
    t = ImageOps.fit(im.convert("RGB"), (w, height), Image.LANCZOS)
    t = ImageOps.expand(t, border=12, fill=(235, 228, 214))
    t = t.convert("RGBA")
    return t.rotate(angle, expand=True, resample=Image.BICUBIC)


def _wrap_title(d, text, max_w, max_lines=4):
    words = text.upper().split()
    for size in range(190, 50, -6):
        f = font("serif", size)
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
        if len(lines) <= max_lines and all(d.textlength(x, font=f) <= max_w for x in lines):
            return f, lines
    f = font("serif", 50)
    return f, [text.upper()[:40]]


def cover(previews, colored, title, count, palette):
    """Left: deep festive panel with a big title. Right: a line-art page and a colored example, big."""
    pal = palette_colors(palette)
    paper = _mix(pal["all"][0], CREAM, 0.88)
    canvas = Image.new("RGBA", (W, H), paper + (255,))
    split = 1000
    panel = _mix(pal["text"], (60, 10, 14), 0.55)
    ImageDraw.Draw(canvas).rectangle((0, 0, split, H), fill=panel + (255,))
    # pages on the right
    back = _page_card(previews[0], 1340, -6)
    front = _page_card(colored, 1340, 5)
    paste_with_shadow(canvas, back, (split + 20, 250), radius=26, offset=(0, 14), opacity=120)
    paste_with_shadow(canvas, front, (split + 215, 190), radius=26, offset=(0, 14), opacity=120)
    d = ImageDraw.Draw(canvas)
    d.rectangle((34, 34, W - 35, H - 35), outline=GOLD + (255,), width=6)
    # left text
    sf = font("sans_bold", 52)
    d.text((90, 150), "PRINTABLE COLORING PAGES", font=sf, fill=GOLD + (255,))
    tf, lines = _wrap_title(d, title, split - 190)
    y = 270
    for ln in lines:
        d.text((94, y + 5), ln, font=tf, fill=(0, 0, 0, 120))
        d.text((90, y), ln, font=tf, fill=CREAM + (255,))
        y += int(tf.size * 1.12)
    d.line((90, y + 30, 520, y + 30), fill=GOLD + (255,), width=7)
    # count badge
    cx, cy, r = 280, H - 600, 150
    d.ellipse((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10), fill=CREAM + (255,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD + (255,))
    ink = _mix(pal["text"], (40, 8, 8), 0.4) + (255,)
    nf = font("sans_bold", 150)
    d.text((cx - d.textlength(str(count), font=nf) / 2, cy - 118), str(count), font=nf, fill=ink)
    lf = font("sans_bold", 46)
    d.text((cx - d.textlength("PAGES", font=lf) / 2, cy + 36), "PAGES", font=lf, fill=ink)
    # pills
    pf = font("sans_bold", 46)
    items = [("US LETTER + A4 PDF", CREAM), ("INSTANT DOWNLOAD", GOLD)]
    yy = H - 330
    for t, bg in items:
        tw = d.textlength(t, font=pf)
        h = pf.size + 40
        d.rounded_rectangle((90, yy, 90 + tw + 80, yy + h), radius=h // 2, fill=bg + (255,))
        d.text((130, yy + 18), t, font=pf, fill=panel + (255,))
        yy += h + 28
    return canvas.convert("RGB")
