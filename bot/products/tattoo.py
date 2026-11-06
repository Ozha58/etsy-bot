"""Custom birth flower name tattoo design (made-to-order digital).

The buyer writes "Name - Month" at checkout (e.g. "Emma - July"). The listing keeps 12 fine-line flower drawings,
one per birth month (12 AI images once per listing). For every order the bot joins the month's flower with the name
in a fine script and sends: 2 layouts (name across the stem / name under the flower) as black transparent PNG, a
white version for dark skin previews, and a printable stencil PDF in 3 sizes. The owner uploads the ZIP to the order."""
import io
import re

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .. import assets, images, mockups
from .. import display_fonts as DF
from ..imgutil import color_to_alpha_background, font, jpeg_bytes, make_zips, png_bytes, thumb_b64, trim_alpha

LABEL_TR = "Kişiye özel doğum çiçeği + isim dövme tasarımı (alıcı 'İsim - Ay' yazar, bot hazırlar)"
SPEC_FIELDS = """
  "set_name": "short style name, 2-4 words (e.g. 'Fine Line Birth Flower')",
  "sample_name": "a short first name shown on the photos (e.g. 'Emma')"
"""
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
FLOWERS = ["carnation", "violet", "daffodil", "daisy", "lily of the valley", "rose", "water lily", "gladiolus",
           "aster", "marigold", "chrysanthemum", "narcissus"]
SUFFIX = ("single delicate flower stem with two small leaves, fine line tattoo design, thin clean black ink line art, "
          "minimalist botanical illustration, vertical composition, pure white background, no shading, no fill, "
          "no color, no text, no letters, no frame")
S = 3000
INK = (20, 20, 22)


def parse(text):
    """'Emma - July' / 'July Emma' / 'Emma 7' -> ('Emma', 6). Month None if missing."""
    t = str(text or "").strip()
    month = None
    for i, m in enumerate(MONTHS):
        hit = re.search(rf"\b({m}|{m[:3]})\b\.?", t, re.I)
        if hit:
            month, t = i, (t[:hit.start()] + t[hit.end():])
            break
    if month is None:
        hit = re.search(r"\b(1[0-2]|0?[1-9])\b", t)
        if hit:
            month, t = int(hit.group(1)) - 1, t[:hit.start()] + t[hit.end():]
    name = re.sub(r"[^A-Za-zÀ-ɏ '\-]", " ", t)
    name = re.sub(r"\s+", " ", name).strip(" -'")[:24]
    return name, month


def _line_art(im):
    """AI drawing -> crisp black line art on transparent background."""
    a = trim_alpha(color_to_alpha_background(im))
    g = ImageOps.grayscale(a.convert("RGB"))
    alpha = a.split()[-1]
    dark = g.point(lambda v: 255 if v < 170 else 0)
    alpha = Image.composite(alpha, Image.new("L", a.size, 0), dark)
    out = Image.new("RGBA", a.size, INK + (0,))
    out.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.6)))
    bb = out.getbbox()
    return out.crop(bb) if bb else out


