"""Daily run: research niches, build products, store them and ask for approval on Telegram."""
import datetime as dt
import random
import time
import traceback
from zoneinfo import ZoneInfo

from . import assets, config, images, research, storage, telegram
from .products import TYPES, type_label
from .telegram import esc


def notify(text):
    try:
        telegram.send(text)
    except Exception as e:
        print(f"[generate] Telegram mesajı gönderilemedi: {e}")


def today_local():
    return dt.datetime.now(ZoneInfo(config.settings()["timezone"])).date()


def compose_description(spec: dict, built: dict) -> str:
    def section(title, lines):
        return title + "\n" + "\n".join(f"• {l}" for l in lines)

    parts = ["✨ " + spec["intro"].strip()]  # a few emojis (3-4) look friendly; never more
    parts.append(section("🎁 WHAT'S INCLUDED", built["included"]))
    parts.append(section("FILE DETAILS", built["details"]))
    parts.append(section("💡 HOW TO USE", built["usage"]))
    parts.append(section("📌 PLEASE NOTE", [
        "This is a digital download. No physical item will be shipped.",
        "Your files are available right after purchase under Purchases & Reviews.",
        "Colors may vary slightly between screens and printers.",
        "Artwork created with the help of AI tools, then curated, edited and prepared for print by our shop.",
        built["license"],
    ]))
    return "\n\n".join(parts)


def used_niches(days):
    cutoff = time.time() - days * 86400
    return [p["niche"] for p in storage.all_products() if p.get("created_at", 0) >= cutoff and p.get("niche")]


def next_id(day: dt.date):
    prefix = day.strftime("%Y%m%d")
    existing = [p["id"] for p in storage.all_products() if p["id"].startswith(prefix)]
    return f"{prefix}-{len(existing) + 1:02d}"


def product_caption(p: dict) -> str:
    t = type_label(p["type"])
    lines = [
        f"🆕 <b>{esc(p['title'])}</b>",
        "",
        f"📦 Tür: {esc(t)}",
        f"🎯 Niş: {esc(p['niche'])}",
        f"💵 Fiyat: ${p['price_usd']:.2f}",
    ]
    if p.get("research", {}).get("etsy_results") is not None:
        r = p["research"]
        lines.append(f"📊 Etsy: {r['etsy_results']:,} rakip ilan, ilk 25'te ortanca {int(r.get('etsy_median_favs') or 0)} favori")
        if r.get("why"):
            lines.append(f"💡 {esc(str(r['why'])[:200])}")
        if r.get("source") == "etsy":
            lines.append("🔎 Kaynak: Etsy araması (rakiplerin gerçek etiketlerinden)")
        elif r.get("source") == "scan":
            lines.append("🔭 Kaynak: niş taraması (/nis)")
        if r.get("etsy_median_price"):
            lines.append(f"💲 Piyasa ortanca fiyatı: ${r['etsy_median_price']:.2f}")
    if p.get("research", {}).get("variation_of"):
        lines.append(f"🏆 Çok satan ürünün varyasyonu: {esc(p['research']['variation_of'][:80])}")
    lines.append(f"🏷 {esc(', '.join(p['tags']))}")
    files = "\n".join(f"  • <code>{esc(f['name'])}</code> ({f['size'] / 1048576:.1f} MB)" for f in p["files"])
    lines.append(f"📁 Teslimat dosyaları:\n{files}")
    lines.append(f"\n<code>{p['id']}</code>")
    return "\n".join(lines)


def approval_buttons(pid):
    return [[("✅ Onayla ve yayınla", f"ok:{pid}"), ("❌ Reddet", f"no:{pid}")],
            [("📝 Açıklama", f"desc:{pid}"), ("📦 Dosyaları gönder", f"files:{pid}")]]


def _cover_version():
    from .recover import COVER_VERSION
    return COVER_VERSION


KICKERS = {"sublimation": "Sublimation PNG Designs", "journal": "Printable Journal Pages", "planner": "Undated Digital Planner", "stickers": "Digital Stickers", "clipart": "Transparent PNG Clipart",
           "junk_journal": "Printable Junk Journal Kit", "coloring": "Printable Coloring Pages", "wallpaper": "Phone Wallpapers",
           "pattern": "Seamless Digital Paper", "wall_art": "Printable Wall Art", "scenes": "Illustration Pack",
           "tumbler": "Tumbler Wrap Design"}
FEATURES = {"sublimation": ["Transparent PNG", "Text set sharp", "Mug wrap included", "Commercial use"],
            "journal": ["Dated pages", "Habit & mood trackers", "A4 · A5 · Letter", "Print at home"],
            "planner": ["Hyperlinked tabs", "Light & dark mode", "Stickers included", "iPad & Android"],
            "stickers": ["Transparent PNG", "Sticker book PDF", "Printable sheets", "Any note app"],
            "clipart": ["Transparent PNG", "Commercial use", "Sticker sheets", "Instant download"],
            "junk_journal": ["Pages, cards & tags", "Stickers & stamps", "Print at home", "300 DPI"]}


