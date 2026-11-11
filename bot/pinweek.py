"""Pinterest on autopilot (no Pinterest API approval needed).

Every Monday the bot picks published products (planners and journals first), draws a fresh 2:3 pin
image for each and schedules 5 pins a day over the week (latest.csv). During the week the listener
releases each pin at its time into two RSS feeds on the GitHub Pages site:
  pins/feed-planner.xml  -> board "Digital Planners & Stickers"
  pins/feed-shop.xml     -> board "Printables & Junk Journals"
A free IFTTT applet per feed ("RSS new item -> Pinterest create pin") posts them to Pinterest.
If the Pinterest API is connected with Standard access, pins are created directly instead."""
import csv
import datetime as dt
import io
import re
import time

from PIL import Image

from . import assets, config, social, storage, telegram
from .pinterest import BOARDS
from .telegram import esc

PINS_DIR = config.ROOT / "panel" / "pins"
HEADERS = ["Title", "Media URL", "Pinterest board", "Thumbnail", "Description", "Link", "Publish date", "Keywords"]
# good times for US buyers, in UTC: 14:00 (morning US), 19:00 (afternoon), 01:00 (evening)
SLOTS_UTC = [(13, 0), (16, 0), (19, 0), (22, 0), (1, 0)]
PINS_PER_WEEK = 35
WEIGHT = {"planner": 3, "stickers": 3, "journal": 3, "junk_journal": 2}  # planners sell best on Pinterest: more turns
FEEDS = {"planner": ("feed-planner.xml", f"{config.SHOP_NAME} Digital Planners", "Digital Planners & Stickers"),
         "shop": ("feed-shop.xml", f"{config.SHOP_NAME} Printables", "Printables & Junk Journals")}
FEED_KEEP = 40
KEEP_DAYS = 30


def _slug(text, n=40):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n] or "pin"


def pick_products(n: int) -> list:
    """Published products for n pins: least-pinned first, newest first, planners and junk journals get more turns.
    Never the same product twice in a row."""
    pub = [p for p in storage.all_products() if p["status"] == "published" and p.get("etsy", {}).get("url")]
    if not pub:
        return []
    pub.sort(key=lambda p: -p.get("etsy", {}).get("published_at", 0))
    count = {p["id"]: len(p.get("pin_history", [])) for p in pub}
    out = []
    while len(out) < n:
        last = out[-1]["id"] if out else None
        cand = [p for p in pub if p["id"] != last] or pub
        best = min(cand, key=lambda p: count[p["id"]] / WEIGHT.get(p["type"], 1))
        count[best["id"]] += 1
        out.append(best)
    return out


