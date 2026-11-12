"""Personalized nursery wall art ("look": "nursery"): a set of three posters for a child's room -
a character portrait, a poster with the child's NAME over a big initial letter, another character portrait.

  * the 6 portraits are original watercolour animals drawn once per product (AI, 6 images); they do not change
    with the name, so the buyer downloads all of them at once, in three print ratios
  * the name poster is drawn by code for every order (no AI): the buyer's name in brush lettering over the
    initial, in three colours and three print ratios
  * listing photos: real-looking rooms (AI photo of a room with an empty wall, 4 images) with the three framed
    posters hung by code, so the posters in the photo are exactly the files the buyer gets

Only original characters: no figures, uniforms, badges or names from films, shows, games or brands.
"""
import io
import math
import random
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .. import display_fonts, images, mockups
from ..imgutil import color_to_alpha_background, font, jpeg_bytes, make_zips, thumb_b64, trim_alpha

S = 2000
PAPER = (253, 252, 249)
INK = (26, 24, 28)
# print ratios: name -> (pixels, what it prints as)
RATIOS = {"3x4": ((3600, 4800), "6x8, 9x12, 12x16, 18x24 in"),
          "4x5": ((3600, 4500), "8x10, 16x20 in"),
          "ISO-A": ((3508, 4961), "A5, A4, A3, A2")}
MASTER = RATIOS["3x4"][0]
# name poster colours: label -> (light wash, letter fill, letter edge)
COLORS = {"blue": ((206, 228, 246), (190, 218, 242), (96, 152, 214)),
          "pink": ((250, 214, 222), (248, 204, 214), (226, 124, 150)),
          "sage": ((214, 230, 212), (202, 222, 200), (120, 158, 122))}
ROOMS = [  # (scene prompt, frame colour, wall area the three frames hang in: x0, y0, x1, y1 as fractions)
    ("bright nursery with a white wooden crib standing against a plain empty cream wall, soft daylight from the side",
     (250, 249, 246), (0.08, 0.10, 0.92, 0.50)),
    ("cozy child's bedroom with a white daybed with grey and blue cushions against a plain empty soft grey wall, "
     "wooden floor, a woven basket", (196, 164, 124), (0.10, 0.08, 0.90, 0.46)),
    ("minimal Scandinavian kids room with a low white dresser and wooden toys on it against a plain empty white wall, "
     "soft sunlight and gentle window shadows", (206, 174, 132), (0.08, 0.10, 0.92, 0.52)),
    ("light airy toddler bedroom with a small white bed with beige quilted bedding against a plain empty warm white "
     "wall, a wooden decoration", (214, 184, 146), (0.10, 0.08, 0.90, 0.48)),
]
ROOM_SUFFIX = ("interior photograph, straight front view of the wall, the upper half of the picture is only empty wall, "
               "no pictures, no frames, no posters, no shelves on the wall, no text, realistic, natural light")
ART_SUFFIX = ("head and shoulders portrait, front view, big friendly eyes, gentle smile, loose black ink outline with "
              "soft watercolor wash, one soft watercolor splash behind the head, a few small paint dots, centered, "
              "plain pure white background, hand painted children's book illustration, no text, no letters, no frame, "
              "no clothing logos, no badges")


