import math

from PIL import Image, ImageDraw

from .. import images, mockups
from ..bundle_cover import bundle_cover
from ..imgutil import color_to_alpha_background, fit_text, jpeg_bytes, make_zips, png_bytes, thumb_b64, trim_alpha

LABEL_TR = "Clipart paketi (15 şeffaf PNG)"
SPEC_FIELDS = """
  "bundle_name": "short collection name, 2-4 words",
  "elements": [ exactly 15 objects {"name": "short element name", "prompt": "English prompt describing ONE single isolated object/character (e.g. 'a cozy pumpkin with a knitted scarf')"} ]
"""

SUFFIX = ("single isolated clipart illustration, one object only, centered with empty space around it, "
          "pure plain white background, no shadow, no ground, no text, no letters, no border, no frame")


def build(spec, slug):
    style = spec.get("style", "watercolor")
    palette = spec.get("palette", [])
    els = []
    for e in spec["elements"][:15]:
        raw = images.generate(f"{e['prompt']}, {style}, color palette {', '.join(palette)}, {SUFFIX}", 1024, 1024)
        cut = trim_alpha(color_to_alpha_background(raw))
        s = min(2400 / cut.width, 2400 / cut.height, 2.4)
        big = cut.resize((int(cut.width * s), int(cut.height * s)), Image.LANCZOS)
        els.append((e["name"], big))
    files = []
    for i, (name, im) in enumerate(els, 1):
        safe = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:30] or "element"
        files.append((f"{i:02d}-{safe}.png", png_bytes(im)))
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n{len(files)} high resolution PNG files with transparent background, 300 DPI.\n"
              "License: personal and small business commercial use (up to 500 physical products).\n"
              "You may NOT resell, share or redistribute the digital files themselves, or use them in other digital clipart products.\n")
    delivery = make_zips(slug, files, readme)

    name = spec.get("bundle_name", "Clipart Bundle")
    thumbs = [im for _, im in els]
    
    mock = []
    
    # 1. GÖRSEL: GERÇEKÇİ MASA TASARIMI (Lifestyle Mockup)
    desk_prompt = ("Top-down view of a cozy wooden desk, scattered colored paper, scissors, a cup of coffee, "
                   "soft natural sunlight casting beautiful shadows. Photorealistic, highly detailed, 8k resolution.")
    try:
        desk_bg = images.generate(desk_prompt, 1920, 1440).convert("RGBA")
        w, h = desk_bg.size
        # Masanın üzerine 3 adet klipartı çıkartma gibi yerleştirelim
        for i in range(3):
            clip = thumbs[i].copy()
            clip.thumbnail((350, 350), Image.LANCZOS)
            # Rastgele bir konum (merkeze yakın)
            x = int(w/2 - 400 + (i * 350))
            y = int(h/2 - 150 + (i % 2 * 200))
            # Çıkartma gibi durması için beyaz bir çerçeve ekleyelim
            sticker_bg = Image.new("RGBA", (clip.width + 40, clip.height + 40), (255, 255, 255, 255))
            sticker_bg.paste(clip, (20, 20), clip)
            desk_bg.paste(sticker_bg, (x, y), sticker_bg)
        mock.append(("01-lifestyle.jpg", desk_bg.convert("RGB")))
    except Exception as e:
        print(f"[clipart] Masa görseli üretilemedi: {e}")

    # 2. GÖRSEL: Grafik Kapak (Çelenk/Daire şeklinde)
    mock.append(("02-cover.jpg", _scatter(thumbs, name, f"{len(els)} PNG Clipart  •  Transparent Background", palette)))
    
    # 3. GÖRSEL: Tüm öğelerin grid görünümü
    mock.append(("03-all.jpg", mockups.grid(thumbs, f"{len(els)} Clipart Elements Included", palette, cols=5)))
    
    # 4. GÖRSEL: Şeffaflık göstergesi (Damalı arka plan)
    mock.append(("04-transparent.jpg", mockups.grid(thumbs[:6], "Transparent Background PNG", palette, cols=3, checker=True)))
    
    # 5. GÖRSEL: Yakın çekim / Kalite göstergesi
    mock.append(("05-closeup.jpg", mockups.info_card("HIGH RESOLUTION DETAIL", [
        "300 DPI",
        "Crisp transparent edges",
        "Perfect for print on demand"
    ], palette, thumbs[0])))
    
    # 6. GÖRSEL: Bilgi Kartı
    mock.append(("06-info.jpg", mockups.info_card("WHAT YOU GET", [
        f"{len(els)} separate PNG files",
        "Transparent background, 300 DPI",
        "Great for cards, invitations, stickers, scrapbooking and crafts",
        "Commercial use for small businesses (up to 500 items)",
    ], palette, thumbs[1])))
    
    # 7. GÖRSEL: Başka bir öğenin yakın çekimi
    mock.append(("07-preview.jpg", mockups.info_card("DESIGN PREVIEW", ["Perfect for sublimation"], palette, thumbs[2])))

    # 8. GÖRSEL: Nasıl çalışır?
    mock.append(("08-how.jpg", mockups.how_it_works(palette)))

    # İLK GÖRSEL: Etsy aramasında dikkat çeken "bundle" kapağı (gerçek dosya sayısıyla)
    mock.insert(0, ("00-bundle.jpg", bundle_cover(
        thumbs, len(els), "Clipart PNG", name, palette,
        sticker=("TRANSPARENT", "PNG", "300 DPI"),
        features=["TRANSPARENT PNG", "300 DPI", "COMMERCIAL USE", "INSTANT DOWNLOAD"])))

    return {
        "delivery": delivery,
        "mockups": [(n, jpeg_bytes(im, 88, dpi=72)) for n, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [f"{len(els)} individual PNG clipart files", "Transparent background", "Delivered as ZIP"],
        "details": ["High resolution, about 2000-2400 px on the long side", "300 DPI"],
        "usage": ["Cards, invitations, party printables, stickers, scrapbooking, sublimation and digital planners",
                  "Unzip the file on a computer before use"],
        "license": "Personal and small business commercial use for physical products (up to 500 items). Reselling or sharing the digital files is not allowed.",
        "taxonomy": ["Clip Art & Image Files", "Digital Prints"],
        "taxonomy_fallback_id": 6844,
        "is_supply": True,
    }


def _scatter(els, title, subtitle, palette):
    """Elements arranged around a central title (like a wreath)."""
    pal = mockups.palette_colors(palette)
    canvas = mockups._bg(pal)
    W, H = mockups.W, mockups.H
    n = len(els)
    cx, cy = W / 2, H / 2
    rx, ry = W * 0.38, H * 0.34
    for i, im in enumerate(els):
        ang = 2 * math.pi * i / n - math.pi / 2
        t = im.copy()
        t.thumbnail((360, 360), Image.LANCZOS)
        x = cx + rx * math.cos(ang) - t.width / 2
        y = cy + ry * math.sin(ang) - t.height / 2
        canvas.alpha_composite(t.convert("RGBA"), (int(x), int(y)))
    d = ImageDraw.Draw(canvas)
    tf = fit_text(d, title.upper(), "sans_bold", W * 0.5, 110, 40)
    tw = d.textlength(title.upper(), font=tf)
    d.text((cx - tw / 2, cy - 120), title.upper(), font=tf, fill=pal["text"] + (255,))
    sf = fit_text(d, subtitle, "serif_italic", W * 0.48, 52, 26)
    sw = d.textlength(subtitle, font=sf)
    d.text((cx - sw / 2, cy + 40), subtitle, font=sf, fill=pal["text"] + (255,))
    return canvas.convert("RGB")
