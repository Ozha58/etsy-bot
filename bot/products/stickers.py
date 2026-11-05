"""Digital sticker pack for one specific need (e.g. migraine & headache): word labels in many colours,
built-in sets for known topics (migraine: 0-10 pain scale + trigger icons), washi, sticky notes, date circles and
8 AI illustrations. Delivered as transparent PNGs, a sticker book PDF (to import into note-taking apps) and
printable sticker sheets."""
import io
import random

from PIL import Image

from .. import ephemera as E
from .. import images, mockups, planner_pdf, planner_stickers
from ..bundle_cover import bundle_cover
from ..imgutil import color_to_alpha_background, hex2rgb, jpeg_bytes, make_zips, png_bytes, thumb_b64, trim_alpha

LABEL_TR = "Dijital sticker paketi (konuya özel etiketler, ikonlar, PNG + PDF)"
SPEC_FIELDS = """
  "pack_name": "short pack name, 2-4 words (e.g. 'Migraine Care')",
  "subject": "the need the stickers are for, 1-3 words (e.g. 'migraine', 'nurse shift')",
  "topic": "migraine if the pack is about migraine or headaches, else other",
  "words": [ exactly 30 short sticker words, 1-3 words each, that this person writes in a planner every week (e.g. 'Took meds', 'Rest day') ],
  "themed": [ exactly 8 objects {"name": "short name", "prompt": "English prompt for ONE cute isolated sticker illustration that fits the subject (e.g. 'a cup of chamomile tea with steam'), no text"} ]
"""
SUFFIX = ("cute sticker illustration, one object, centered, soft colors, clean outline, pure plain white background, "
          "no shadow, no text, no letters")


