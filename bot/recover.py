"""Redraw the cover of an already published listing with today's cover design and replace the
first photo on Etsy (Telegram: /kapak <id> or /kapak hepsi). Uses the product's stored files,
so no image quota is spent. Planners are rebuilt completely (new PDFs, stickers, covers and all
10 photos, no watermark) from their own cover art and stickers."""
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
    pdfs, n_st, n_cov, art = {}, 0, 0, None
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
                if low.endswith("cover-01.jpg"):  # the clean AI cover art
                    art = Image.open(io.BytesIO(z.read(n))).convert("RGB")
    if not pdfs:
        raise RuntimeError("planlayıcı PDF'i bulunamadı")
    light = next((v for k, v in pdfs.items() if "dark" not in k), None) or next(iter(pdfs.values()))
    dark = next((v for k, v in pdfs.items() if "dark" in k), light)
    import pypdfium2 as pdfium
    n_pages = len(pdfium.PdfDocument(light))
    front, back1 = planner_pdf.render_pages(light, [0, 3], 1400)
    if art is not None:  # redraw the first page with today's layout (small card low, art fully visible)
        try:
            spec = p.get("spec", {})
            name = spec.get("planner_name") or "Digital Planner"
            title = name if "planner" in name.lower() else f"{name} Planner"
            pal0 = [hex2rgb(c) for c in spec.get("palette", [])] or [(150, 110, 90)]
            pp = planner_pdf.Planner(title, pal0, art, [], "sun", False)
            front = planner_pdf.render_pages(pp.build(), [0], 1400)[0]
        except Exception as e:
            print(f"[kapak] yeni ilk sayfa çizilemedi: {e}")
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
    return PL._cover_mock(front, [back1, back2], pal[0], badges[:5], art=art)


