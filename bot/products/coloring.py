import io
from PIL import Image

from .. import images, mockups, mockups_coloring
from ..bundle_cover import bundle_cover
from ..imgutil import jpeg_bytes, thumb_b64

N_PAGES = 20  # one AI image per page
LABEL_TR = "Boyama sayfaları (20 sayfa, PDF)"
SPEC_FIELDS = """
  "audience": "adults or kids",
  "book_name": "short collection name, 2-5 words",
  "pages": [ exactly 20 objects {"name": "...", "prompt": "detailed English prompt describing ONE coloring page scene/subject and its composition. Line art only."} ]
"""

LETTER = (2550, 3300)  # 8.5x11 in @300dpi
A4 = (2480, 3508)


def _suffix(audience):
    if str(audience).lower().startswith("kid"):
        detail = "simple bold thick outlines, large open areas, cute friendly style suitable for children"
    else:
        detail = "intricate detailed outlines for adults, many small areas to color"
    return (f"Black and white coloring book page, {detail}, clean crisp black line art on pure white background, "
            "no shading, no gray tones, no color, no fill, no text, no letters, no border, no frame, full page composition.")


def _page(lineart: Image.Image, size):
    pw, ph = size
    margin = int(pw * 0.06)
    box_w, box_h = pw - 2 * margin, ph - 2 * margin
    g = lineart.convert("L")
    s = min(box_w / g.width, box_h / g.height)
    g = g.resize((int(g.width * s), int(g.height * s)), Image.LANCZOS)
    bw = g.point(lambda v: 255 if v > 165 else 0, mode="L")
    page = Image.new("L", (pw, ph), 255)
    page.paste(bw, ((pw - bw.width) // 2, (ph - bw.height) // 2))
    return page.convert("1")


def _pdf(pages):
    b = io.BytesIO()
    pages[0].save(b, "PDF", save_all=True, append_images=pages[1:], resolution=300)
    return b.getvalue()


def build(spec, slug):
    audience = spec.get("audience", "adults")
    raws = []
    for p in spec["pages"][:N_PAGES]:
        r = images.try_generate(f"{p['prompt']}. {_suffix(audience)}", 1488, 1920)
        if r is None:
            if images.quota_exhausted():
                break
            continue
        raws.append(r)
    images.need(len(raws), len(spec["pages"][:N_PAGES]), ratio=0.75)
    letter = [_page(r, LETTER) for r in raws]
    a4 = [_page(r, A4) for r in raws]
    delivery = [
        (f"{slug}-US-Letter.pdf", _pdf(letter)),
        (f"{slug}-A4.pdf", _pdf(a4)),
    ]
    palette = spec.get("palette", [])
    previews = [p.convert("L").convert("RGB") for p in letter]
    name = spec.get("book_name", "Coloring Pages")
    colored = mockups.colored_preview(letter[0], palette, seed=len(slug))
    
    mock = []
    
    # 1. GÖRSEL: GERÇEKÇİ MASA TASARIMI (Realistic Hero Shot)
    # Yapay zekadan boş bir ahşap masa ve kalemler çizmesini istiyoruz
    desk_prompt = ("Top-down view of a cozy wooden desk, scattered colored pencils and markers, a cup of coffee, "
                   "soft natural sunlight casting beautiful shadows. Photorealistic, highly detailed, 8k resolution. "
                   "Empty white space in the exact center for a piece of paper.")
    try:
        desk_bg = images.generate(desk_prompt, 1920, 1920)
        # Çizdiğimiz boyama sayfasını (renklendirilmiş halini) masanın ortasına yerleştiriyoruz
        p_w, p_h = int(1920 * 0.55), int(1920 * 0.55 * 1.29) # A4 oranı
        page_img = colored.resize((p_w, p_h), Image.LANCZOS)
        # Hafif bir gölge efekti için masayı biraz karartıp sayfayı koyabiliriz ama şimdilik direkt koyalım
        desk_bg.paste(page_img, ((1920 - p_w) // 2, (1920 - p_h) // 2))
        mock.append(("01-lifestyle.jpg", desk_bg))
    except Exception as e:
        print(f"[coloring] Masa görseli üretilemedi: {e}")
        
    # 2. GÖRSEL: Grafik Kapak
    mock.append(("02-cover.jpg", mockups_coloring.cover(previews, colored, name, len(letter), palette)))
    
    # 3. GÖRSEL: Tüm sayfaların grid görünümü (Müşteri ne alacağını görsün)
    mock.append(("03-all.jpg", mockups.grid(previews, f"{len(letter)} Coloring Pages Included", palette, cols=4)))
    
    # 4. GÖRSEL: Renklendirme örneği (Color Your Way)
    mock.append(("04-example.jpg", mockups.info_card("COLOR YOUR WAY", [
        "Use colored pencils, markers or crayons",
        "Print as many times as you like",
        "US Letter and A4 PDFs included",
        "Single-sided pages, 300 DPI",
    ], palette, colored)))
    
    # 5, 6, 7. GÖRSEL: Rastgele sayfa önizlemeleri
    for i, pv in enumerate(previews[1:4], 5):
        mock.append((f"0{i}-page.jpg", mockups.info_card(name.upper(), [p["name"] for p in spec["pages"][:N_PAGES]][:6], palette, pv)))
        
    # 8. GÖRSEL: Kağıt boyutları ve detaylar
    mock.append(("08-sizes.jpg", mockups.info_card("WHAT YOU GET", [
        "1 PDF in US Letter size (8.5x11 in)",
        "1 PDF in A4 size",
        "Crisp black line art, 300 DPI",
        "Instant Download"
    ], palette, previews[4])))
    
    # 9. GÖRSEL: Nasıl çalışır?
    mock.append(("09-how.jpg", mockups.how_it_works(palette)))

    # İLK GÖRSEL: "bundle" kapağı – gerçek sayfa sayısı, arkada sayfaların kolajı (+ renkli örnek)
    mock.insert(0, ("00-bundle.jpg", bundle_cover(
        previews + [colored, colored.convert("RGB")], len(letter), "Coloring Pages", name, palette,
        ribbon="PRINTABLE", sticker=("US LETTER", "A4", "PDF"),
        features=["PRINTABLE PDF", "US LETTER + A4", "300 DPI", "INSTANT DOWNLOAD"])))
    mock = mock[:10]

    return {
        "delivery": delivery,
        "mockups": [(n, jpeg_bytes(im, 88, dpi=72)) for n, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [
            f"{len(letter)} printable coloring pages",
            "1 PDF in US Letter size (8.5x11 in)",
            "1 PDF in A4 size",
        ],
        "details": ["300 DPI, crisp black line art", "Single-sided pages with margins for easy printing"],
        "usage": ["Print at home on regular or thicker paper", "Print as many copies as you need for your own use"],
        "license": "For personal and classroom use only. Please do not share, resell or redistribute the files.",
        "taxonomy": ["Coloring Books", "Coloring Pages", "Digital Prints"],
        "taxonomy_fallback_id": 2078,
        "is_supply": False,
    }
