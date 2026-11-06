"""Clipart PNG bundle: 30 transparent PNG elements about ONE subject (30 AI images)
+ printable sticker sheets (PDF) + one preview sheet. Honest size: about 2400 px on the long side, 300 DPI."""
import io
import re

import numpy as np
from PIL import Image, ImageDraw

from .. import ephemera as E
from .. import images, mockups
from ..bundle_cover import bundle_cover
from ..imgutil import color_to_alpha_background, fit_text, font, jpeg_bytes, make_zips, png_bytes, thumb_b64, trim_alpha

COUNT = 30
LABEL_TR = f"Clipart paketi ({COUNT} şeffaf PNG + sticker sayfaları)"
SPEC_FIELDS = f"""
  "bundle_name": "short collection name, 2-4 words, about the subject (e.g. 'Vintage Gingerbread')",
  "subject": "the bundle's main subject in 1-3 words (e.g. 'gingerbread')",
  "elements": [ exactly {COUNT} objects {{"name": "short element name", "prompt": "English prompt for ONE single isolated object or character about the subject, each element clearly different (e.g. 'a gingerbread house with white icing and candy canes'). One object only, no text, no letters."}} ]
"""

SUFFIX = ("single isolated clipart illustration, one object only, centered with generous empty space around it, "
          "pure plain white background, no shadow, no ground, no text, no letters, no numbers, no border, no frame, "
          "no watermark")
LONG_SIDE = 2400


def _clean(im):
    """Cut the white background, trim, and check the result is a real transparent element."""
    cut = trim_alpha(color_to_alpha_background(im))
    a = np.asarray(cut.split()[-1])
    if a.size == 0:
        return None
    corners = [a[0, 0], a[0, -1], a[-1, 0], a[-1, -1]]
    filled = (a > 128).mean()
    if max(corners) > 40 or filled < 0.08 or filled > 0.97:  # background left over, or almost nothing / everything kept
        return None
    s = min(LONG_SIDE / max(cut.size), 2.4)
    return cut.resize((int(cut.width * s), int(cut.height * s)), Image.LANCZOS)


def _safe(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "element").lower()).strip("-")[:40] or "element"