def build(spec, slug):
    palette = [hex2rgb(c) for c in spec.get("palette", [])][:6] or [(140, 122, 168), (184, 160, 184), (120, 144, 160)]
    topic = "migraine" if "migraine" in (spec.get("topic", "") + spec.get("subject", "")).lower() or \
        "headache" in spec.get("subject", "").lower() else None
    words = [w.strip()[:22] for w in spec.get("words", []) if isinstance(w, str) and w.strip()][:30]
    if topic:
        planner_stickers.EDITION_WORDS[topic] = list(dict.fromkeys(planner_stickers.EDITION_WORDS[topic] + words))
    else:
        topic = "custom"
        planner_stickers.EDITION_WORDS["custom"] = words
    themed = []
    for t in spec.get("themed", [])[:8]:
        im = images.try_generate(f"{t['prompt']}, {spec.get('style', '')}, {SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        if im is not None:
            themed.append(E.sticker(trim_alpha(color_to_alpha_background(im))))
    images.need(len(themed), 8, ratio=0.5)

    cols = palette + [tuple(int(v * 0.8) for v in c) for c in palette]
    allst = planner_stickers.make_all(cols[:8], themed, per_word=8, edition=topic)
    keep = ("01-themed", f"08-{topic}", "09-pain", "10-trigger", "02-washi", "03-sticky", "05-dates", "07-icons")
    st = [(n, im) for n, im in allst if n.startswith(keep)]
    n = len(st)
    files = [(f"PNG/{name}", png_bytes(im)) for name, im in st]

    # sticker book: pages of stickers to import into a note-taking app (one PDF, landscape pages)
    book, rnd = [], random.Random(3)
    for k in range(0, n, 24):
        page = Image.new("RGB", (2400, 1800), (252, 250, 247))
        for i, (_, im) in enumerate(st[k:k + 24]):
            s = im.copy()
            s.thumbnail((330, 210), Image.LANCZOS)
            x, y = 90 + (i % 6) * 380, 90 + (i // 6) * 420
            page.paste(s, (x + (330 - s.width) // 2, y + (300 - s.height) // 2), s)
        book.append(page)
    b = io.BytesIO()
    book[0].save(b, "PDF", save_all=True, append_images=book[1:], resolution=200)
    files.append(("Sticker-Book-for-note-apps.pdf", b.getvalue()))
    small = [im.resize((max(1, im.width // 2), max(1, im.height // 2)), Image.LANCZOS) for _, im in st if not _.startswith("02-washi")]
    sheets = [E.sticker_sheet(small[k:k + 20], seed=k) for k in range(0, min(len(small), 120), 20)]
    b = io.BytesIO()
    sheets[0].save(b, "PDF", save_all=True, append_images=sheets[1:], resolution=300)
    files.append(("Printable-Sticker-Sheets-US-Letter.pdf", b.getvalue()))
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n"
              f"- {n} transparent PNG stickers (folders by type)\n"
              f"- Sticker book PDF ({len(book)} pages) to import into your note-taking app's sticker library\n"
              f"- {len(sheets)} printable sticker sheets (US Letter)\n\n"
              "Digital planners: import the PNG files (or the sticker book) as stickers or images, then drag them onto your pages.\n"
              "Paper planners: print the sheets on sticker paper and cut.\n\n"
              "Personal use. Please do not share or resell the files.\n")
    delivery = make_zips(slug, files, readme)

    name = spec.get("pack_name", "Planner Stickers")
    hexpal = ["#%02x%02x%02x" % c for c in palette]
    labels = [im for nm, im in st if nm.startswith(f"08-{topic}")]
    special = ([im for nm, im in st if nm.startswith("09-pain")] + [im for nm, im in st if nm.startswith("10-trigger")][:10] +
               [im for nm, im in st if nm.startswith("01-themed")])
    # a planner page dressed with the stickers ("how it looks in use")
    pal3 = (palette * 3)[:3]
    pl = planner_pdf.Planner(name, pal3, Image.new("RGB", (1200, 900), (240, 236, 230)), [], "sun", False,
                             "migraine" if topic == "migraine" else "life", "soft")
    data = pl.build()
    page = planner_pdf.render_pages(data, [pl.order.index("m0w0d0")], 1400)[0]
    from .planner import collage_pages
    in_use = collage_pages([page], st, "migraine" if topic == "migraine" else "life", palette)[0]
    mock = [
        ("01-bundle.jpg", bundle_cover(labels[::3][:10] + special[:14] + [in_use], n, "DIGITAL STICKERS", name, hexpal,
                                       bundle_word=spec.get("subject", "PLANNER").upper()[:22], ribbon="PNG + PDF",
                                       sticker=("PRINT", "OR", "DIGITAL"),
                                       features=["TRANSPARENT PNG", "STICKER BOOK", "PRINTABLE"])),
        ("02-in-use.jpg", mockups.info_card("IN YOUR PLANNER", ["Drag and drop onto any page", "Works in any note-taking app",
                                                                 "Or print on sticker paper"], hexpal, in_use)),
        ("03-labels.jpg", mockups.grid(labels[::2][:20], f"{len(labels)} Word Stickers", hexpal, cols=4)),
        ("04-special.jpg", mockups.grid(special[:20], "Scales, Icons & Illustrations", hexpal, cols=5)),
        ("05-book.jpg", mockups.info_card("STICKER BOOK INCLUDED", [f"{len(book)} pages, import in one step",
                                                                     "Organized by type"], hexpal, book[0])),
        ("06-sheets.jpg", mockups.info_card("PRINTABLE SHEETS", [f"{len(sheets)} US Letter pages", "Print and cut"], hexpal, sheets[0])),
        ("07-how.jpg", mockups.how_it_works(hexpal)),
    ]
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [f"{n} transparent PNG stickers", f"Sticker book PDF ({len(book)} pages) for note-taking apps",
                     f"{len(sheets)} printable sticker sheets (US Letter)", "Delivered as ZIP"],
        "details": ["Works with any note-taking app that imports images or stickers", "Also printable on sticker paper"] +
                   (["Tracking stickers only, not medical advice"] if topic == "migraine" else []),
        "usage": ["Digital planners: import the PNGs or the sticker book", "Paper planners: print and cut"],
        "license": "Personal use only. Please do not share or resell the files.",
        "taxonomy": ["Planners & Stickers", "Stickers", "Clip Art & Image Files"],
        "taxonomy_fallback_id": 6844,
        "is_supply": False,
        "skip_attributes": ["room"],
        "count": n,
        "cover_items": [in_use] + labels[::4][:4] + special[:6],
        "cover_kicker": f"{spec.get('subject', '')} stickers".strip(),
        "cover_features": ["Pain scale & icons" if topic == "migraine" else "Word labels & icons", "Transparent PNG",
                           "Sticker book PDF", "Printable sheets"],
    }
