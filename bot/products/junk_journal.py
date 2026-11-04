"""Printable junk journal kit: 6 vintage scenes + 8 isolated objects (14 AI images)
-> pages, journaling cards, tags, postage stamps, stickers, cutouts, digital papers, sticker sheets (60+ pieces)."""
import io

from PIL import Image

from .. import ephemera as E
from .. import images, mockups, mockups_jj
from ..imgutil import color_to_alpha_background, hex2rgb, jpeg_bytes, make_zips, png_bytes, thumb_b64, trim_alpha

LABEL_TR = "Junk journal kiti (60+ parça: sayfa, kart, etiket, pul, sticker, kâğıt)"
SPEC_FIELDS = """
  "kit_name": "short kit name, 2-4 words, about the subject (e.g. 'Honey Bee Meadow')",
  "subject": "the kit's main subject in 1-3 words (e.g. 'honey bees')",
  "scenes": [ exactly 6 objects {"name": "short name", "prompt": "English prompt for ONE complete vintage illustration about the subject (a scene, a landscape, a still life or a botanical plate). Never any text, letters, words or numbers in the picture."} ],
  "objects": [ exactly 8 objects {"name": "short name", "prompt": "English prompt for ONE single isolated object about the subject (e.g. 'a vintage honey jar with a wooden dipper'). One object only, no text."} ]
"""

SCENE_SUFFIX = ("antique vintage book illustration, aged print, detailed, full composition, "
                "no text, no letters, no words, no numbers, no watermark, no border, no frame")
OBJECT_SUFFIX = ("single isolated vintage illustration of one object, centered with empty space around it, "
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
    for s in spec["scenes"][:6]:
        im = images.try_generate(f"{s['prompt']}, {style}, {SCENE_SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is not None:
            scenes.append(im.convert("RGB"))
    images.need(len(scenes), 6, ratio=0.67)
    for o in spec["objects"][:8]:
        im = images.try_generate(f"{o['prompt']}, {style}, {OBJECT_SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is not None:
            objs.append(trim_alpha(color_to_alpha_background(im)))
    images.need(len(objs), 8, ratio=0.75)

    col = lambda i: palette[i % len(palette)]
    obj_scenes = [_obj_scene(o, col(i), 30 + i) for i, o in enumerate(objs)]
    pages = [E.page(sc, seed=i + 1, layout=i, accent=E.SEPIA) for i, sc in enumerate(scenes)]
    pages.append(_plate(objs[:4], seed=40))
    if len(objs) >= 8:
        pages.append(_plate(objs[4:8], seed=41))
    cards = [E.card(sc, seed=i + 1) for i, sc in enumerate(scenes)] + [E.card(s, seed=60 + i) for i, s in enumerate(obj_scenes[:2])]
    tags = ([E.tag(sc, seed=i + 1) for i, sc in enumerate(scenes[:4])] +
            [E.tag(o, seed=70 + i, is_object=True) for i, o in enumerate(objs[:4])])
    stamps = ([E.stamp(sc, seed=i + 1, color=col(i)) for i, sc in enumerate(scenes)] +
              [E.stamp(o, seed=80 + i, color=col(i + 1), is_object=True) for i, o in enumerate(objs[:6])])
    stickers = [E.sticker(o) for o in objs]
    papers = [E.tossed_paper(objs, 3000, seed=1, scale=0.12),
              E.tossed_paper(objs[::-1], 3000, seed=2, tint=tuple(int(c * 0.35 + p * 0.65) for c, p in zip(col(1), E.PAPER)), scale=0.09),
              E.tossed_paper(objs[:4], 3000, seed=3, tint=tuple(int(c * 0.3 + p * 0.7) for c, p in zip(col(0), E.PAPER)), scale=0.16),
              E.stripe_paper(col(0), 3000, seed=4, kind="stripes"),
              E.stripe_paper(col(1), 3000, seed=5, kind="dots"),
              E.stripe_paper(col(2), 3000, seed=6, kind="gingham")]
    half = (len(stickers) + 1) // 2
    sheets = [E.sticker_sheet(stickers[:half]), E.sticker_sheet(stickers[half:])] if len(stickers) > 4 else [E.sticker_sheet(stickers)]

    files = []
    files += [(f"01-pages/page-{i:02d}.jpg", jpeg_bytes(p, 88)) for i, p in enumerate(pages, 1)]
    files += [(f"02-cards/card-{i:02d}.jpg", jpeg_bytes(c, 90)) for i, c in enumerate(cards, 1)]
    files += [(f"03-tags/tag-{i:02d}.png", png_bytes(t)) for i, t in enumerate(tags, 1)]
    files += [(f"04-stamps/stamp-{i:02d}.png", png_bytes(s)) for i, s in enumerate(stamps, 1)]
    files += [(f"05-stickers/sticker-{i:02d}.png", png_bytes(s)) for i, s in enumerate(stickers, 1)]
    files += [(f"06-cutouts/cutout-{i:02d}.png", png_bytes(o)) for i, o in enumerate(objs, 1)]
    files += [(f"07-papers/paper-{i:02d}.jpg", jpeg_bytes(p, 84)) for i, p in enumerate(papers, 1)]
    b = io.BytesIO()
    sheets[0].save(b, "PDF", save_all=True, append_images=sheets[1:], resolution=300)
    files.append(("08-sticker-sheets/printable-sticker-sheets-US-Letter.pdf", b.getvalue()))
    collage = [E.sticker_sheet(stamps), E.sticker_sheet(tags)]
    b = io.BytesIO()
    collage[0].save(b, "PDF", save_all=True, append_images=collage[1:], resolution=300)
    files.append(("09-collage-sheets/printable-collage-sheets-US-Letter.pdf", b.getvalue()))

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
    delivery = make_zips(slug, files, readme)

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
        "taxonomy": ["Scrapbooking Embellishments", "Digital Prints", "Clip Art & Image Files"],
        "taxonomy_fallback_id": 2078,
        "is_supply": True,
        "count": total,
    }
