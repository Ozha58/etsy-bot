"""Printable junk journal kit: 10 vintage scenes + 12 isolated objects (22 AI images)
-> pages, journaling cards, tags, postage stamps, stickers, cutouts, digital papers, sticker sheets (110+ pieces)."""
import io

from PIL import Image

from .. import ephemera as E
from .. import images, mockups, mockups_jj
from ..bundle_cover import bundle_cover
from ..imgutil import color_to_alpha_background, hex2rgb, jpeg_bytes, make_zips, png_bytes, thumb_b64, trim_alpha

N_SCENES, N_OBJECTS = 10, 12  # 22 AI images -> about 115 printable pieces

LABEL_TR = "Junk journal kiti (110+ parça: sayfa, kart, etiket, pul, sticker, kâğıt)"
SPEC_FIELDS = """
  "kit_name": "short kit name, 2-4 words, about the subject (e.g. 'Honey Bee Meadow')",
  "subject": "the kit's main subject in 1-3 words (e.g. 'honey bees')",
  "scenes": [ exactly 10 objects {"name": "short name", "prompt": "English prompt for ONE complete vintage illustration about the subject (a scene, a landscape, a still life or a botanical plate). Never any text, letters, words or numbers in the picture."} ],
  "objects": [ exactly 12 objects {"name": "short name", "prompt": "English prompt for ONE single isolated object about the subject (e.g. 'a vintage honey jar with a wooden dipper'). One object only, no text."} ]
"""

SCENE_SUFFIX = ("highly detailed realistic illustration, natural colors, full composition, "
                "no text, no letters, no words, no numbers, no watermark, no border, no frame")
OBJECT_SUFFIX = ("single isolated highly detailed realistic illustration of one object, true-to-life textures and colors, "
                 "centered with empty space around it, "
                 "pure plain white background, no shadow, no ground, no text, no letters, no border, no frame")


