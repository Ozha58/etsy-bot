"""Scene illustration pack: 15 full painted scenes, square 4096x4096 JPG, 300 DPI."""
from PIL import Image, ImageFilter

from .. import images, mockups, mockups_scenes
from ..imgutil import jpeg_bytes, make_zips, thumb_b64

COUNT = 15
GEN_W, GEN_H = 1024, 1024
OUT_SIZE = 4096
PREVIEW = 2400

LABEL_TR = "Sahne illüstrasyon paketi (15 JPG, 4096x4096)"
SPEC_FIELDS = """
  "bundle_name": "short collection name, 2-4 words",
  "elements": [ exactly 15 objects {"name": "short scene name", "prompt": "English prompt describing ONE complete illustrated scene with the main subject, setting and mood"} ]
"""

STYLE = ("vintage painterly illustration, detailed digital painting with soft brush texture, "
         "warm muted palette, cinematic soft light")
SUFFIX = ("full scene, nicely composed, main subject clearly visible, square composition, no text, no letters, "
          "no watermark, no logo, no border, no frame")


def build(spec, slug):
    palette = spec.get("palette", [])
    files, previews, names = [], [], []
    for i, e in enumerate(spec["elements"][:COUNT], 1):
        raw = images.generate(f"{e['prompt']}, {STYLE}, {SUFFIX}", GEN_W, GEN_H).convert("RGB")
        big = raw.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
        safe = "".join(c if c.isalnum() else "-" for c in e["name"].lower()).strip("-")[:30] or "scene"
        files.append((f"{i:02d}-{safe}.jpg", jpeg_bytes(big, 88, dpi=300)))
        previews.append(big.resize((PREVIEW, PREVIEW), Image.LANCZOS))
        names.append(e["name"])
        del big, raw
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n{len(files)} high resolution JPG illustrations, 4096 x 4096 px, 300 DPI.\n"
              "License: personal and small business commercial use (up to 500 physical products).\n")
    delivery = make_zips(slug, files, readme)

    name = spec.get("bundle_name", "Illustration Bundle")
    ims = previews
    n = len(ims)
    pal = mockups.palette_colors(palette)
    wall = mockups._mix(pal["all"][0], (236, 231, 223), 0.72)
    
    # GÜVENLİ 8 GÖRSEL LİSTESİ (Hata vermemesi için orijinal yapıya sadık kalındı)
    mock = [
        # 1. GÖRSEL: Grafik Kapak
        ("01-cover.jpg", mockups_scenes.single_cover(ims, name, n, palette)),
        # 2. GÖRSEL: Tüm sahnelerin mozaik görünümü
        ("02-mosaic.jpg", mockups_scenes.mosaic(ims, name, n, palette)),
        # 3. GÖRSEL: Gerçekçi duvar mockup'ı (Sadece 1 kere çağırıyoruz ki çökmesin)
        ("03-wall.jpg", mockups.wall_mockup(ims[0], wall)),
        # 4. GÖRSEL: Bilgi Kartı
        ("04-info.jpg", mockups.info_card("WHAT YOU GET", [
            f"{n} separate JPG files",
            "4096 x 4096 px, 300 DPI, print ready",
            "Soft background, no transparency",
            "Instant ZIP download",
        ], palette, ims[1 % n])),
        # 5. GÖRSEL: Nasıl Çalışır?
        ("05-how.jpg", mockups.how_it_works(palette)),
        # 6, 7, 8. GÖRSELLER: Ekstra detay önizlemeleri
        ("06-detail1.jpg", mockups.info_card("PREVIEW", ["High resolution detail"], palette, ims[2 % n])),
        ("07-detail2.jpg", mockups.info_card("PREVIEW", ["Beautiful painterly style"], palette, ims[3 % n])),
        ("08-detail3.jpg", mockups.info_card("PREVIEW", ["Perfect for cards & crafts"], palette, ims[4 % n])),
    ]
    
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [f"{n} individual JPG illustrations", "4096 x 4096 px, 300 DPI", "Delivered as ZIP"],
        "details": ["Square 4096 x 4096 px", "300 DPI, print ready"],
        "usage": ["Cards, invitations, crafts, printables, scrapbooking and digital projects",
                  "Unzip the file on a computer before use"],
        "license": "Personal and small business commercial use for physical products (up to 500 items). Reselling or sharing the digital files is not allowed.",
        "taxonomy": ["Clip Art & Image Files", "Digital Prints"],
        "taxonomy_fallback_id": 6844,
        "is_supply": True,
    }
