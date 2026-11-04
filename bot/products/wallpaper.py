"""Phone wallpaper pack: 10 vertical painted scenes, iPhone/Android and iPad sizes."""
from .. import images, mockups, mockups_wallpaper
from ..imgutil import crop_ratio, jpeg_bytes, make_zips, thumb_b64, upscale

COUNT = 10  # wallpapers per pack (each one is one image-model request)
GEN_W, GEN_H = 1280, 1920

LABEL_TR = "Telefon duvar kağıdı paketi (10 adet, iPhone/Android/iPad)"
SPEC_FIELDS = """
  "bundle_name": "short collection name, 2-4 words",
  "elements": [ exactly 10 objects {"name": "short wallpaper name", "prompt": "English prompt describing ONE vertical phone wallpaper scene with a clear main subject in the center (e.g. 'Santa Claus with his reindeer and sleigh on a snowy hill under a starry sky')"} ]
"""

STYLE = "vintage painterly illustration, soft brush texture, warm muted palette, cozy cinematic light"  # used when the plan has no style
LAYOUT = ("vertical composition for a phone wallpaper, main subject centered, "
          "calm uncluttered area at the top for the clock")
SUFFIX = ("full scene, nicely composed, no text, no letters, no watermark, no logo, no border, no frame, no phone, no device")

# (tag, width/height, (px width, px height), description)
SIZES = [
    ("iPhone-Android", 1290 / 2796, (1290, 2796), "iPhone and Android phones (1290 x 2796 px, 19.5:9)"),
    ("iPad-Tablet", 3 / 4, (2048, 2732), "iPad and tablets (2048 x 2732 px, 3:4)"),
]


def build(spec, slug):
    palette = spec.get("palette", [])
    arts, names = [], []
    wanted = spec["elements"][:COUNT]
    for e in wanted:
        im = images.try_generate(f"{e['prompt']}, {spec.get('style') or STYLE}, {LAYOUT}, {SUFFIX}", GEN_W, GEN_H)
        if im is None:
            if images.quota_exhausted():
                break
            continue
        arts.append(im.convert("RGB"))
        names.append(e["name"])
    images.need(len(arts), len(wanted))
    n = len(arts)
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n{n} phone wallpapers in 2 sizes, one ZIP per device:\n"
              + "\n".join(f"  - {s[3]}" for s in SIZES)
              + "\n\nHow to use: unzip on your computer or phone, save an image to Photos, then set it as wallpaper.\n"
                "For personal use only. Please do not share, resell or redistribute the files.\n")
    delivery = []
    for tag, ratio, (pw, ph), _ in SIZES:
        files = []
        for i, art in enumerate(arts, 1):
            safe = "".join(c if c.isalnum() else "-" for c in names[i - 1].lower()).strip("-")[:30] or "wallpaper"
            img = upscale(crop_ratio(art, ratio), pw, ph)
            files.append((f"{i:02d}-{safe}-{tag}.jpg", jpeg_bytes(img, 90)))
        delivery += make_zips(f"{slug}-{tag}", files, readme)

    name = spec.get("bundle_name", "Phone Wallpapers")
    pal = mockups.palette_colors(palette)
    mock = [
        ("01-cover.jpg", mockups_wallpaper.cover(arts, name, n, palette)),
        ("02-all.jpg", mockups_wallpaper.mosaic(arts, name, n, palette)),
        ("03-info.jpg", mockups.info_card("WHAT YOU GET", [
            f"{n} phone wallpapers",
            "iPhone, Android and iPad sizes",
            "High resolution JPG, 2 ZIP files",
            "Instant download",
        ], palette, arts[1 % n])),
        ("04-how.jpg", mockups.how_it_works(palette)),
    ]
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [f"{n} phone wallpapers", "ZIP 1: iPhone and Android size (1290 x 2796 px)", "ZIP 2: iPad and tablet size (2048 x 2732 px)"],
        "details": [s[3] for s in SIZES],
        "usage": ["Unzip, save the image to your phone or tablet photos, then set it as wallpaper",
                  "Phone or tablet frames shown in the photos are not included"],
        "license": "For personal use only. Please do not share, resell or redistribute the files.",
        "taxonomy": ["Digital Prints"],
        "taxonomy_fallback_id": 2078,
        "is_supply": False,
    }