def _slots(count: int, start: dt.datetime) -> list:
    """count publish datetimes (UTC) spread over the 7 days after start."""
    per_day = max(1, -(-count // 7))
    slots = []
    day = (start + dt.timedelta(days=1)).date()
    while len(slots) < count:
        for h, m in SLOTS_UTC[:per_day]:
            when = dt.datetime.combine(day + dt.timedelta(days=1 if h < 6 else 0), dt.time(h, m))
            slots.append(when)
            if len(slots) >= count:
                break
        day += dt.timedelta(days=1)
    return slots


def _prune():
    if not PINS_DIR.exists():
        return
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in PINS_DIR.glob("*.jpg"):
        if f.stat().st_mtime < cutoff:
            f.unlink()


def sync_titles():
    """Use the titles that are live on Etsy (they may have been edited there)."""
    import html
    from . import etsy
    try:
        live = {str(l["listing_id"]): html.unescape(l.get("title", "")) for l in etsy.shop_listings("active")}
    except Exception as e:
        print(f"[pinweek] Etsy başlıkları alınamadı: {e}")
        return 0
    n = 0
    for p in storage.all_products():
        t = live.get(str(p.get("etsy", {}).get("listing_id")))
        if t and p.get("title") != t:
            p["title"] = t
            storage.save_product(p)
            n += 1
    print(f"[pinweek] {n} ürün başlığı Etsy ile eşitlendi")
    return n


def build(n_pins=None, fresh=False):
    s = config.settings()
    sync_titles()
    if fresh:  # rebuild the last file from scratch: forget the dates it scheduled
        first = (storage.load_meta().get("pinweek", {}).get("first") or "9999")[:10]
        for p in storage.all_products():
            if p.get("pin_history"):
                p["pin_history"] = [d for d in p["pin_history"] if d < first]
                storage.save_product(p)
    n = int(n_pins or max(int(s.get("pins_per_week", PINS_PER_WEEK)), PINS_PER_WEEK))
    products = pick_products(n)
    if not products:
        raise RuntimeError("Henüz yayınlanmış ürün yok, pin dosyası oluşturulamadı.")
    PINS_DIR.mkdir(parents=True, exist_ok=True)
    _prune()
    base = config.pages_url() + "pins/"
    now = dt.datetime.utcnow()
    week = now.strftime("%Y-%m-%d")
    rows, previews, used = [], [], {}
    for when, p in zip(_slots(len(products), now), products):
        k = used.get(p["id"], 0) + len(p.get("pin_history", []))
        used[p["id"]] = used.get(p["id"], 0) + 1
        photos = [(nm, assets.download(p["id"], "photo__" + nm)) for nm in p["photos"]]
        ims = social._pick_photos(p, photos)
        ims = ims[k % len(ims):] + ims[:k % len(ims)]  # a different hero image each time the product repeats
        jpg = social.pin_image(p, ims)
        fname = f"{week}-{_slug(p['title'])}-{k}.jpg"
        (PINS_DIR / fname).write_bytes(jpg)
        texts = social.texts(p, p["etsy"]["url"])
        rows.append({
            "Title": texts["pin_title"],
            "Media URL": base + fname,
            "Pinterest board": FEEDS["planner" if p["type"] in ("planner", "stickers", "journal") else "shop"][2],
            "Thumbnail": "",
            "Description": texts["pin_desc"],
            "Link": p["etsy"]["url"],
            "Publish date": when.strftime("%Y-%m-%dT%H:%M:%S"),
            "Keywords": ", ".join(social.good_tags(p)[:10]),
        })
        p.setdefault("pin_history", []).append(when.strftime("%Y-%m-%d"))
        storage.save_product(p)
        if len(previews) < 4:
            previews.append((fname, jpg))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEADERS)
    w.writeheader()
    w.writerows(rows)
    csv_bytes = buf.getvalue().encode("utf-8")
    meta = storage.load_meta()
    meta["pinweek"] = {"week": week, "rows": len(rows), "first": rows[0]["Publish date"], "last": rows[-1]["Publish date"]}
    storage.save_meta(meta)
    (PINS_DIR / "latest.csv").write_bytes(csv_bytes)
    write_feeds()
    return rows, csv_bytes, previews


def notify():
    """After a new week's pins are built: short note."""
    meta = storage.load_meta()
    pw = meta.get("pinweek", {})
    meta["pin_cursor"] = 0
    storage.save_meta(meta)
    telegram.send(f"📌 <b>Bu haftanın {pw.get('rows', '?')} Pinterest pini hazır.</b>\n"
                  "Her gün 5 tanesi saatinde kendiliğinden Pinterest'e gidecek (ABD saatine göre en iyi saatler).")


# ---------------------------------------------------------------- autopilot: release pins into RSS feeds

def _rfc822(ts):
    import email.utils
    return email.utils.formatdate(ts, usegmt=True)


def _x(t):
    import html
    return html.escape(str(t or ""), quote=True)


def _sample(key):
    site = config.pages_url()
    img, title, link = "", f"{config.SHOP_NAME} Digital Planners" if key == "planner" else f"{config.SHOP_NAME} Printables", config.SHOP_URL
    f = PINS_DIR / "latest.csv"
    if f.exists():
        for r in csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))):
            if (r["Pinterest board"] == FEEDS["planner"][2]) == (key == "planner"):
                img, title, link = r["Media URL"], r["Title"], r["Link"]
                break
    if not img:
        jpgs = sorted(PINS_DIR.glob("*.jpg"))
        img = site + "pins/" + jpgs[-1].name if jpgs else site + "icon.png"
    return {"feed": key, "title": title, "desc": f"Instant digital downloads from {config.SHOP_NAME} on Etsy.", "link": link,
            "image": img, "guid": img + "#sample", "at": int(time.time()) - 30 * 86400, "size": 200000}


def write_feeds():
    """Write both RSS feeds from meta['pin_feed'] (always valid, even when empty)."""
    PINS_DIR.mkdir(parents=True, exist_ok=True)
    items = storage.load_meta().get("pin_feed", [])
    site = config.pages_url()
    for key, (fname, title, board) in FEEDS.items():
        mine = [i for i in items if i.get("feed") == key][-FEED_KEEP:][::-1]
        if not mine:  # an empty feed is refused by IFTTT: show one sample (old date, own guid, never posted again)
            mine = [_sample(key)]
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:media="http://search.yahoo.com/mrss/" xmlns:atom="http://www.w3.org/2005/Atom">',
               "<channel>", f"<title>{_x(title)}</title>", f"<link>{config.SHOP_URL}</link>",
               f"<description>{_x(board)} - instant digital downloads from {config.SHOP_NAME} on Etsy</description>",
               f'<atom:link href="{_x(site + "pins/" + fname)}" rel="self" type="application/rss+xml"/>',
               f"<lastBuildDate>{_rfc822(time.time())}</lastBuildDate>"]
        for i in mine:
            out += ["<item>", f"<title>{_x(i['title'])}</title>", f"<link>{_x(i['link'])}</link>",
                    f"<description>{_x(i['desc'])}</description>",
                    f'<content:encoded><![CDATA[<img src="{i["image"]}" alt="{_x(i["title"])}"/><p>{_x(i["desc"])}</p>]]></content:encoded>',
                    f'<guid isPermaLink="false">{_x(i.get("guid") or i["image"])}</guid>', f"<pubDate>{_rfc822(i['at'])}</pubDate>",
                    f'<enclosure url="{_x(i["image"])}" type="image/jpeg" length="{int(i.get("size", 200000))}"/>',
                    f'<media:content url="{_x(i["image"])}" medium="image" type="image/jpeg" width="1000" height="1500"/>',
                    f'<media:thumbnail url="{_x(i["image"])}"/>', "</item>"]
        out += ["</channel>", "</rss>"]
        (PINS_DIR / fname).write_text("\n".join(out), encoding="utf-8")