SUBJECT_SCENES = {
    "migraine": [
        "a calm dim bedroom in soft lavender light, a silk sleep mask and a cold compress on the pillow, a glass of water "
        "and a cup of herbal tea on the nightstand, closed curtains, a tablet showing a planner page",
        "a cozy bedside table at dusk with a glass of water, a small pill organizer, peppermint oil, a cup of chamomile "
        "tea and an open planner with a pain tracker, soft blue and lavender tones, curtains drawn",
        "a quiet rest corner with a soft blanket, an eye mask, a hot water bottle, lavender sprigs and a tablet with a "
        "headache diary on the screen, very soft dim light, calm muted colors",
    ],
    "adhd": ["a tidy colorful desk with sticky notes, a timer, a checklist planner on a tablet and a cup of coffee, bright morning light"],
    "budget": ["a calm desk with a tablet showing a budget planner, a calculator, coins in a jar, receipts and a cup of coffee, soft daylight"],
    "student": ["a study desk with books, highlighters, a laptop and a tablet planner, warm lamp light, campus window"],
}


def _topic_cover(idea, spec, slug, built):
    """Replace the first photo with a cover made around an AI scene of this product's own subject."""
    from . import covers
    from .bundle_cover import delivery_items
    recent = [p.get("cover_layout") for p in sorted(storage.all_products(), key=lambda p: -p.get("created_at", 0))
              if p.get("cover_layout")]
    layout = covers.choose_layout(slug, recent)
    scene = spec.get("cover_scene") or f"a cozy scene about {idea.get('niche', spec.get('title', ''))}"
    subject = (spec.get("edition") or "") + " " + spec.get("title", "") + " " + spec.get("subject", "")
    for key, scenes in SUBJECT_SCENES.items():  # a known need: the cover always shows THAT world, never a generic decor
        if key in subject.lower():
            scene = random.Random(slug).choice(scenes)
            break
    hero = images.try_generate(f"{scene}, {spec.get('style', '')}, {covers.SCENE_SUFFIX}", 1024, 1024)
    items = built.get("cover_items") or delivery_items(built["delivery"], limit=12)
    title = (spec.get("title") or "").split(",")[0].strip()
    cov = covers.make(layout, hero, items, title=title, kicker=built.get("cover_kicker") or KICKERS.get(idea["type"], ""),
                      count=built.get("count"), unit=built.get("cover_unit") or covers.UNITS.get(idea["type"], ""),
                      features=built.get("cover_features") or FEATURES.get(idea["type"], ()),
                      palette=spec.get("palette"), seed=slug)
    from .imgutil import jpeg_bytes, thumb_b64
    built["mockups"] = [("00-cover.jpg", jpeg_bytes(cov, 88, dpi=72))] + built["mockups"][:9]
    built["thumb"] = thumb_b64(cov)
    built["preview"] = cov
    return layout


def build_one(idea: dict, day: dt.date) -> dict:
    plan = TYPES[idea["type"]].prepare(idea, day) if hasattr(TYPES[idea["type"]], "prepare") else None
    spec = research.product_spec(idea)
    if plan:  # decided by code (e.g. journal: month / year bundle, colour / black & white, price ladder)
        spec.update(plan)
    pid = next_id(day)
    slug = research.slugify(spec.get("title"), 40)
    mod = TYPES[idea["type"]]
    t0 = time.time()
    built = mod.build(spec, slug)
    if not built or "included" not in built:
        raise Exception(f"HATA: {mod.__name__} dosyası görselleri üretirken çöktü ve boş döndü.")
    layout = None
    try:  # a topic cover in a layout the shop has not used lately (never the same template on every listing)
        if not built.get("own_cover"):  # e.g. sublimation: its first photo shows the designs on shirts and mugs
            layout = _topic_cover(idea, spec, slug, built)
    except Exception as e:
        print(f"[cover] konu kapağı yapılamadı, ürünün kendi kapağı kalıyor: {e}")
    try:
        from . import watermark
        if idea["type"] != "planner":  # planner photos only show empty templates: a watermark just hurts the look
            built["mockups"] = watermark.apply_all(built["mockups"])
    except Exception as e:
        print(f"[watermark] eklenemedi: {e}")
    try:  # every photo in the first photo's shape, so Etsy shows them full size on computer and phone
        from . import photo_ratio
        built["mockups"] = photo_ratio.same_ratio(built["mockups"])
    except Exception as e:
        print(f"[photo_ratio] yapılamadı: {e}")
    p = {
        "id": pid,
        "created_at": int(time.time()),
        "day": day.isoformat(),
        "cover_layout": layout,
        "status": "pending",
        "type": idea["type"],
        "niche": idea["niche"],
        "research": {k: idea.get(k) for k in ("search_query", "why", "etsy_results", "etsy_median_favs", "etsy_median_price", "etsy_velocity", "source", "score", "variation_of")},
        "title": spec["title"],
        "description": compose_description(spec, built),
        "tags": spec["tags"],
        "price_usd": spec["price_usd"],
        "spec": spec,
        "build": {k: built[k] for k in ("taxonomy", "taxonomy_fallback_id", "is_supply", "skip_attributes", "listing") if k in built},
        "files": [{"name": n, "size": len(b)} for n, b in built["delivery"]],
        "photos": [n for n, _ in built["mockups"]],
        "thumb": built["thumb"],
        "cover_version": _cover_version(),  # built with today's bundle cover: /kapak hepsi skips it
        "build_seconds": int(time.time() - t0),
    }
    p.update(built.get("product_extra", {}))
    storage.add_event(p, "oluşturuldu")
    payload = {f"file__{n}": b for n, b in built["delivery"]}
    payload.update(built.get("extra_assets", {}))  # e.g. custom: the artwork kept for rendering each order
    payload.update({f"photo__{n}": b for n, b in built["mockups"]})
    assets.upload(pid, payload)
    storage.save_product(p)
    storage.commit_and_push(f"Yeni ürün {pid}")
    # Telegram: photos + approval message
    try:
        telegram.album(built["mockups"])
        telegram.send(product_caption(p), approval_buttons(pid))
    except Exception as e:
        print(f"[generate] Telegram gönderilemedi: {e}")
    return p


