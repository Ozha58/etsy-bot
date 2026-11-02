"""Scene illustration pack: 15 full painted scenes, square 4096x4096 JPG, 300 DPI (not cut-out PNG clipart)."""
from PIL import Image, ImageFilter

from .. import images, mockups, mockups_scenes
from ..imgutil import jpeg_bytes, make_zips, thumb_b64

COUNT = 15                  # scenes per pack (each one is one image-model request)
GEN_W, GEN_H = 1024, 1024   # generated size (square)
OUT_SIZE = 4096             # delivered size in px (square)
PREVIEW = 2400              # size kept in memory for the listing images

LABEL_TR = "Sahne illüstrasyon paketi (15 JPG, 4096x4096)"
SPEC_FIELDS = """
  "bundle_name": "short collection name, 2-4 words",
  "elements": [ exactly 15 objects {"name": "short scene name", "prompt": "English prompt describing ONE complete illustrated scene with the main subject, setting and mood (e.g. 'Santa Claus sitting in a wooden rocking chair beside a reindeer and a pile of wrapped gifts in a snowy pine forest')"} ]
"""

STYLE = ("vintage painterly Christmas illustration, realistic detailed digital painting with soft brush texture, "
         "soft falling snow, warm muted palette of deep red, cream, gold and forest green, cinematic soft light")
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
              "License: personal and small business commercial use (up to 500 physical products).\n"
              "You may NOT resell, share or redistribute the digital files themselves, or use them in other digital products.\n")
    delivery = make_zips(slug, files, readme)

    name = spec.get("bundle_name", "Illustration Bundle")
    ims = previews
    n = len(ims)
    pal = mockups.palette_colors(palette)
    wall = mockups._mix(pal["all"][0], (236, 231, 223), 0.72)
    mock = [
        # 1. GÖRSEL: En önemli kapak! Gerçekçi bir oda/duvar tasarımı.
        ("01-realistic-room.jpg", mockups.wall_mockup(ims[0], wall)),
        # 2. GÖRSEL: Koleksiyonun tamamını gösteren mozaik
        ("02-mosaic.jpg", mockups_scenes.mosaic(ims, name, n, palette)),
        # 3. GÖRSEL: İkinci bir gerçekçi oda açısı (farklı bir resimle)
        ("03-room-angle2.jpg", mockups.wall_mockup(ims[1], wall)),
        # 4. GÖRSEL: Stilize edilmiş (eski usul) kapak görseli
        ("04-cover.jpg", mockups_scenes.single_cover(ims, name, n, palette)),
        # 5. GÖRSEL: Yakın çekim (Kaliteyi ve çizgileri göstermek için)
        ("05-closeup.jpg", mockups.wall_mockup(ims[2], wall)),
        # 6. GÖRSEL: "Neler Dahil" bilgi kartı
        ("06-info.jpg", mockups.info_card("WHAT YOU GET", [
            f"{n} separate JPG files",
            "4096 x 4096 px, 300 DPI, print ready",
            "Soft background, no transparency",
            "Instant ZIP download",
        ], palette, ims[3 % n])),
        # 7. GÖRSEL: Nasıl çalışır?
        ("07-how.jpg", mockups.how_it_works(palette)),
        # 8. GÖRSEL: Son bir oda mockup'ı
        ("08-room-angle3.jpg", mockups.wall_mockup(ims[4 % n], wall)),
    ]