def _obj_scene(obj, color, seed):
    """An isolated object on tinted aged paper, usable like a scene."""
    bg = E.tinted(color, 1024, 1024, seed).convert("RGBA")
    o = obj.copy()
    o.thumbnail((760, 760), Image.LANCZOS)
    bg.alpha_composite(o, ((1024 - o.width) // 2, (1024 - o.height) // 2))
    return bg.convert("RGB")


def _plate(objs, seed):
    """Botanical-plate style page with four objects."""
    w, h = 2550, 3300
    page = E.aged_paper(w, h, seed=seed).convert("RGBA")
    from PIL import ImageDraw
    d = ImageDraw.Draw(page)
    m = int(w * 0.06)
    d.rectangle((m, m, w - m, h - m), outline=E.SEPIA + (150,), width=6)
    d.rectangle((m + 22, m + 22, w - m - 22, h - m - 22), outline=E.SEPIA + (110,), width=3)
    cw, ch = (w - 2 * m) // 2, (h - 2 * m) // 2
    for i, o in enumerate(objs[:4]):
        o = o.copy()
        o.thumbnail((int(cw * 0.72), int(ch * 0.72)), Image.LANCZOS)
        cx = m + (i % 2) * cw + cw // 2
        cy = m + (i // 2) * ch + ch // 2
        E.shadow_paste(page, o, (cx - o.width // 2, cy - o.height // 2), opacity=50)
        d.line((cx - cw * 0.25, cy + ch * 0.4, cx + cw * 0.25, cy + ch * 0.4), fill=E.SEPIA + (130,), width=3)
    return page.convert("RGB")


def build(spec, slug):
    palette = [hex2rgb(c) for c in spec.get("palette", [])] or [(170, 60, 50), (70, 100, 70), (190, 150, 80)]
    style = spec.get("style", "")
    scenes, objs = [], []
    for s in spec["scenes"][:N_SCENES]:
        im = images.try_generate(f"{s['prompt']}, {style}, {SCENE_SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is not None:
            scenes.append(im.convert("RGB"))
    images.need(len(scenes), min(N_SCENES, len(spec["scenes"])), ratio=0.6)
    for o in spec["objects"][:N_OBJECTS]:
        im = images.try_generate(f"{o['prompt']}, {style}, {OBJECT_SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is not None:
            objs.append(trim_alpha(color_to_alpha_background(im)))
    images.need(len(objs), min(N_OBJECTS, len(spec["objects"])), ratio=0.6)

    col = lambda i: palette[i % len(palette)]
    tint = lambda c, k: tuple(int(a * k + p * (1 - k)) for a, p in zip(c, E.PAPER))
    obj_scenes = [_obj_scene(o, col(i), 30 + i) for i, o in enumerate(objs)]
    # every scene and every object becomes a page, a card, a tag and a stamp (honest count, no duplicates)
    pages = [E.page(sc, seed=i + 1, layout=i, accent=E.SEPIA) for i, sc in enumerate(scenes)]
    pages += [_plate(objs[k:k + 4], seed=40 + k) for k in range(0, len(objs) - 3, 4)]
    cards = [E.card(sc, seed=i + 1) for i, sc in enumerate(scenes)] + [E.card(s, seed=60 + i) for i, s in enumerate(obj_scenes)]
    tags = ([E.tag(sc, seed=i + 1) for i, sc in enumerate(scenes)] +
            [E.tag(o, seed=70 + i, is_object=True) for i, o in enumerate(objs)])
    stamps = ([E.stamp(sc, seed=i + 1, color=col(i)) for i, sc in enumerate(scenes)] +
              [E.stamp(o, seed=80 + i, color=col(i + 1), is_object=True) for i, o in enumerate(objs)])
    stickers = [E.sticker(o) for o in objs]
    papers = [E.tossed_paper(objs, 3000, seed=1, scale=0.12),
              E.tossed_paper(objs[::-1], 3000, seed=2, tint=tint(col(1), 0.35), scale=0.09),
              E.tossed_paper(objs[:4], 3000, seed=3, tint=tint(col(0), 0.3), scale=0.16),
              E.tossed_paper(objs[4:] or objs, 3000, seed=4, tint=tint(col(2), 0.3), scale=0.14)]
    papers += [E.stripe_paper(col(i), 3000, seed=5 + i * 3 + j, kind=kind)
               for i in range(3) for j, kind in enumerate(("stripes", "dots", "gingham"))]
    sheets = [E.sticker_sheet(stickers[k:k + 6]) for k in range(0, len(stickers), 6)]

    collage = [E.sticker_sheet(stamps[k:k + 9]) for k in range(0, len(stamps), 9)] + \
              [E.sticker_sheet(tags[k:k + 9]) for k in range(0, len(tags), 9)]

    def _pdf(ims, q):
        b = io.BytesIO()
        ims[0].save(b, "PDF", save_all=True, append_images=ims[1:], resolution=300, quality=q)
        return b.getvalue()

    def _png(im, scale):
        if scale < 1:
            im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
        return png_bytes(im)

    def _files(q, scale):
        f = []
        f += [(f"01-pages/page-{i:02d}.jpg", jpeg_bytes(p, q)) for i, p in enumerate(pages, 1)]
        f += [(f"02-cards/card-{i:02d}.jpg", jpeg_bytes(c, q)) for i, c in enumerate(cards, 1)]
        f += [(f"03-tags/tag-{i:02d}.png", _png(t, scale)) for i, t in enumerate(tags, 1)]
        f += [(f"04-stamps/stamp-{i:02d}.png", _png(s, scale)) for i, s in enumerate(stamps, 1)]
        f += [(f"05-stickers/sticker-{i:02d}.png", _png(s, scale)) for i, s in enumerate(stickers, 1)]
        f += [(f"06-cutouts/cutout-{i:02d}.png", _png(o, scale)) for i, o in enumerate(objs, 1)]
        f += [(f"07-papers/paper-{i:02d}.jpg", jpeg_bytes(p, q - 4)) for i, p in enumerate(papers, 1)]
        f.append(("08-sticker-sheets/printable-sticker-sheets-US-Letter.pdf", _pdf(sheets, q)))
        f.append(("09-collage-sheets/printable-collage-sheets-US-Letter.pdf", _pdf(collage, q)))
        return f

    counts = {"pages": len(pages), "cards": len(cards), "tags": len(tags), "stamps": len(stamps),
              "stickers": len(stickers), "cutouts": len(objs), "papers": len(papers), "sheets": len(sheets) + len(collage)}
    total = sum(v for k, v in counts.items() if k != "sheets")
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n"
              f"{total} printable junk journal pieces, 300 DPI:\n"
              f"- {counts['pages']} journal pages (US Letter 8.5x11 in, JPG)\n"
              f"- {counts['cards']} journaling cards (3x4 in, JPG)\n"
              f"- {counts['tags']} tags (2.5x5 in, PNG with transparent background)\n"
              f"- {counts['stamps']} postage stamps (PNG with transparent background)\n"
              f"- {counts['stickers']} stickers + {counts['cutouts']} cutouts (PNG with transparent background)\n"
              f"- {counts['papers']} digital papers (10x10 in, JPG)\n"
              f"- printable sticker sheets and collage sheets (PDF, US Letter)\n\n"
              "Print at home or at a print shop. Personal use and small handmade journals you sell (up to 200).\n"
              "Please do not share or resell the digital files.\n")
    # Etsy allows 5 files of 20 MB: lower the JPEG quality / PNG size step by step until the kit fits
    for q, scale in ((88, 1.0), (82, 1.0), (76, 0.85), (70, 0.75), (64, 0.65)):
        try:
            delivery = make_zips(slug, _files(q, scale), readme)
            break
        except ValueError:
            continue
    else:
        raise RuntimeError("Junk journal dosyaları 5 ZIP'e sığmadı")

    name = spec.get("kit_name", "Junk Journal Kit")
    parts = {"pages": pages, "cards": cards, "tags": tags, "stamps": stamps, "stickers": stickers,
             "cutouts": objs, "papers": papers, "sheets": sheets + collage}
    mock = [
        ("01-cover.jpg", mockups_jj.cover(parts, name, total)),
        ("02-inside.jpg", mockups_jj.inside(parts, counts)),
        ("03-pages.jpg", mockups_jj.showcase(pages[:4], "JOURNAL PAGES", f"{counts['pages']} pages • US Letter • 300 DPI", seed=6)),
        ("04-ephemera.jpg", mockups_jj.showcase(cards[:3] + tags[:3] + stamps[:2], "CARDS • TAGS • STAMPS",
                                                 f"{counts['cards']} cards • {counts['tags']} tags • {counts['stamps']} stamps", seed=7)),
        ("05-stickers.jpg", mockups_jj.showcase(stickers[:8], "STICKERS & CUTOUTS", "transparent PNG + printable sticker sheets", seed=8)),
        ("06-papers.jpg", mockups_jj.showcase(papers[:6], "DIGITAL PAPERS", f"{counts['papers']} papers • 10x10 in", seed=9, cols=3)),
        ("07-how.jpg", mockups.how_it_works(spec.get("palette", []))),
    ]
    mock.insert(0, ("00-bundle.jpg", bundle_cover(
        pages + cards + papers, total, "Journal Pieces", name, spec.get("palette", []),
        bundle_word="JUNK JOURNAL", ribbon="PRINTABLE",
        sticker=("PAGES", "TAGS", "STICKERS"),
        features=["PRINTABLE", "US LETTER", "300 DPI", "INSTANT DOWNLOAD"])))
    return {
        "delivery": delivery,
        "mockups": [(n, jpeg_bytes(im, 88, dpi=72)) for n, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [
            f"{counts['pages']} journal pages (US Letter, JPG)",
            f"{counts['cards']} journaling cards (3x4 in)",
            f"{counts['tags']} tags and {counts['stamps']} postage stamps (transparent PNG)",
            f"{counts['stickers']} stickers + {counts['cutouts']} cutouts (transparent PNG)",
            f"{counts['papers']} digital papers (10x10 in)",
            "Printable sticker sheets and collage sheets (PDF)",
        ],
        "details": [f"{total}+ pieces, 300 DPI", "Aged vintage paper look, no text on the artwork"],
        "usage": ["Print at home on matte paper or sticker paper", "Cut out, collage and build your own journal"],
        "license": "Personal use and small handmade journals you sell (up to 200). Please do not share or resell the digital files.",
        "taxonomy": ["Paper > Scrapbooking Ephemera", "Clip Art & Image Files"],
        "taxonomy_fallback_id": 6844,
        "is_supply": True,
        "skip_attributes": ["room"],
        "count": total,
    }
