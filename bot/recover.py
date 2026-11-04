"""Redraw the cover of an already published listing with today's cover design and replace the
first photo on Etsy (Telegram: /kapak <id> or /kapak hepsi). Uses the product's stored files,
so no image quota is spent."""
import io
import zipfile

from PIL import Image

from . import assets, etsy, mockups_scenes, mockups_wallpaper, storage, telegram, watermark
from .imgutil import jpeg_bytes
from .telegram import esc

SUPPORTED = ("scenes", "wallpaper")


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
    raise RuntimeError(f"bu ürün türü için kapak yenileme yok ({p['type']})")


def refresh(p):
    lid = p.get("etsy", {}).get("listing_id")
    if p.get("status") != "published" or not lid:
        raise RuntimeError("ürün Etsy'de yayında değil")
    cover = new_cover(p)
    data = jpeg_bytes(cover, 88, dpi=72)
    data = watermark.apply_all([("01-cover.jpg", data)])[0][1]
    etsy.replace_main_image(lid, data, f"{p['title']} - cover preview")
    return data


def run(arg):
    arg = (arg or "").strip()
    pub = [p for p in storage.all_products() if p.get("status") == "published" and p.get("type") in SUPPORTED]
    if arg.lower() in ("hepsi", "all"):
        targets = [p for p in pub if not p.get("cover_refreshed")][:6]
    else:
        targets = [p for p in pub if p["id"] == arg]
    if not targets:
        telegram.send("Kapağı yenilenecek ürün bulunamadı. Kullanım: <code>/kapak 20261101-03</code> veya <code>/kapak hepsi</code> "
                      "(yalnızca yayındaki sahne paketi ve wallpaper ürünleri).")
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
