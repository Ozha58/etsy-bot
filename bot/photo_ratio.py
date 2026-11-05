"""Every listing photo square (2000 x 2000).

Etsy sizes a listing's photo frame by its FIRST photo, shows Shop Home and market pages square and says buyers
buy more from shops with square photos. Our covers were 4:5 portrait and the other photos 4:3 landscape, so on a
computer Etsy showed them small with empty bands. Now: the 4:5 cover is cut to its centre square (its text and
badges are designed to stay inside y 10-90 %), every other photo is placed whole on a square canvas, the free
space filled with a soft, blurred continuation of the photo itself.
Telegram: /foto <id or listing no> or /foto hepsi (published listings)."""
import io

from PIL import Image, ImageEnhance, ImageFilter

from . import assets, etsy, storage, telegram
from .imgutil import jpeg_bytes
from .telegram import esc


def fit_to(im, size):
    """im (any ratio) -> exactly `size`, nothing cropped: the photo centred on a blurred, lightened copy of itself."""
    W, H = size
    im = im.convert("RGB")
    if abs(im.width / im.height - W / H) < 0.01:
        return im.resize(size, Image.LANCZOS)
    s = max(W / im.width, H / im.height)
    bg = im.resize((int(im.width * s) + 2, int(im.height * s) + 2), Image.BILINEAR)
    l, t = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", size, (250, 248, 244)), 0.55)
    s = min(W / im.width, H / im.height)
    fg = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    shadow = Image.new("L", size, 0)
    sx, sy = (W - fg.width) // 2, (H - fg.height) // 2
    shadow.paste(255, (sx, sy + 14, sx + fg.width, sy + fg.height + 14))
    dark = Image.new("RGB", size, (60, 50, 45))
    bg = Image.composite(dark, bg, shadow.filter(ImageFilter.GaussianBlur(22)).point(lambda v: v * 60 // 255))
    bg.paste(fg, (sx, sy))
    return bg


SQUARE = (2000, 2000)


def to_square(im, crop=False):
    """crop=True: cut the centre square (for a cover built for every crop); else fit whole with blurred bands."""
    im = im.convert("RGB")
    if crop:
        s = min(im.size)
        l, t = (im.width - s) // 2, (im.height - s) // 2
        return im.crop((l, t, l + s, t + s)).resize(SQUARE, Image.LANCZOS)
    return fit_to(im, SQUARE)


def same_ratio(mockups):
    """[(name, jpeg bytes)] -> every photo 2000 x 2000. The first one (the cover) is centre-cropped when it is a
    4:5 portrait cover, every other photo is kept whole."""
    out = []
    for k, (name, data) in enumerate(mockups):
        im = Image.open(io.BytesIO(data))
        if im.size == SQUARE:
            out.append((name, data))
            continue
        crop = k == 0 and 0.75 <= im.width / im.height <= 0.85
        out.append((name, jpeg_bytes(to_square(im, crop), 88, dpi=72)))
    return out


def needs_fix(sizes):
    return any(abs(w / h - 1) > 0.01 for w, h in sizes)


def fix_listing(p):
    lid = p.get("etsy", {}).get("listing_id")
    photos = [(n, assets.download(p["id"], "photo__" + n)) for n in p.get("photos", [])]
    if not lid or len(photos) < 2:
        raise RuntimeError("ilan ya da fotoğraf bulunamadı")
    if not needs_fix([Image.open(io.BytesIO(b)).size for _, b in photos]):
        return None
    photos = same_ratio(photos)
    etsy.replace_all_images(lid, photos[:10], p.get("title", ""))
    assets.upload(p["id"], {f"photo__{n}": b for n, b in photos})
    return photos


def run(arg):
    arg = (arg or "").strip()
    pub = [p for p in storage.all_products() if p.get("status") == "published" and p.get("etsy", {}).get("listing_id")]
    if arg.lower() in ("hepsi", "all"):
        targets = [p for p in pub if not p.get("photo_ratio_ok")][:4]
    else:
        targets = [p for p in pub if arg in (p["id"], str(p.get("etsy", {}).get("listing_id")))]
    if not targets:
        telegram.send("Fotoğrafı düzeltilecek ilan bulunamadı. Kullanım: <code>/foto 4606392470</code> veya <code>/foto hepsi</code>")
        return False
    changed = False
    for p in targets:
        try:
            res = fix_listing(p)
            p["photo_ratio_ok"] = True
            storage.save_product(p)
            changed = True
            if res:
                storage.add_event(p, "Fotoğraf oranları eşitlendi")
                telegram.send(f"🖼 Fotoğraflar aynı boya getirildi: <b>{esc(p['title'][:70])}</b>")
        except Exception as e:
            telegram.send(f"⚠️ {esc(p['id'])} fotoğrafları düzeltilemedi: <code>{esc(str(e)[:300])}</code>")
    left = len([p for p in pub if not p.get("photo_ratio_ok")])
    if arg.lower() in ("hepsi", "all") and left:
        telegram.send(f"Kalan {left} ilan için tekrar <code>/foto hepsi</code> yazın.")
    return changed