def _name_img(name, size, color=INK):
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    f = DF.get("elegant", size)
    b = probe.textbbox((0, 0), name, font=f)
    im = Image.new("RGBA", (b[2] - b[0] + 60, b[3] - b[1] + 60), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((30 - b[0], 30 - b[1]), name, font=f, fill=color + (255,))
    return im


def _fit(im, w, h):
    """Scale up OR down to fit the box (thumbnail() only shrinks)."""
    k = min(w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)


def compose(flower, name, layout):
    """'across': the name crosses the lower stem; 'under': the name sits below the flower."""
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    nm = _fit(_name_img(name, 420), S * 0.62, 560)
    if layout == "across":
        fl = _fit(flower, S * 0.55, S * 0.9)
        fx, fy = (S - fl.width) // 2, (S - fl.height) // 2
        c.alpha_composite(fl, (fx, fy))
        c.alpha_composite(nm, ((S - nm.width) // 2 + int(S * 0.05), fy + int(fl.height * 0.6)))
    else:
        fl = _fit(flower, S * 0.5, S - nm.height - 300)
        y = (S - fl.height - nm.height - 40) // 2
        c.alpha_composite(fl, ((S - fl.width) // 2, y))
        c.alpha_composite(nm, ((S - nm.width) // 2, y + fl.height + 40))
    bb = c.getbbox()
    return c.crop((max(0, bb[0] - 60), max(0, bb[1] - 60), min(S, bb[2] + 60), min(S, bb[3] + 60))) if bb else c


def _recolor(im, color):
    out = Image.new("RGBA", im.size, color + (0,))
    out.putalpha(im.split()[-1])
    return out


def _stencil_pdf(designs, name, month):
    """US Letter page per layout with the tattoo at 2, 3 and 4 inches tall (300 DPI)."""
    pages = []
    for d in designs:
        page = Image.new("RGB", (2550, 3300), "white")
        dr = ImageDraw.Draw(page)
        dr.text((1275, 150), f"{name} · {MONTHS[month]} · {FLOWERS[month].title()}", font=font("sans", 48),
                fill=(90, 90, 90), anchor="mm")
        x = 120
        for inch in (2, 3, 4):
            t = d.copy()
            h = inch * 300
            t = t.resize((max(1, int(t.width * h / t.height)), h), Image.LANCZOS)
            if x + t.width > 2450:
                x = 120
            page.paste(t, (x, 3300 - h - 300), t)
            dr.text((x + t.width / 2, 3300 - 230), f"{inch} in", font=font("sans", 40), fill=(120, 120, 120), anchor="mm")
            x += t.width + 120
        pages.append(page)
    b = io.BytesIO()
    pages[0].save(b, "PDF", save_all=True, append_images=pages[1:], resolution=300)
    return b.getvalue()


def render(p, text):
    """Files for one order. Raises ValueError (Turkish) if the month or name is missing."""
    name, month = parse(text)
    if month is None:
        raise ValueError("doğum ayı yazılmamış")
    if not name:
        raise ValueError("isim yazılmamış")
    flower = Image.open(io.BytesIO(assets.download(p["id"], f"tattoo__flower-{month + 1:02d}.png"))).convert("RGBA")
    designs = [compose(flower, name, lay) for lay in ("across", "under")]
    safe = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "name"
    files = []
    for lay, d in zip(("name-across-stem", "name-under-flower"), designs):
        files.append((f"{safe}-{MONTHS[month].lower()}-{lay}-black.png", png_bytes(d)))
        files.append((f"{safe}-{MONTHS[month].lower()}-{lay}-white.png", png_bytes(_recolor(d, (255, 255, 255)))))
    files.append((f"{safe}-{MONTHS[month].lower()}-stencil-2-3-4-inch.pdf", _stencil_pdf(designs, name, month)))
    return files


def _on_skin(d, w=1100, h=1400):
    """The tattoo on a soft skin-tone panel (multiply, a touch of blur) for the listing photos."""
    skin = Image.new("RGB", (w, h), (226, 190, 165))
    px = skin.load()
    for y in range(h):
        for x in range(0, w, 4):
            v = int(10 * ((x - w / 2) / w) ** 2 * 4)
            col = (226 - v, 190 - v, 165 - v)
            for k in range(4):
                if x + k < w:
                    px[x + k, y] = col
    t = d.copy()
    t.thumbnail((int(w * 0.62), int(h * 0.78)), Image.LANCZOS)
    ink = Image.new("RGBA", t.size, (40, 38, 45, 0))
    ink.putalpha(t.split()[-1].point(lambda v: int(v * 0.85)).filter(ImageFilter.GaussianBlur(1.2)))
    skin = skin.convert("RGBA")
    skin.alpha_composite(ink, ((w - t.width) // 2, (h - t.height) // 2))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=60, fill=255)
    skin.putalpha(m)
    return skin


def build(spec, slug):
    palette = spec.get("palette") or ["#b98b73", "#6b705c", "#ddbea9", "#3f4238"]
    sample = (parse(spec.get("sample_name") or "Emma")[0] or "Emma").split()[0]
    flowers = []
    for i, fl in enumerate(FLOWERS):
        im = images.try_generate(f"a {fl}, {SUFFIX}", 768, 1024)
        if im is None and images.quota_exhausted():
            break
        flowers.append(_line_art(im) if im is not None else None)
    ok = [f for f in flowers if f is not None]
    images.need(len(ok), 12, ratio=1.0)  # every month must exist: a buyer may choose any of them

    samples = [compose(flowers[m], sample, "across" if m % 2 else "under") for m in range(12)]
    cells = []
    for m, d in enumerate(samples):
        cell = Image.new("RGBA", (700, 860), (255, 255, 255, 255))
        t = d.copy()
        t.thumbnail((600, 680), Image.LANCZOS)
        cell.alpha_composite(t, ((700 - t.width) // 2, 20 + (680 - t.height) // 2))
        dr = ImageDraw.Draw(cell)
        dr.text((350, 760), MONTHS[m], font=font("sans_bold", 46), fill=(60, 55, 50), anchor="mm")
        dr.text((350, 815), FLOWERS[m].title(), font=font("serif_italic", 38), fill=(120, 110, 100), anchor="mm")
        cells.append(cell.convert("RGB"))

    # cover: three tattoos on skin + title
    W = 2000
    cover = Image.new("RGBA", (W, W), (244, 238, 230, 255))
    d = ImageDraw.Draw(cover)
    d.rounded_rectangle((60, 50, W - 60, 400), radius=40, fill=(63, 66, 56, 255))
    t1 = "CUSTOM BIRTH FLOWER NAME TATTOO"
    d.text((W / 2, 170), t1, font=DF.fit(d, t1, "bold", W - 220, 150, 60), fill=(255, 255, 255), anchor="mm")
    d.text((W / 2, 305), "Fine Line · Your Name + Birth Month", font=DF.fit(d, "Fine Line · Your Name + Birth Month",
           "elegant", W - 300, 120, 60), fill=(240, 228, 210), anchor="mm")
    for i, (m, x) in enumerate(((6, 70), (2, 700), (10, 1330))):
        sk = _on_skin(samples[m], 600, 1250)
        mockups.paste_with_shadow(cover, sk, (x, 520 + (40 if i == 1 else 0)), radius=30, offset=(0, 18), opacity=60)
    cover = cover.convert("RGB")

    files = [("HOW-TO-RECEIVE-YOUR-TATTOO-DESIGN.pdf", _instructions(spec["title"])),
             ("all-12-birth-flowers-preview.jpg", jpeg_bytes(_wm(mockups.grid(cells, "12 Birth Flowers", palette, cols=4)), 80))]
    delivery = make_zips(slug, files, f"{spec['title']}\n\nYour personal tattoo design is sent within 24 hours.\n")
    mock = [
        ("00-cover.jpg", cover),
        ("01-months.jpg", mockups.grid(cells, "Choose Your Birth Month Flower", palette, cols=4)),
        ("02-order.jpg", mockups.info_card("HOW TO ORDER", ["Type: Name - Birth month",
                                                            "(e.g. Emma - July)",
                                                            "We send your design in 24 hours"], palette, samples[6])),
        ("03-styles.jpg", mockups.grid([compose(flowers[4], sample, "across"), compose(flowers[4], sample, "under")],
                                       "2 Layouts Included", palette, cols=2)),
        ("04-stencil.jpg", mockups.info_card("PRINTABLE STENCIL", ["Black + white PNG, transparent",
                                                                   "Stencil PDF: 2, 3 and 4 inch",
                                                                   "Take it to your tattoo artist"], palette, samples[0])),
        ("05-skin.jpg", mockups.grid([_on_skin(samples[m]).convert("RGB") for m in (0, 4, 8)], "Fine Line on Skin",
                                     palette, cols=3)),
    ]
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "own_cover": True,
        "extra_assets": {f"tattoo__flower-{m + 1:02d}.png": png_bytes(f) for m, f in enumerate(flowers) if f is not None},
        "listing": {"is_personalizable": True, "personalization_is_required": True,
                    "personalization_char_count_max": 40,
                    "personalization_instructions": "Name - Birth month (e.g. Emma - July). Sent within 24 hours."},
        "included": ["Your name + birth month flower, 2 layouts", "Black and white transparent PNG (high resolution)",
                     "Printable stencil PDF in 2, 3 and 4 inch", "Sent to you on Etsy within 24 hours"],
        "details": ["Made to order: type Name - Birth month in the personalization box",
                    "Digital design only, no physical item or temporary tattoo is shipped"],
        "usage": ["Show it to your tattoo artist or print the stencil", "Also lovely as a framed print or card"],
        "license": "Personal use. Please do not resell the design.",
        "taxonomy": ["Digital Prints", "Drawing & Illustration"],
        "taxonomy_fallback_id": 6844,
        "is_supply": False,
        "skip_attributes": ["room"],
        "count": 12,
    }


def _wm(im):
    im = im.convert("RGB")
    im.thumbnail((1000, 1000))
    d = ImageDraw.Draw(im, "RGBA")
    for y in range(80, im.height, 240):
        d.text((im.width / 2, y), "SAMPLE", font=font("sans_bold", 90), fill=(120, 120, 120, 90), anchor="mm")
    return im


def _instructions(title):
    page = Image.new("RGB", (2550, 3300), (252, 250, 246))
    d = ImageDraw.Draw(page)
    d.text((1275, 420), "Thank you for your order!", font=font("serif", 130), fill=(60, 50, 45), anchor="mm")
    y = 700
    for ln in [title, "", "Your tattoo design is made for you with the name and", "birth month you entered at checkout.",
               "You receive it within 24 hours here on Etsy:", "Purchases and reviews > this order > Download files.", "",
               "Please check the spelling you entered.", "If anything should change, just send us a message."]:
        d.text((1275, y), ln, font=font("sans", 62), fill=(70, 65, 60), anchor="mm")
        y += 110
    b = io.BytesIO()
    page.save(b, "PDF", resolution=300)
    return b.getvalue()
