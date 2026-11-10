"""Personalized PNG (made-to-order digital): the buyer types a name at checkout ("Mrs. Johnson", "The Smiths"),
the bot writes it into all 6 designs of the set and sends the finished files to Telegram; the shop owner uploads
them to the order in the Etsy app (Etsy's API cannot attach files to an order).

The listing itself only carries an instructions PDF + a small watermarked preview. The 6 illustrations are kept
in the product's assets (custom__art-N.png) so every order can be rendered again with the buyer's name."""
import io
import re

from PIL import Image, ImageDraw

from .. import assets, images, mockups
from ..imgutil import color_to_alpha_background, font, jpeg_bytes, make_zips, png_bytes, thumb_b64, trim_alpha
from . import sublimation as SB

COUNT = 6
SIZE = SB.SIZE
LABEL_TR = f"Kişiye özel PNG (alıcının adıyla {COUNT} tasarım, sipariş gelince bot hazırlar)"
SPEC_FIELDS = f"""
  "set_name": "short set name, 2-4 words (e.g. 'Teacher Pencil Bow')",
  "kind": "who it is for, 1-2 words (e.g. 'teacher', 'family', 'nurse', 'grandma')",
  "sample_name": "a realistic example name shown on the photos (e.g. 'Mrs. Johnson', 'The Millers')",
  "designs": [ exactly {COUNT} objects {{"name": "short name", "tagline": "a short upbeat line printed under the name, 1-4 words, family friendly, no brand, song, movie or famous quote (e.g. 'Teach Love Inspire', 'Christmas 2026')", "prompt": "English prompt for ONE isolated illustration that fits the set (e.g. 'a pencil with a pink coquette bow and apple'), no text in the picture"}} ]
"""
NAME_OK = re.compile(r"[^A-Za-z0-9 .,'&!\-À-ɏ]")
LAYOUTS = ("name_top", "name_bottom")


def clean_name(text):
    t = NAME_OK.sub("", str(text or "")).strip()
    return re.sub(r"\s+", " ", t)[:32] or "Your Name"