def _art_from_pdf(pdf_bytes):
    """The clean cover art is embedded as an image on the planner's first page (the title card is vector on top)."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    page = pdfium.PdfDocument(pdf_bytes)[0]
    best = None
    for o in page.get_objects():
        if o.type == raw.FPDF_PAGEOBJ_IMAGE:
            im = o.get_bitmap(render=False).to_pil().convert("RGB")
            if best is None or im.width * im.height > best.width * best.height:
                best = im
    return best


REBUILD_LOOKS = [  # (name, palette, tag) calm, animal-free looks for rebuilt planners
    ("Neutral Boho", [(150, 110, 90), (176, 152, 110), (124, 150, 120)], "boho planner"),
    ("Sage Green", [(124, 150, 120), (176, 160, 130), (150, 130, 120)], "sage green planner"),
    ("Minimal Beige", [(170, 150, 125), (140, 130, 120), (200, 180, 150)], "minimalist planner"),
    ("Terracotta", [(186, 110, 80), (200, 160, 120), (140, 120, 100)], "terracotta planner"),
    ("Dusty Rose", [(190, 130, 130), (200, 170, 150), (150, 130, 140)], "pink planner"),
]
ED_COPY = {  # edition -> (heading, rest of title, edition tags, intro)
    "life": ("Digital Planner", "Undated Hyperlinked iPad and Android Life Planner with Stickers",
             ["life planner", "daily planner", "weekly planner", "aesthetic planner"],
             "Plan your whole life in one calm, beautiful place. This undated digital planner is fully hyperlinked, so every "
             "tab, month, week and day is one tap away. Use it on your iPad or Android tablet with any PDF note-taking app."),
    "budget": ("Budget Planner", "Undated Digital Finance Planner for iPad and Android with Savings and Bill Trackers",
               ["budget planner", "finance planner", "savings tracker", "bill tracker", "money planner"],
               "Take control of your money with a calm, beautiful budget planner. Track spending, bills, savings and debt "
               "every day, plan each paycheck and watch your savings grow, all fully hyperlinked on your iPad or Android tablet."),
    "student": ("Student Planner", "Undated Digital Academic Planner for iPad and Android with Assignment Tracker",
                ["student planner", "academic planner", "college planner", "study planner", "assignment tracker"],
                "Stay on top of classes, assignments and exams with a calm, beautiful student planner. Plan every semester, "
                "week and study session, all fully hyperlinked on your iPad or Android tablet."),
    "adhd": ("ADHD Planner", "Undated Digital Planner for Focus, Routines and Brain Dumps, iPad and Android",
             ["adhd planner", "adhd digital planner", "routine planner", "focus planner", "brain dump"],
             "A calm, simple planner made for ADHD brains: just three things a day, a brain dump on every page, routines, "
             "a dopamine menu and focus logs, all fully hyperlinked on your iPad or Android tablet."),
    "wellness": ("Wellness Planner", "Undated Digital Health and Fitness Planner for iPad and Android",
                 ["wellness planner", "health planner", "fitness planner", "self care planner", "meal planner"],
                 "Look after your body and mind with a calm, beautiful wellness planner. Plan meals, workouts, water, sleep "
                 "and self-care every day, all fully hyperlinked on your iPad or Android tablet."),
    "business": ("Business Planner", "Undated Digital Small Business Planner for iPad and Android with Order Tracker",
                 ["business planner", "small business", "content planner", "order tracker", "entrepreneur"],
                 "Run your small business from one calm, beautiful planner. Track orders, clients, content and income every "
                 "day, plan launches and goals, all fully hyperlinked on your iPad or Android tablet."),
}


def rebuild_planner(p):
    """Rebuild an old planner listing with today's planner (750+ pages, new photos, no watermark) from its own art."""
    from . import generator, research
    from .products import planner as PL
    lid = p.get("etsy", {}).get("listing_id")
    if p.get("status") != "published" or not lid:
        raise RuntimeError("ürün Etsy'de yayında değil")
    pdf, objs = None, []
    for f in p.get("files", []):
        if not f["name"].endswith(".zip"):
            continue
        z = zipfile.ZipFile(io.BytesIO(assets.download(p["id"], "file__" + f["name"])))
        for n in sorted(z.namelist()):
            low = n.lower()
            if low.endswith(".pdf") and "dark" not in low and (pdf is None or "signature" in low and "sunday" in low):
                pdf = z.read(n)
            elif "01-themed/" in low and low.endswith(".png"):
                objs.append(Image.open(io.BytesIO(z.read(n))).convert("RGBA"))
    if not pdf:
        raise RuntimeError("planlayıcı PDF'i bulunamadı")
    # old planners were made around an animal: drop that art and those stickers. Every rebuilt planner gets an
    # edition and a color look not used yet in the shop, so two rebuilt listings are never the same product.
    spec = dict(p.get("spec", {}))
    others = [q.get("spec", {}) for q in storage.all_products() if q.get("type") == "planner" and q["id"] != p["id"]]
    used_ed = [o.get("edition", "life") for o in others]
    edition = min(ED_COPY, key=lambda e: (used_ed.count(e), list(ED_COPY).index(e)))
    used_names = [o.get("planner_name", "") for o in others]
    aname, pal, ltag = min(REBUILD_LOOKS, key=lambda l: (sum(n.startswith(l[0]) for n in used_names), REBUILD_LOOKS.index(l)))
    heading, rest, etags, intro = ED_COPY[edition]
    art = PL.boho_art(pal, seed=len(others) + 3)
    objs = []
    title = f"{aname} {heading}, {rest}"[:140]
    tags = list(dict.fromkeys(etags + [ltag, "digital planner", "undated planner", "ipad planner", "android planner",
                                       "hyperlinked planner", "planner stickers"]))
    tags = [t for t in tags if len(t) <= 20][:13]
    spec.update({"planner_name": f"{aname} {heading.replace(' Planner', '').replace('Digital', '').strip()}".strip(),
                 "title": title, "tags": tags, "edition": edition, "look": None, "intro": intro,
                 "palette": ["#%02x%02x%02x" % c for c in pal]})
    slug = research.slugify(title, 40)
    built = PL.assemble(spec, slug, art, objs)
    desc = generator.compose_description(spec, built) if spec.get("intro") else p.get("description", "")
    telegram.send("⏳ Yeni dosyalar Etsy'ye yükleniyor…")
    etsy.replace_files(lid, built["delivery"])
    etsy.replace_all_images(lid, built["mockups"], title)
    try:
        etsy.update_listing(lid, title=title[:140], description=desc, tags=tags)
    except Exception as e:
        print(f"[recover] başlık/açıklama güncellenemedi: {e}")
    payload = {f"file__{n}": b for n, b in built["delivery"]}
    payload.update({f"photo__{n}": b for n, b in built["mockups"]})
    assets.upload(p["id"], payload)
    p.update({"title": title, "description": desc, "tags": tags, "spec": spec, "thumb": built["thumb"],
              "files": [{"name": n, "size": len(b)} for n, b in built["delivery"]],
              "photos": [n for n, _ in built["mockups"]], "rebuilt": True})
    return built["mockups"]


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
        targets = [p for p in pub if not p.get("cover_refreshed")]
        targets = [p for p in targets if p["type"] != "planner"][:6] + [p for p in targets if p["type"] == "planner"][:1]
    else:
        targets = [p for p in pub if arg in (p["id"], str(p.get("etsy", {}).get("listing_id")))]
    if not targets:
        telegram.send("Kapağı yenilenecek ürün bulunamadı. Kullanım: <code>/kapak 20261101-03</code> veya <code>/kapak hepsi</code> "
                      "veya Etsy ilan numarasıyla <code>/kapak 4610043051</code> (sahne paketi, wallpaper ve planlayıcı).")
        return False
    changed = False
    for p in targets:
        try:
            if p["type"] == "planner":
                telegram.send(f"📒 Planlayıcı baştan yenileniyor (yeni sayfalar, 10 yeni fotoğraf, filigransız): "
                              f"<b>{esc(p['title'][:80])}</b> – ~5 dk")
                photos = rebuild_planner(p)
                p["cover_refreshed"] = True
                storage.add_event(p, "Planlayıcı yenilendi")
                storage.save_product(p)
                changed = True
                telegram.album(photos[:10], caption=f"✅ Yenilendi: <b>{esc(p['title'][:80])}</b>")
                continue
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