def run(count=None, force=False):
    s = config.settings()
    day = today_local()
    target = int(count or s["products_per_day"])
    already = [p for p in storage.all_products() if p.get("day") == day.isoformat()]
    if not force and not count:
        target = max(0, target - len(already))
    if target == 0:
        print("[generate] Bugünün ürünleri zaten hazır.")  # (no Telegram message: avoid duplicates from backup triggers)
        return []
    notify(f"🔎 Günlük üretim başladı: {target} ürün hazırlanıyor… (genellikle 15-30 dk)")
    from .smart_niche import find_trending_niches
    notify(f"🧠 Yapay Zeka {target} adet mikro-niş fikri üretiyor...")
    chosen = find_trending_niches(target)
    reserve = []
    queue = chosen + reserve
    made, failed = [], []
    while queue and len(made) < target:
        idea = queue.pop(0)
        if any(m["type"] == idea["type"] for m in made) and sum(m["type"] == idea["type"] for m in made) >= s["max_same_type_per_day"]:
            continue
        print(f"[generate] → {idea['type']}: {idea['niche']}")
        try:
            made.append(build_one(idea, day))
        except Exception as e:
            traceback.print_exc()
            failed.append(f"{idea['niche']} ({idea['type']}): {str(e)[:320]}")
            if len(failed) >= target + 3:
                break
            if images.quota_exhausted():
                break  # no image provider left today, don't waste the remaining ideas
            if "Görsel üretilemedi" in str(e) and images.stats["cloudflare"] == 0 and images.stats["pollinations"] == 0 and len(failed) >= 2:
                break  # image providers are down, no point in trying more
    summary = [f"📋 <b>Günlük özet ({day.isoformat()})</b>: {len(made)}/{target} ürün hazırlandı."]
    if made:
        summary.append("Onay bekleyen ürünler yukarıda. ✅ ile onaylarsanız Etsy'de yayınlanır.")
    if images.quota_exhausted():
        summary.append("\n⛔ <b>Bugünkü ücretsiz görsel kotası doldu.</b> Kota her gün 03:00'te yenilenir; "
                       "yarın 11:15'teki otomatik üretim normal çalışır. Ek ürünü yarın /uret ile isteyebilirsin.")
    elif failed:
        summary.append("\n⚠️ Başarısız denemeler:\n" + "\n".join(f"• {esc(f)}" for f in failed[:6]))
    summary.append(f"\n🖼 Görsel: Cloudflare {images.stats['cloudflare']}, Pollinations {images.stats['pollinations']}, hata {images.stats['failed']}")
    try:
        u = images.usage_today()
        summary.append(f"🔋 Bugünkü ücretsiz kota: ~{u['used']:,}/{images.DAILY_NEURONS:,} kullanıldı, "
                       f"~{u['left_images']} görsel kaldı (03:00'te yenilenir)")
    except Exception as e:
        print(f"[generate] kota hesaplanamadı: {e}")
    if config.pages_url():
        summary.append(f"🌐 Panel: {config.pages_url()}")
    notify("\n".join(summary))
    if not made and not images.quota_exhausted():
        raise RuntimeError("Hiç ürün üretilemedi")
    return made