def _fit(im, size, bg=PAPER):
    """The master artwork (3:4) on another print ratio: scaled to fit, paper colour around it."""
    out = Image.new("RGB", size, bg)
    c = ImageOps.contain(im, size, Image.LANCZOS)
    out.paste(c, ((size[0] - c.width) // 2, (size[1] - c.height) // 2))
    return out


def portrait(art):
    """One portrait poster (3600 x 4800): the painted animal large on clean paper."""
    W, H = MASTER
    pg = Image.new("RGB", MASTER, PAPER)
    a = trim_alpha(color_to_alpha_background(art.convert("RGB")))
    a = ImageOps.contain(a, (int(W * 0.86), int(H * 0.78)), Image.LANCZOS)
    pg.paste(a, ((W - a.width) // 2, (H - a.height) // 2), a)
    return pg


def _wash(size, colour, seed, spread=0.34):
    """A soft watercolour cloud: overlapping blurred blobs, uneven like real paint."""
    W, H = size
    q = 8
    rnd = random.Random(seed)
    m = Image.new("L", (W // q, H // q), 0)
    d = ImageDraw.Draw(m)
    cx, cy = W / q / 2, H / q / 2
    for _ in range(46):
        ang, rad = rnd.uniform(0, 6.283), rnd.uniform(0, 1) ** 0.6 * W / q * spread
        r = rnd.uniform(0.07, 0.19) * W / q
        x, y = cx + math.cos(ang) * rad, cy + math.sin(ang) * rad * 1.15
        d.ellipse((x - r, y - r, x + r, y + r), fill=rnd.randint(70, 150))
    m = m.filter(ImageFilter.GaussianBlur(W / q / 46))
    grain = np.asarray(Image.effect_noise((W // q, H // q), 26)).astype(np.float32) / 255
    a = np.clip(np.asarray(m).astype(np.float32) * (0.82 + 0.36 * grain), 0, 255).astype(np.uint8)
    layer = Image.new("RGBA", size, colour + (0,))
    layer.putalpha(Image.fromarray(a).resize(size, Image.BICUBIC))
    return layer


def _paw(d, cx, cy, r, colour, rot=0.0):
    """A paw print: one pad and four toes."""
    def at(dx, dy):
        c, s = math.cos(rot), math.sin(rot)
        return cx + (dx * c - dy * s) * r, cy + (dx * s + dy * c) * r
    x, y = at(0, 0.28)
    d.ellipse((x - 0.62 * r, y - 0.50 * r, x + 0.62 * r, y + 0.50 * r), fill=colour)
    for dx, dy, k in ((-0.72, -0.34, 0.27), (-0.26, -0.78, 0.29), (0.26, -0.78, 0.29), (0.72, -0.34, 0.27)):
        x, y = at(dx, dy)
        d.ellipse((x - k * r, y - k * r * 1.2, x + k * r, y + k * r * 1.2), fill=colour)


def name_poster(name, color="blue", seed=7):
    """The personalised poster (3600 x 4800): the name in brush lettering across a big soft initial letter."""
    W, H = MASTER
    wash, fill, edge = COLORS.get(color, COLORS["blue"])
    name = name.strip() or "Name"
    pg = Image.new("RGB", MASTER, PAPER).convert("RGBA")
    pg.alpha_composite(_wash(MASTER, wash, seed))
    # the initial: big rounded letter, light fill, a sketchy double edge
    ini = next((c for c in name if c.isalnum()), "A").upper()
    lf = font("sans_bold", int(H * 0.56))  # the shop's bold font, fattened with a stroke into a chunky soft letter
    while ImageDraw.Draw(pg).textlength(ini, font=lf) > W * 0.56:
        lf = font("sans_bold", lf.size - 40)
    layer = Image.new("RGBA", MASTER, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = W // 2, int(H * 0.50)
    fat = 84
    d.text((cx + 34, cy + 40), ini, font=lf, fill=edge + (255,), anchor="mm", stroke_width=fat + 22, stroke_fill=edge + (255,))
    d.text((cx, cy), ini, font=lf, fill=fill + (255,), anchor="mm", stroke_width=fat + 22, stroke_fill=edge + (255,))
    d.text((cx, cy), ini, font=lf, fill=fill + (255,), anchor="mm", stroke_width=fat, stroke_fill=fill + (255,))
    layer = layer.filter(ImageFilter.GaussianBlur(3))
    pg.alpha_composite(layer)
    d = ImageDraw.Draw(pg)
    rnd = random.Random(seed * 31 + len(name))
    # paw prints and paint dots around the letter
    for k, (fx, fy, r) in enumerate(((0.50, 0.10, 70), (0.84, 0.26, 110), (0.16, 0.76, 84), (0.24, 0.82, 64),
                                     (0.62, 0.90, 120))):
        col = INK if k in (0, 1) else edge if k % 2 else wash
        _paw(d, W * fx + rnd.randint(-40, 40), H * fy + rnd.randint(-40, 40), r, col, rnd.uniform(-0.5, 0.5))
    for _ in range(26):
        x, y, r = rnd.uniform(0.1, 0.9) * W, rnd.uniform(0.08, 0.92) * H, rnd.randint(8, 26)
        d.ellipse((x - r, y - r, x + r, y + r), fill=edge if rnd.random() < 0.6 else wash)
    # the name: black brush lettering, a little tilted, across the middle of the letter
    text = name.upper() if len(name) <= 9 else name
    nf = display_fonts.fit(d, text, "brush", W * 0.84, int(H * 0.19), 220)
    box = d.textbbox((0, 0), text, font=nf, anchor="lt")
    tw, th = box[2] - box[0] + 160, box[3] - box[1] + 200
    t = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(t).text((tw // 2, th // 2), text, font=nf, fill=INK + (255,), anchor="mm")
    t = t.rotate(3, resample=Image.BICUBIC, expand=True)
    pg.alpha_composite(t, ((W - t.width) // 2, int(H * 0.47) - t.height // 2))
    return pg.convert("RGB")


# ---------------------------------------------------------------- rooms
def _frame(poster, w, colour):
    """A framed poster of width w: thin frame, white mat line, soft glass light."""
    b = max(8, w // 34)
    h = round(w * MASTER[1] / MASTER[0])
    fr = Image.new("RGB", (w + 2 * b, h + 2 * b), colour)
    d = ImageDraw.Draw(fr)
    d.rectangle((0, 0, fr.width - 1, fr.height - 1), outline=tuple(max(0, c - 46) for c in colour), width=2)
    d.rectangle((b - 2, b - 2, b + w + 1, b + h + 1), outline=tuple(max(0, c - 60) for c in colour), width=2)
    fr.paste(poster.resize((w, h), Image.LANCZOS), (b, b))
    glass = Image.new("L", fr.size, 0)
    gd = ImageDraw.Draw(glass)
    gd.polygon([(fr.width * 0.55, 0), (fr.width * 0.80, 0), (fr.width * 0.42, fr.height), (fr.width * 0.17, fr.height)], fill=20)
    fr = Image.composite(Image.new("RGB", fr.size, (255, 255, 255)), fr, glass.filter(ImageFilter.GaussianBlur(w // 12)))
    return fr


def hang(room, posters, colour, area):
    """Three framed posters on the wall of a room photo (2000 x 2000), with soft shadows and the room's own light."""
    room = ImageOps.fit(room.convert("RGB"), (S, S), Image.LANCZOS)
    x0, y0, x1, y1 = (int(v * S) for v in area)
    gap = int((x1 - x0) * 0.045)
    w = min(((x1 - x0) - 2 * gap) // 3, int((y1 - y0) / (MASTER[1] / MASTER[0])))
    b = max(8, w // 34)
    fw, fh = w + 2 * b, round(w * MASTER[1] / MASTER[0]) + 2 * b
    left = (x0 + x1) // 2 - (3 * fw + 2 * gap) // 2
    top = (y0 + y1) // 2 - fh // 2
    out = room.convert("RGBA")
    # the wall's light over the frames (window shadows fall over pictures too): the blurred wall, as a factor
    wall = np.asarray(room.filter(ImageFilter.GaussianBlur(26)).convert("L")).astype(np.float32)
    for k, p in enumerate(posters[:3]):
        fx = left + k * (fw + gap)
        sh = Image.new("RGBA", (fw + 120, fh + 120), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((60 + 10, 60 + 16, 60 + fw + 10, 60 + fh + 16), fill=(40, 30, 20, 90))
        out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)), (fx - 60, top - 60))
        fr = np.asarray(_frame(p, w, colour)).astype(np.float32)
        light = wall[top:top + fh, fx:fx + fw]
        light = np.clip(light / max(1.0, float(np.median(light))), 0.80, 1.10)[..., None]
        out.paste(Image.fromarray(np.clip(fr * light, 0, 255).astype(np.uint8)), (fx, top))
    return out.convert("RGB")


def _plain_room(seed, colour=(236, 230, 222)):
    """Fallback when no room photo could be made: a painted wall with a floor line (still honest: a simple scene)."""
    im = Image.new("RGB", (S, S), colour)
    d = ImageDraw.Draw(im)
    d.rectangle((0, int(S * 0.78), S, S), fill=(214, 196, 172))
    d.rectangle((0, int(S * 0.765), S, int(S * 0.78)), fill=(250, 248, 244))
    return im.filter(ImageFilter.GaussianBlur(1))


# ---------------------------------------------------------------- listing cards
def _title(d, text, y, size=120, fill=(34, 44, 84)):
    f = display_fonts.fit(d, text, "serif", S - 240, size, 60)
    d.text((S // 2, y), text, font=f, fill=fill, anchor="mm")


def all_card(posters, labels, name_p, n):
    """"You receive all N portraits + your name poster"."""
    c = Image.new("RGB", (S, S), (252, 247, 240))
    c.paste(_wash((S, S), (250, 222, 206), 3, 0.5).convert("RGB"), (0, 0), _wash((S, S), (250, 222, 206), 3, 0.5))
    d = ImageDraw.Draw(c)
    _title(d, f"You Receive All {n} Portraits", 150)
    d.rounded_rectangle((S // 2 - 520, 250, S // 2 + 520, 350), 50, fill=(96, 152, 214))
    d.text((S // 2, 300), "+ YOUR CUSTOM NAME POSTER", font=font("sans_bold", 54), fill=(255, 255, 255), anchor="mm")
    items = posters[:n] + [name_p]
    cols = 4 if len(items) > 6 else 3
    rows = -(-len(items) // cols)
    w = min((S - 200 - (cols - 1) * 40) // cols, int((S - 520 - (rows - 1) * 40) / rows * 3 / 4))
    h = w * 4 // 3
    gx = (S - cols * w - (cols - 1) * 40) // 2
    for k, p in enumerate(items):
        r, cc = divmod(k, cols)
        last = len(items) - r * cols if r == rows - 1 else cols
        ox = gx + (cols - last) * (w + 40) // 2 if r == rows - 1 else gx
        x, y = ox + cc * (w + 40), 430 + r * (h + 40)
        d.rounded_rectangle((x - 8, y - 8, x + w + 8, y + h + 8), 18, fill=(255, 255, 255), outline=(232, 222, 210), width=3)
        c.paste(p.resize((w, h), Image.LANCZOS), (x, y))
    d.text((S // 2, S - 70), "Mix and match: hang any two with the name poster", font=font("sans_medium", 50),
           fill=(90, 80, 74), anchor="mm")
    return c


def names_card(make, names):
    """The same poster with three names and the three colours."""
    c = Image.new("RGB", (S, S), (246, 240, 232))
    d = ImageDraw.Draw(c)
    _title(d, "Any Name, Three Colors", 170)
    w = 560
    h = w * 4 // 3
    for k, (nm, col) in enumerate(zip(names, COLORS)):
        x = 100 + k * (w + 60)
        y = 420
        d.rounded_rectangle((x - 10, y - 10, x + w + 10, y + h + 10), 16, fill=(255, 255, 255), outline=(226, 216, 204), width=3)
        c.paste(make(nm, col).resize((w, h), Image.LANCZOS), (x, y))
        d.text((x + w // 2, y + h + 80), col.upper(), font=font("sans_bold", 48), fill=(90, 80, 74), anchor="mm")
    for k, ln in enumerate(("1. Type the name in the personalization box", "2. We make your name poster in all three colors",
                            "3. Download and print within 24 hours")):
        d.text((S // 2, 1440 + k * 120 + 110), ln, font=font("sans_medium", 58), fill=(60, 56, 70), anchor="mm")
    return c


def sizes_card(poster, n):
    c = Image.new("RGB", (S, S), (250, 246, 240))
    d = ImageDraw.Draw(c)
    _title(d, "Print In Any Size", 170)
    c.paste(poster.resize((660, 880), Image.LANCZOS), (150, 420))
    d.rectangle((150, 420, 810, 1300), outline=(206, 174, 132), width=14)
    y = 440
    for key, (px, prints) in RATIOS.items():
        d.text((930, y), key.replace("x", ":").replace("ISO-A", "A sizes"), font=font("sans_bold", 70), fill=(34, 44, 84))
        d.text((930, y + 96), prints, font=font("sans_medium", 56), fill=(70, 66, 76))
        d.text((930, y + 172), f"{px[0]} x {px[1]} px, 300 DPI", font=font("sans", 44), fill=(120, 112, 108))
        y += 300
    for k, ln in enumerate((f"{n} portraits + your name poster, JPG files", "Print at home, at a print shop or online",
                            "Frames are not included: digital files only")):
        d.ellipse((190, 1470 + k * 120, 226, 1506 + k * 120), fill=(96, 152, 214))
        d.text((260, 1488 + k * 120), ln, font=font("sans_medium", 56), fill=(60, 56, 70), anchor="lm")
    return c


# ---------------------------------------------------------------- order + product
def render(p, name, clean):
    """An order: the name poster in three colours and three print ratios -> [(file name, jpeg bytes)]."""
    name = clean(name)
    if len(name) > 16:
        raise ValueError("isim en fazla 16 karakter olabilir (poster düzeni)")
    safe = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "name"
    out = []
    for col in COLORS:
        master = name_poster(name, col, seed=len(p.get("id", "")) + 7)
        for key, (size, _) in RATIOS.items():
            out.append((f"{safe}-name-poster-{col}-{key}.jpg", jpeg_bytes(_fit(master, size), 92, dpi=300)))
    return out


def _instructions_pdf(title, n):
    pg = Image.new("RGB", (2550, 3300), (252, 250, 246))
    d = ImageDraw.Draw(pg)
    d.text((1275, 420), "Thank you for your order!", font=font("serif", 130), fill=(60, 50, 45), anchor="mm")
    lines = [title, "", f"In this download: all {n} portrait posters, ready to print,",
             "each in three print ratios (3:4, 4:5 and A sizes).", "",
             "Your personalized NAME poster is made for you and sent", "within 24 hours (at the latest 3 days) here on Etsy:",
             "Purchases and reviews > this order > Download files.", "It comes in blue, pink and sage.", "",
             "Please check the spelling you entered at checkout.", "If anything should change, just send us a message.", "",
             "Personal use only. Please do not share or resell the files."]
    y = 700
    for ln in lines:
        d.text((1275, y), ln, font=font("sans", 60), fill=(70, 65, 60), anchor="mm")
        y += 108
    b = io.BytesIO()
    pg.save(b, "PDF", resolution=300)
    return b.getvalue()


def build(spec, slug, clean, count):
    names = [clean(x) for x in spec.get("sample_names") or []] or ["Ethan", "Mia", "Noah"]
    sample = clean(spec.get("sample_name") or names[0])
    designs = spec.get("designs", [])[:count]
    arts, labels = [], []
    for ds in designs:
        im = images.try_generate(f"{ds['prompt']}, {ART_SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is None:
            continue
        arts.append(im.resize((3072, 3072), Image.LANCZOS))
        labels.append(re.sub(r"[^a-z0-9]+", "-", str(ds.get("tagline") or ds.get("name") or "portrait").lower()).strip("-"))
    images.need(len(arts), count, ratio=0.8)
    n = len(arts)
    posters = [portrait(a) for a in arts]
    seed = sum(map(ord, slug))
    cols = list(COLORS)
    make = lambda nm, col="blue": name_poster(nm, col, seed=len(slug) + 7)
    name_p = make(sample, cols[seed % 3])

    # delivery: every portrait in three ratios (instant download); the name poster follows per order
    files = [("HOW-TO-RECEIVE-YOUR-NAME-POSTER.pdf", _instructions_pdf(spec["title"], n))]
    for k, (p, lab) in enumerate(zip(posters, labels), 1):
        for key, (size, _) in RATIOS.items():
            files.append((f"{key}/{k:02d}-{lab}-{key}.jpg", jpeg_bytes(_fit(p, size), 90, dpi=300)))
    readme = (f"{spec['title']}\n\nThank you! All {n} portrait posters are in this download, in three print ratios.\n"
              "Your personalized name poster (blue, pink and sage) is sent to you on Etsy within 24 hours "
              "(at the latest 3 days).\n")
    delivery = make_zips(slug, files, readme)

    # rooms: an AI photo of a room with an empty wall, the three frames are hung by code (4 images)
    rnd = random.Random(seed)
    rooms = ROOMS[seed % len(ROOMS):] + ROOMS[:seed % len(ROOMS)]
    shots = []
    for k, (scene, frame, area) in enumerate(rooms):
        photo = images.try_generate(f"{scene}, {ROOM_SUFFIX}", 1024, 1024)
        if photo is None:
            photo = _plain_room(seed + k)
        a, b = rnd.sample(range(n), 2) if n > 1 else (0, 0)
        if k == 0:
            a, b = 0, 1 % n  # the cover shows the first two portraits
        mid = name_p if k == 0 else make(names[k % len(names)], cols[(seed + k) % 3])
        shots.append(hang(photo, [posters[a], mid, posters[b]], frame, area))
    mock = [("00-cover.jpg", shots[0]),
            ("01-all.jpg", all_card(posters, labels, name_p, n)),
            ("02-room.jpg", shots[1]),
            ("03-order.jpg", names_card(make, (names + ["Ethan", "Mia", "Noah"])[:3])),
            ("04-room.jpg", shots[2]),
            ("05-sizes.jpg", sizes_card(posters[2 % n], n)),
            ("06-room.jpg", shots[3]),
            ("07-detail.jpg", ImageOps.fit(posters[3 % n], (S, S), Image.LANCZOS, centering=(0.5, 0.45))),
            ("08-detail.jpg", ImageOps.fit(name_p, (S, S), Image.LANCZOS, centering=(0.5, 0.48)))]
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "own_cover": True,
        "extra_assets": {},
        "product_extra": {"custom_count": n},
        "listing": {"is_personalizable": True, "personalization_is_required": True,
                    "personalization_char_count_max": 40,
                    "personalization_instructions": spec.get("personalization_instructions")
                    or f"Type the name exactly as it should appear (e.g. {sample}), max 16 characters. "
                       "Your name poster is sent within 24 hours."},
        "included": [f"{n} portrait posters, ready to download right away (JPG, 300 DPI)",
                     "1 name poster personalized with your name, in blue, pink and sage, sent within 24 hours",
                     "Every poster in three print ratios: 3:4 (3600 x 4800 px), 4:5 (3600 x 4500 px) and A sizes (3508 x 4961 px)"],
        "details": ["Made to order: enter the name in the personalization box at checkout",
                    "Prints up to 18 x 24 in / A2",
                    "Digital files only: frames and prints are not included, nothing is shipped"],
        "usage": ["Print at home, at a print shop or with an online print service",
                  "Nursery, kids room, playroom, baby shower and birthday gift"],
        "license": "Personal use only. Do not share or resell the files.",
        "taxonomy": ["Digital Prints", "Prints", "Art & Collectibles"],
        "taxonomy_fallback_id": 2078,
        "is_supply": False,
        "count": n,
    }
