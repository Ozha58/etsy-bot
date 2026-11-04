"""Redraw the cover of an already published listing with today's cover design and replace the
first photo on Etsy (Telegram: /kapak <id> or /kapak hepsi). Uses the product's stored files,
so no image quota is spent."""
import io
import zipfile

from PIL import Image

from . import assets, etsy, mockups_scenes, mockups_wallpaper, storage, telegram, watermark
from .imgutil import jpeg_bytes
from .telegram import esc

SUPPORTED = ("scenes", "wallpaper", "planner")


def _images_from_zips(p, want=None, limit=15):
    ims = []
    for f in p.get("files", []):
        if not f["name"].endswith(".zip") or (want and want not in f["name"]):
            continue
        z = zipfile.ZipFile(io.BytesIO(assets.download(p["id"], "file__" + f["name"])))
        for n in sorted(z.namelist()):
            if n.lower().endswith((".jpg", ".jpeg", ".png")):
                im = Image.open(io.BytesIO(z.read(n))).convert("RGB")
                im.thumbnail((1400, 1400), Image.LANCZOS)
                ims.append(im)
                if len(ims) >= limit:
                    return ims
    return ims


def new_cover(p):
    spec = p.get("spec", {})
    palette = spec.get("palette", [])
    if p["type"] == "scenes":
        ims = _images_from_zips(p, limit=15)
        if not ims:
            raise RuntimeError("ürün dosyalarında görsel bulunamadı")
        return mockups_scenes.collage_cover(ims, spec.get("bundle_name", "Illustration Bundle"), len(ims), palette)
    if p["type"] == "wallpaper":
        ims = _images_from_zips(p, want="iPhone", limit=10) or _images_from_zips(p, limit=10)
        if not ims:
            raise RuntimeError("ürün dosyalarında görsel bulunamadı")
        return mockups_wallpaper.cover(ims, spec.get("bundle_name", "Phone Wallpapers"), len(ims), palette)
    if p["type"] == "planner":
        return _planner_cover(p)
    raise RuntimeError(f"bu ürün türü için kapak yenileme yok ({p['type']})")


def _planner_cover(p):
    """New best-seller style cover for an existing planner listing, with honest numbers from its own files."""
    import re
    from . import planner_pdf
    from .imgutil import hex2rgb
    from .products import planner as PL
    pdfs, n_st, n_cov = {}, 0, 0
    for f in p.get("files", []):
        if not f["name"].endswith(".zip"):
            continue
        z = zipfile.ZipFile(io.BytesIO(assets.download(p["id"], "file__" + f["name"])))
        for n in z.namelist():
            low = n.lower()
            if low.endswith(".pdf") and "sunday" in low:
                pdfs[low] = z.read(n)
            elif low.startswith("stickers/") and low.endswith(".png"):
                n_st += 1
            elif low.startswith("covers/"):
                n_cov += 1
    if not pdfs:
        raise RuntimeError("planlayıcı PDF'i bulunamadı")
    light = next((v for k, v in pdfs.items() if "dark" not in k), None) or next(iter(pdfs.values()))
    dark = next((v for k, v in pdfs.items() if "dark" in k), light)
    import pypdfium2 as pdfium
    n_pages = len(pdfium.PdfDocument(light))
    front, back1 = planner_pdf.render_pages(light, [0, 3], 1400)
    back2 = planner_pdf.render_pages(dark, [5], 1400)[0]
    themes = len({k.split("-sunday")[0].rsplit("-", 1)[-1] for k in pdfs})
    m = re.search(r"(\d+)\+?\s+templates", p.get("description", ""), re.I)
    n_tpl = int(m.group(1)) if m else 0
    badges = [(f"{n_pages // 50 * 50}+", "LINKED PAGES")]
    badges.append((str(themes), "COLOR THEMES") if themes > 2 else ("LIGHT", "& DARK MODE"))
    if n_tpl:
        badges.append((f"{n_tpl}+", "TEMPLATES"))
    if n_st:
        badges.append((f"{n_st // 50 * 50}+", "STICKERS"))
    badges.append((f"{n_cov}" if n_cov else "SUN", "COVERS" if n_cov else "& MON START"))
    pal = [hex2rgb(c) for c in p.get("spec", {}).get("palette", [])] or [(196, 140, 50)]
    return PL._cover_mock(front, [back1, back2], pal[0], badges[:5])


def clean_title(title):
    """Remove app / brand names and fix capitals (e.g. 'moose xodo Digital Planner' -> 'Moose Digital Planner')."""
    import re
    from . import research
    t = title or ""
    for b in research.BANNED:
        t = re.sub(r"\b" + re.escape(b) + r"\b", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,-|")
    return etsy.nice_title(t[:1].upper() + t[1:])


def refresh(p):
    lid = p.get("etsy", {}).get("listing_id")
    if p.get("status") != "published" or not lid:
        raise RuntimeError("ürün Etsy'de yayında değil")
    cover = new_cover(p)
    data = jpeg_bytes(cover, 88, dpi=72)
    if p["type"] != "planner":
        data = watermark.apply_all([("01-cover.jpg", data)])[0][1]
    title = clean_title(p["title"])
    if title and title != p["title"]:
        try:
            etsy.update_title(lid, title)
            p["title"] = title
        except Exception as e:
            print(f"[recover] başlık düzeltilemedi: {e}")
    etsy.replace_main_image(lid, data, f"{p['title']} - cover preview")
    return data


def run(arg):
    arg = (arg or "").strip()
    pub = [p for p in storage.all_products() if p.get("status") == "published" and p.get("type") in SUPPORTED]
    if arg.lower() in ("hepsi", "all"):
        targets = [p for p in pub if not p.get("cover_refreshed")][:6]
    else:
        targets = [p for p in pub if arg in (p["id"], str(p.get("etsy", {}).get("listing_id")))]
    if not targets:
        telegram.send("Kapağı yenilenecek ürün bulunamadı. Kullanım: <code>/kapak 20261101-03</code> veya <code>/kapak hepsi</code> "
                      "veya Etsy ilan numarasıyla <code>/kapak 4610043051</code> (sahne paketi, wallpaper ve planlayıcı).")
        return False
    changed = False
    for p in targets:
        try:
            data = refresh(p)
            p["cover_refreshed"] = True
            storage.add_event(p, "Kapak yenilendi")
            storage.save_product(p)
            changed = True
            telegram.album([("cover.jpg", data)], caption=f"🖼 Kapak yenilendi: <b>{esc(p['title'][:80])}</b>")
        except Exception as e:
            telegram.send(f"⚠️ {esc(p['id'])} kapak yenilenemedi: <code>{esc(str(e)[:300])}</code>")
    left = len([p for p in pub if not p.get("cover_refreshed")])
    if arg.lower() in ("hepsi", "all") and left:
        telegram.send(f"Kalan {left} ürün için tekrar <code>/kapak hepsi</code> yazın.")
    return changed