def preview_sheet(els, title, palette, cols=8):
    """One JPG with every element, so buyers can find a piece fast."""
    w = 3000
    rows = -(-len(els) // cols)
    cell = (w - 120) // cols
    h = 260 + rows * cell + 80
    sheet = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    pal = mockups.palette_colors(palette)
    tf = fit_text(d, title, "sans_bold", w - 200, 110, 40)
    d.text(((w - d.textlength(title, font=tf)) / 2, 70), title, font=tf, fill=pal["text"])
    for i, (name, im) in enumerate(els):
        t = im.copy()
        t.thumbnail((int(cell * 0.82), int(cell * 0.74)), Image.LANCZOS)
        x = 60 + (i % cols) * cell
        y = 260 + (i // cols) * cell
        sheet.paste(t, (x + (cell - t.width) // 2, y + int(cell * 0.04) + (int(cell * 0.74) - t.height) // 2), t)
        lab = f"{i + 1:02d}"
        f = font("sans", 30)
        d.text((x + (cell - d.textlength(lab, font=f)) / 2, y + int(cell * 0.82)), lab, font=f, fill=(150, 150, 150))
    return sheet


def _on_dark(els, palette):
    """Proof of clean edges: a few elements on a dark background."""
    pal = mockups.palette_colors(palette)
    canvas = Image.new("RGBA", (mockups.W, mockups.H), (34, 32, 38, 255))
    d = ImageDraw.Draw(canvas)
    t = "CLEAN EDGES ON DARK BACKGROUNDS"
    f = fit_text(d, t, "sans_bold", mockups.W - 300, 80, 40)
    d.text(((mockups.W - d.textlength(t, font=f)) / 2, 90), t, font=f, fill=(255, 255, 255, 255))
    picks = els[:6]
    cw = (mockups.W - 200) // 3
    ch = (mockups.H - 340) // 2
    for i, im in enumerate(picks):
        x = 100 + (i % 3) * cw
        y = 260 + (i // 3) * ch
        s = im.copy()
        s.thumbnail((int(cw * 0.8), int(ch * 0.8)), Image.LANCZOS)
        canvas.alpha_composite(s, (x + (cw - s.width) // 2, y + (ch - s.height) // 2))
    return canvas.convert("RGB")


def build(spec, slug):
    style = spec.get("style", "watercolor")
    palette = spec.get("palette", [])
    els = []
    for e in spec["elements"][:COUNT]:
        im = images.try_generate(f"{e['prompt']}, {style}, color palette {', '.join(palette)}, {SUFFIX}", 1024, 1024)
        if im is None and images.quota_exhausted():
            break
        big = _clean(im) if im is not None else None
        if big is not None:
            els.append((e.get("name", "element"), big))
    images.need(len(els), COUNT, ratio=0.75)  # at least 30 good elements, else no product today

    n = len(els)
    name = spec.get("bundle_name", "Clipart Bundle")
    files = [(f"PNG/{i:02d}-{_safe(nm)}.png", png_bytes(im)) for i, (nm, im) in enumerate(els, 1)]
    stickers = [E.sticker(im.resize((im.width // 3, im.height // 3), Image.LANCZOS)) for _, im in els]
    sheets = [E.sticker_sheet(stickers[k:k + 12], seed=k) for k in range(0, n, 12)]
    b = io.BytesIO()
    sheets[0].save(b, "PDF", save_all=True, append_images=sheets[1:], resolution=300)
    files.append(("Sticker-Sheets-US-Letter.pdf", b.getvalue()))
    prev = preview_sheet(els, f"{name} - {n} PNG", palette)
    files.append(("Preview-Sheet.jpg", jpeg_bytes(prev, 85)))
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n"
              f"- {n} PNG clipart files, transparent background, about {LONG_SIDE} px on the long side, 300 DPI\n"
              f"- {len(sheets)} printable sticker sheets (PDF, US Letter)\n"
              "- 1 preview sheet with all designs (numbered)\n\n"
              "HOW TO OPEN: download on a computer if you can, then right-click the ZIP and choose 'Extract all'. "
              "On a phone use the Files app (iPhone) or Files by Google (Android).\n\n"
              "LICENSE: personal use and small business commercial use on up to 500 physical products. "
              "You may not resell, share or redistribute the digital files, or use them in other clipart, "
              "template or digital products.\n\nQuestions? Message us on Etsy, we reply within a day.\n")
    delivery = make_zips(slug, files, readme)

    thumbs = [im for _, im in els]
    half = (n + 1) // 2
    mock = [
        ("01-bundle.jpg", bundle_cover(thumbs, n, "Clipart PNG", name, palette,
                                       sticker=("TRANSPARENT", "PNG", "300 DPI"),
                                       features=["TRANSPARENT PNG", "COMMERCIAL USE", "STICKER SHEETS", "INSTANT DOWNLOAD"])),
        ("02-all-1.jpg", mockups.grid(thumbs[:half], f"{n} Clipart Elements Included (1/2)", palette, cols=5)),
        ("03-all-2.jpg", mockups.grid(thumbs[half:], f"{n} Clipart Elements Included (2/2)", palette, cols=5)),
        ("04-transparent.jpg", mockups.grid(thumbs[:6], "Transparent Background PNG", palette, cols=3, checker=True)),
        ("05-dark.jpg", _on_dark(thumbs[6:12] or thumbs, palette)),
        ("06-stickers.jpg", mockups.info_card("PRINTABLE STICKER SHEETS", [f"{len(sheets)} US Letter pages", "Print on sticker paper and cut",
                                                                            "Great for planners and journals"], palette, sheets[0])),
        ("07-closeup.jpg", mockups.info_card("HIGH QUALITY DETAIL", [f"About {LONG_SIDE} px, 300 DPI", "Clean transparent edges",
                                                                       "Cards, invitations, stickers, mugs"], palette, thumbs[0])),
        ("08-what.jpg", mockups.info_card("WHAT YOU GET", [f"{n} separate PNG files", f"{len(sheets)} sticker sheet pages (PDF)",
                                                           "Numbered preview sheet", "Instant download (ZIP)"], palette, prev)),
        ("09-license.jpg", mockups.info_card("COMMERCIAL USE", ["Personal and small business use", "Up to 500 physical products",
                                                                "No reselling of the digital files"], palette, thumbs[1])),
        ("10-how.jpg", mockups.how_it_works(palette)),
    ]
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [f"{n} individual PNG clipart files with transparent background",
                     f"{len(sheets)} printable sticker sheet pages (PDF, US Letter)",
                     "Numbered preview sheet with every design", "Delivered as ZIP"],
        "details": [f"About {LONG_SIDE} px on the long side, 300 DPI (about 8 inches printed)", "RGB, clean edges"],
        "usage": ["Cards, invitations, gift tags, stickers, scrapbooking, junk journals and digital planners",
                  "Sublimation on mugs and tumblers", "Unzip the file on a computer before use"],
        "license": "Personal and small business commercial use on up to 500 physical products. Reselling or sharing the digital files is not allowed.",
        "taxonomy": ["Clip Art & Image Files", "Digital Prints"],
        "taxonomy_fallback_id": 6844,
        "is_supply": True,
        "skip_attributes": ["room"],
        "count": n,
    }
