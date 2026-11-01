"""Scene illustration pack: full painted scenes delivered as high resolution JPG (not cut-out PNG clipart)."""
from PIL import Image

from .. import images, mockups
from ..imgutil import jpeg_bytes, make_zips, thumb_b64

COUNT = 12          # scenes per pack (each one is one image-model request)
GEN_W, GEN_H = 1344, 1024   # generated size; lower to 1024x768 if the daily quota runs out
OUT_LONG = 2400     # delivered long side in px

LABEL_TR = "Sahne illüstrasyon paketi (12 yüksek çözünürlüklü JPG)"
SPEC_FIELDS = """
  "bundle_name": "short collection name, 2-4 words",
  "elements": [ exactly 12 objects {"name": "short scene name", "prompt": "English prompt describing ONE complete illustrated scene with the main subject, setting and mood (e.g. 'Santa Claus sitting in a wooden rocking chair beside a reindeer and a pile of wrapped gifts in a snowy pine forest')"} ]
"""

STYLE = ("vintage painterly Christmas illustration, realistic detailed digital painting with soft brush texture, "
         "soft falling snow, warm muted palette of deep red, cream, gold and forest green, cinematic soft light")
SUFFIX = ("full scene, nicely composed, main subject clearly visible, no text, no letters, no watermark, no logo, "
          "no border, no frame")


def build(spec, slug):
    palette = spec.get("palette", [])
    scenes = []
    for e in spec["elements"][:COUNT]:
        raw = images.generate(f"{e['prompt']}, {STYLE}, {SUFFIX}", GEN_W, GEN_H).convert("RGB")
        s = OUT_LONG / max(raw.width, raw.height)
        big = raw.resize((int(raw.width * s), int(raw.height * s)), Image.LANCZOS)
        scenes.append((e["name"], big))
    files = []
    for i, (name, im) in enumerate(scenes, 1):
        safe = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:30] or "scene"
        files.append((f"{i:02d}-{safe}.jpg", jpeg_bytes(im, 92, dpi=300)))
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n{len(files)} high resolution JPG illustrations, 300 DPI.\n"
              "License: personal and small business commercial use (up to 500 physical products).\n"
              "You may NOT resell, share or redistribute the digital files themselves, or use them in other digital products.\n")
    delivery = make_zips(slug, files, readme)

    name = spec.get("bundle_name", "Illustration Bundle")
    ims = [im for _, im in scenes]
    pal = mockups.palette_colors(palette)
    wall = mockups._mix(pal["all"][0], (236, 231, 223), 0.72)
    n = len(ims)
    mock = [
        ("01-cover.jpg", mockups.cover(ims[:5], name, f"{n} JPG Illustrations  •  High Resolution", palette)),
        ("02-all.jpg", mockups.grid(ims, f"{n} Illustrations Included", palette, cols=4)),
        ("03-wall.jpg", mockups.wall_mockup(ims[0], wall)),
        ("04-info.jpg", mockups.info_card("WHAT YOU GET", [
            f"{n} separate JPG files",
            "High resolution, 300 DPI",
            "Great for cards, crafts, printables and digital projects",
            "Commercial use for small businesses (up to 500 items)",
        ], palette, ims[1 % n])),
        ("05-how.jpg", mockups.how_it_works(palette)),
    ]
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [f"{n} individual JPG illustrations", "High resolution", "Delivered as ZIP"],
        "details": ["About 2400 px on the long side", "300 DPI"],
        "usage": ["Cards, invitations, crafts, printables, scrapbooking and digital projects",
                  "Unzip the file on a computer before use"],
        "license": "Personal and small business commercial use for physical products (up to 500 items). Reselling or sharing the digital files is not allowed.",
        "taxonomy": ["Clip Art & Image Files", "Digital Prints"],
        "taxonomy_fallback_id": 6844,
        "is_supply": True,
    }