def release_due(max_late_hours=6):
    """Release every scheduled pin whose time has come (once). Returns the released rows."""
    f = PINS_DIR / "latest.csv"
    if not f.exists():
        return []
    rows = list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))))
    meta = storage.load_meta()
    done = set(meta.get("pins_released", []))
    now = dt.datetime.utcnow()
    due, skipped = [], []
    for r in rows:
        if r["Media URL"] in done:
            continue
        try:
            when = dt.datetime.fromisoformat(r["Publish date"])
        except Exception:
            continue
        if when > now:
            continue
        (skipped if now - when > dt.timedelta(hours=max_late_hours) else due).append(r)
    if not due and not skipped:
        return []
    api = False
    try:
        from . import pinterest
        api = pinterest.configured() and pinterest.connected() and storage.load_meta().get("pinterest_standard")
    except Exception:
        pass
    feed = meta.get("pin_feed", [])
    for r in due:
        key = "planner" if r["Pinterest board"] == FEEDS["planner"][2] else "shop"
        img = PINS_DIR / r["Media URL"].rsplit("/", 1)[-1]
        sent = False
        if api and img.exists():
            try:
                from . import pinterest
                pinterest.create_pin("planner" if key == "planner" else "shop", img.read_bytes(), r["Title"],
                                     r["Description"], r["Link"], r["Title"])
                sent = True
            except Exception as e:
                print(f"[pins] API ile pinlenemedi, RSS'e eklendi: {e}")
        if not sent:
            feed.append({"feed": key, "title": r["Title"][:100], "desc": r["Description"][:800], "link": r["Link"],
                         "image": r["Media URL"], "at": int(time.time()),
                         "size": img.stat().st_size if img.exists() else 200000})
    meta = storage.load_meta()
    meta["pin_feed"] = feed[-2 * FEED_KEEP:]
    meta["pins_released"] = (meta.get("pins_released", []) + [r["Media URL"] for r in due + skipped])[-400:]
    meta["pins_released_total"] = int(meta.get("pins_released_total", 0)) + len(due)
    storage.save_meta(meta)
    write_feeds()
    return due


def send_daily(n=3):
    """Send the next n pins of this week's list to Telegram, ready to post by hand."""
    f = PINS_DIR / "latest.csv"
    if not f.exists():
        raise RuntimeError("Bu haftanın pin listesi yok, /pinler ile oluşturun.")
    rows = list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))))
    meta = storage.load_meta()
    cur = int(meta.get("pin_cursor", 0))
    batch = rows[cur:cur + n]
    if not batch:
        telegram.send("📌 Bu haftanın pinleri bitti. Pazartesi yenileri gelecek (hemen istersen /pinler).")
        return 0
    for k, r in enumerate(batch, cur + 1):
        img = PINS_DIR / r["Media URL"].rsplit("/", 1)[-1]
        cap = (f"📌 <b>Pin {k}/{len(rows)}</b>  •  Pano: <b>{esc(r['Pinterest board'])}</b>\n\n"
               f"<b>Başlık:</b>\n<code>{esc(r['Title'])}</code>\n\n"
               f"<b>Açıklama:</b>\n<code>{esc(r['Description'][:600])}</code>\n\n"
               f"<b>Bağlantı:</b>\n<code>{esc(r['Link'])}</code>")[:1024]
        if img.exists():
            telegram.call("sendPhoto", {"chat_id": config.TELEGRAM_CHAT_ID, "caption": cap, "parse_mode": "HTML"},
                          files={"photo": (img.name, img.read_bytes(), "image/jpeg")}, timeout=120)
        else:
            telegram.send(cap + f"\n\nGörsel: {esc(r['Media URL'])}")
    meta["pin_cursor"] = cur + len(batch)
    storage.save_meta(meta)
    left = len(rows) - meta["pin_cursor"]
    telegram.send("👆 Pinterest'te: <b>Oluştur → Pin oluşturun</b> → görseli yükle → kutulara yapıştır → panoyu seç → Yayınla."
                  + (f"\n({left} pin bu hafta sırada)" if left else ""))
    return len(batch)


def run(n_pins=None, fresh=False):
    rows, _, previews = build(n_pins, fresh)
    print(f"[pinweek] {len(rows)} pin hazırlandı")
    try:
        telegram.album([(n, _jpg_small(b)) for n, b in previews],
                       f"🖼 Bu haftaki pinlerden örnekler ({len(rows)} pin hazırlanıyor, dosya birkaç dakika içinde gelecek)")
    except Exception as e:
        print(f"[pinweek] önizleme gönderilemedi: {e}")
    return rows


def _jpg_small(b):
    im = Image.open(io.BytesIO(b))
    im.thumbnail((700, 1050))
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=85)
    return out.getvalue()