def compose(art, name, tagline, ink, layout):
    """One finished 3600 px transparent design: the buyer's name in script + the art + a small bold tagline."""
    c = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    nm = SB._text_img(name, "script", SIZE * 0.92, 1000, ink, max_h=1100)
    tg = SB._text_img(tagline.upper(), "bold", SIZE * 0.80, 420, ink, max_h=520) if tagline else None
    a = art.copy()
    a.thumbnail((int(SIZE * 0.72), SIZE - nm.height - (tg.height if tg else 0) - 260), Image.LANCZOS)
    parts = [nm, a, tg] if layout == "name_top" else [tg, a, nm]
    parts = [p for p in parts if p is not None]
    gap = 50
    y = (SIZE - sum(p.height for p in parts) - gap * (len(parts) - 1)) // 2
    for p in parts:
        c.alpha_composite(p, ((SIZE - p.width) // 2, y))
        y += p.height + gap
    return c


def _style(p_or_spec, k):
    spec = p_or_spec.get("spec", p_or_spec)
    pal = spec.get("palette", [])
    d = (spec.get("designs") or [{}] * COUNT)
    tag = re.sub(r"\s+", " ", str((d[k] if k < len(d) else {}).get("tagline", "")).strip())[:30]
    return tag, SB._ink(pal, k), LAYOUTS[k % 2]


def _design(p_or_spec, art, name, k):
    """One finished design. A preset can ask for the richer festive look ("look": "festive"); products made
    before it (no "look" in their spec) keep the plain look their listing photos show."""
    spec = p_or_spec.get("spec", p_or_spec)
    tag, ink, layout = _style(spec, k)
    if spec.get("look") == "festive":
        from . import custom_festive
        return custom_festive.compose(art, name, tag, k)
    return compose(art, name, tag, ink, layout)


def render(p, name):
    """All designs of a published custom product with the buyer's name -> [(file name, png bytes)]."""
    name = clean_name(name)
    safe = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "name"
    out = []
    for k in range(p.get("custom_count", COUNT)):
        try:
            art = Image.open(io.BytesIO(assets.download(p["id"], f"custom__art-{k + 1}.png"))).convert("RGBA")
        except Exception as e:
            print(f"[custom] çizim {k + 1} indirilemedi: {e}")
            continue
        dsg = _design(p, art, name, k)
        out.append((f"{safe}-design-{k + 1}.png", png_bytes(dsg)))
        out.append((f"{safe}-design-{k + 1}-mug-wrap.png", png_bytes(SB.mug_wrap(dsg))))
    return out


def _instructions_pdf(title, n):
    page = Image.new("RGB", (2550, 3300), (252, 250, 246))
    d = ImageDraw.Draw(page)
    d.text((1275, 420), "Thank you for your order!", font=font("serif", 130), fill=(60, 50, 45), anchor="mm")
    lines = [title, "",
             "Your personalized designs are made by hand for you.",
             f"You will receive {n} PNG designs + mug wraps with your name",
             "within 24 hours (at the latest 3 days) here on Etsy:",
             "Purchases and reviews > this order > Download files.", "",
             "Please check the spelling you entered at checkout.",
             "If anything should change, just send us a message.", "",
             "Personal and small business use (up to 500 items).",
             "Please do not share or resell the files."]
    y = 700
    for ln in lines:
        d.text((1275, y), ln, font=font("sans", 62), fill=(70, 65, 60), anchor="mm")
        y += 110
    b = io.BytesIO()
    page.save(b, "PDF", resolution=300)
    return b.getvalue()


def _watermark(im):
    im = im.convert("RGB")
    im.thumbnail((900, 900))
    d = ImageDraw.Draw(im, "RGBA")
    f = font("sans_bold", 90)
    for y in range(80, im.height, 260):
        d.text((im.width / 2, y), "SAMPLE", font=f, fill=(120, 120, 120, 90), anchor="mm")
    return im


def build(spec, slug):
    palette = spec.get("palette", [])
    style = spec.get("style", "watercolor")
    sample = clean_name(spec.get("sample_name") or "Mrs. Johnson")
    arts = []
    for ds in spec.get("designs", [])[:COUNT]:
        im = images.try_generate(f"{ds['prompt']}, {style}, color palette {', '.join(palette)}, {SB.SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is None:
            continue
        a = trim_alpha(color_to_alpha_background(im))
        arts.append(a.resize((a.width * 3, a.height * 3), Image.LANCZOS))
    images.need(len(arts), COUNT, ratio=0.8)
    n = len(arts)
    dsgs = [_design(spec, a, sample, k) for k, a in enumerate(arts)]

    preview = mockups.grid(dsgs, f"{n} designs with YOUR name", palette, cols=3)
    files = [("HOW-TO-RECEIVE-YOUR-DESIGNS.pdf", _instructions_pdf(spec["title"], n)),
             ("preview-sample.jpg", jpeg_bytes(_watermark(preview), 80))]
    readme = (f"{spec['title']}\n\nThank you! This listing is personalized: your {n} designs with the name you entered "
              "are sent to you on Etsy within 24 hours (at the latest 3 days).\n")
    delivery = make_zips(slug, files, readme)

    set_name = spec.get("set_name", "Personalized Designs")
    kind = (spec.get("kind") or "custom").strip()
    tumbler_wrap = Image.new("RGB", (2790, 2460), (255, 255, 255))
    t = dsgs[0].copy()
    t.thumbnail((1250, 2200), Image.LANCZOS)
    tumbler_wrap.paste(t, (1395 - t.width // 2, (2460 - t.height) // 2), t)
    mock = [] if spec.get("look") == "festive" else [
        ("00-cover.jpg", SB.product_cover(dsgs, n, set_name, palette, title=f"CUSTOM {kind.upper()} NAME PNG")),
        ("01-all.jpg", mockups.grid(dsgs, f"{n} Designs, All With Your Name", palette, cols=3)),
        ("02-order.jpg", mockups.info_card("HOW TO ORDER", ["1. Type the name in the personalization box",
                                                            f"2. We write it into all {n} designs",
                                                            "3. Download your files within 24 hours"], palette, dsgs[1 % n])),
        ("03-shirts.jpg", SB.tee_mock(dsgs[2 % n], palette, "SHIRTS, TOTES & SWEATSHIRTS")),
        ("04-mug.jpg", SB.mug_mock(dsgs[3 % n], palette)),
        ("05-tumbler.jpg", mockups.tumbler_mockup(tumbler_wrap, palette, label="TUMBLERS & MORE")),
        ("06-transparent.jpg", mockups.grid(dsgs[:4], "Transparent Background PNG", palette, cols=2, checker=True)),
        ("07-what.jpg", mockups.info_card("WHAT YOU GET", [f"{n} PNG designs with your name, 3600 x 3600 px",
                                                           f"{n} ready 11 oz mug wraps", "Transparent background, 300 DPI",
                                                           "Sent within 24 hours"], palette, dsgs[4 % n])),
    ]
    if not mock:  # festive look: square photos in deep red and green, the same design shown with several names
        from . import custom_festive
        names = [clean_name(x) for x in spec.get("sample_names") or []] or [sample, "Noah", "Emma"]
        mock = custom_festive.photos(dsgs, arts, n, kind, lambda i, nm: _design(spec, arts[i % n], nm, i % n), names)
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "own_cover": True,
        "extra_assets": {f"custom__art-{k + 1}.png": png_bytes(a) for k, a in enumerate(arts)},
        "product_extra": {"custom_count": n},
        "listing": {"is_personalizable": True, "personalization_is_required": True,
                    "personalization_char_count_max": 40,
                    "personalization_instructions": spec.get("personalization_instructions")
                    or f"Name exactly as it should appear (e.g. {sample}). Your designs are sent within 24 hours."},
        "included": [f"{n} PNG designs personalized with your name (3600 x 3600 px, transparent, 300 DPI)",
                     f"{n} ready 11 oz mug wraps with your name", "Sent to you on Etsy within 24 hours"],
        "details": ["Made to order: enter the name in the personalization box at checkout",
                    "This is a digital file, nothing is shipped"],
        "usage": ["Sublimation: mugs, tumblers, totes, light shirts", "DTF and print on demand: upload the PNG as it is"],
        "license": "Personal and small business commercial use on up to 500 physical products. Do not share or resell the files.",
        "taxonomy": ["Clip Art & Image Files", "Digital Prints"],
        "taxonomy_fallback_id": 6844,
        "is_supply": False,
        "skip_attributes": ["room"],
        "count": n,
    }
