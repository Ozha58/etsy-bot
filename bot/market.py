"""Etsy market tools on the shop's own Etsy API key (free, run only when the owner asks in Telegram):

/radar          rising listings in the personalized PNG market, ranked by favorites per day
/etiket <words> the tags the best listings of a niche really use, plus price and competition
/sira           where our own active listings appear in Etsy search for their main phrase

The velocity radar and the rank tracker are adapted from etsy-engine (MIT License, Copyright (c) 2026 Raywake,
https://github.com/oguzhankayan/etsy-engine). Competitor titles are only read to measure demand; nothing is copied.
"""
import re
import statistics
import time
from collections import Counter

from . import etsy, research, storage, telegram
from .telegram import esc

RADAR_QUERIES = [
    "custom name png", "personalized png", "custom teacher png", "personalized sublimation png",
    "custom family name png", "personalized christmas png", "custom mama png", "personalized grandma png",
    "custom pet name png", "custom birthday png", "custom name shirt png", "personalized tumbler png",
]
MIN_FAVORERS = 8   # too few favorites: the speed number is noise
MIN_AGE_DAYS = 2.0
SAMPLE = 100       # Etsy returns at most 100 listings per search
PAUSE = 0.35       # stay far below Etsy's request limit

STOP = {"the", "a", "an", "and", "for", "of", "in", "on", "at", "to", "with", "by", "from", "your", "you",
        "printable", "digital", "download", "instant", "pdf", "png", "file", "files", "design", "designs",
        "bundle", "set", "pack", "sublimation", "transparent", "commercial", "use", "custom", "personalized",
        "2025", "2026", "2027"}
RANK_STOP = {"the", "a", "an", "and", "for", "of", "in", "on", "at", "to", "with", "by", "from", "your", "you",
             "printable", "digital", "download", "instant", "pdf", "bundle", "set", "pack", "2025", "2026", "2027"}


def _price(r):
    p = r.get("price") or {}
    if p.get("currency_code") == "USD" and p.get("divisor"):
        return int(p["amount"]) / int(p["divisor"])
    return None


def _phrase(title):
    """The first clause of an Etsy title, without counts and format words: the product idea, not the wording."""
    head = re.split(r"[|,–—:]", etsy.html_unescape(title or ""), maxsplit=1)[0]
    head = re.sub(r"^\s*(set of\s*)?\d+\b\s*(pages?|pack|piece|pcs|designs?)?!?\s*", "", head, flags=re.I)
    head = re.sub(r"\b(printable|instant download|pdf|digital download|bundle)\b", "", head, flags=re.I)
    return " ".join(head.split()).strip(" -,.")[:70]


def _age_days(r, now):
    born = float(r.get("original_creation_timestamp") or r.get("creation_timestamp") or 0)
    return max(MIN_AGE_DAYS, (now - born) / 86400) if born else None


# ---------------- 1. radar ----------------

def radar(queries=None, top=12):
    queries = queries or RADAR_QUERIES
    now = time.time()
    best = {}
    for q in queries:
        try:
            res = etsy.search_active(q, limit=SAMPLE)
        except Exception as e:
            print(f"[radar] '{q}' okunamadı: {e}")
            continue
        for r in res.get("results", []) or []:
            favs = int(r.get("num_favorers") or 0)
            age = _age_days(r, now)
            phrase = _phrase(r.get("title", ""))
            if favs < MIN_FAVORERS or not age or not phrase or research.is_banned(phrase):
                continue
            lid = r.get("listing_id")
            row = {"phrase": phrase, "speed": favs / age, "favs": favs, "age": age, "price": _price(r),
                   "id": lid, "query": q}
            if lid not in best or best[lid]["speed"] < row["speed"]:
                best[lid] = row
        time.sleep(PAUSE)
    rows = sorted(best.values(), key=lambda x: x["speed"], reverse=True)
    out, seen = [], set()
    for row in rows:  # one line per idea, not five near-identical listings of one shop
        key = " ".join(sorted(set(w for w in re.findall(r"[a-z]+", row["phrase"].lower()) if w not in STOP)))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= top:
            break
    lines = [f"📡 <b>Radar: kişiye özel PNG'de yükselenler</b>\n{len(queries)} arama, {len(best)} ilan tarandı. "
             "Sıralama: günde aldığı favori (satış hızının en iyi göstergesi).\n"]
    for i, r in enumerate(out, 1):
        price = f" · ${r['price']:.2f}" if r["price"] else ""
        lines.append(f"{i}. <b>{esc(r['phrase'])}</b>\n    {r['speed']:.1f} fav/gün · {r['favs']} fav · "
                     f"{int(r['age'])} günlük{price} · <a href=\"https://www.etsy.com/listing/{r['id']}\">ilan</a>")
    if out:
        lines.append("\nBeğendiğin fikrin rekabetine bak: /etiket kelimeler veya /nis kelimeler")
    else:
        lines.append("Hiç sonuç çıkmadı, Etsy bağlantısını /durum ile kontrol et.")
    telegram.send("\n".join(lines))
    return out


# ---------------- 2. tags ----------------

def tags(keyword, sample=50):
    from . import niche_scan
    keyword = (keyword or "").strip()
    if not keyword:
        telegram.send("Kullanım: <code>/etiket custom teacher name png</code>")
        return None
    res = etsy.search_active(keyword, limit=sample)
    results, count = res.get("results", []) or [], int(res.get("count", 0))
    if not results:
        telegram.send(f"🔎 <b>{esc(keyword)}</b> için Etsy'de ilan bulunamadı.")
        return None
    m = niche_scan.measure(keyword, results, count)
    tag_count = Counter()
    for r in results:
        for t in {x.strip().lower() for x in (r.get("tags") or []) if x.strip()}:
            if not research.is_banned(t):
                tag_count[t] += 1
    prices = [p for p in (_price(r) for r in results) if p]
    top_tags = tag_count.most_common(20)
    lines = [f"🏷 <b>{esc(keyword)}</b>",
             f"{count:,} rakip ilan · ilk 25'te ortanca {int(m['favs'])} fav · {m['speed']:.2f} fav/gün · "
             f"yeni ilan oranı %{int(m['fresh'] * 100)}"]
    if prices:
        lines.append(f"Fiyat: ortanca ${statistics.median(prices):.2f} (en düşük ${min(prices):.2f}, en yüksek ${max(prices):.2f})")
    lines.append(f"\n<b>En çok kullanılan etiketler</b> (ilk {len(results)} ilanda kaç tanesinde var):")
    lines += [f"{n} · {esc(t)}" for t, n in top_tags]
    lines.append("\nYeni ilanlarda bu etiketlerden 13 tanesini seç (Etsy en fazla 13 etiket alıyor).")
    telegram.send("\n".join(lines))
    return {"measure": m, "tags": top_tags}


# ---------------- 3. rank tracker ----------------

def _keyword(title):
    """2-4 meaningful words from the first clause of our title: the phrase a buyer would type."""
    head = re.split(r"[|,–—]| - ", etsy.html_unescape(title or ""), maxsplit=1)[0]
    words = [w for w in re.split(r"[^a-zA-Z0-9']+", head.lower()) if w and w not in RANK_STOP and len(w) > 1]
    return " ".join(words[:4])


def search_rank(keyword, listing_id):
    res = etsy.search_active(keyword, limit=SAMPLE)
    for i, r in enumerate(res.get("results", []) or [], 1):
        if int(r.get("listing_id", 0)) == int(listing_id):
            return i, int(res.get("count", 0))
    return None, int(res.get("count", 0))


def ranks(only_listing=None):
    listings = etsy.shop_listings("active")
    if only_listing:
        listings = [x for x in listings if str(x.get("listing_id")) == str(only_listing)]
        if not listings:
            telegram.send(f"⚠️ {esc(str(only_listing))} numaralı aktif ilan bulunamadı.")
            return None
    if len(listings) > 5:
        telegram.send(f"📊 {len(listings)} ilanın sırası ölçülüyor, ~{max(1, len(listings) // 40)} dk sürer...")
    meta = storage.load_meta()
    old = meta.get("ranks", {})
    rows = []
    for x in listings:
        lid = str(x["listing_id"])
        kw = _keyword(x.get("title", ""))
        if not kw:
            continue
        try:
            rank, total = search_rank(kw, lid)
        except Exception as e:
            print(f"[sira] {lid} ölçülemedi: {e}")
            continue
        prev = (old.get(lid) or {}).get("rank")
        rows.append({"id": lid, "kw": kw, "rank": rank, "total": total, "prev": prev,
                     "title": etsy.html_unescape(x.get("title", ""))})
        time.sleep(PAUSE)
    meta["ranks"] = {r["id"]: {"kw": r["kw"], "rank": r["rank"], "at": int(time.time())} for r in rows}
    meta["ranks_prev"] = old
    storage.save_meta(meta)

    def move(r):
        if r["prev"] is None and r["rank"] is None:
            return ""
        if r["prev"] is None:
            return " 🆕"
        if r["rank"] is None:
            return f" ⬇️ (önce #{r['prev']})"
        d = r["prev"] - r["rank"]
        return f" ⬆️{d}" if d > 0 else (f" ⬇️{-d}" if d < 0 else "")

    found = sorted([r for r in rows if r["rank"]], key=lambda r: r["rank"])
    buried = [r for r in rows if not r["rank"]]
    lines = [f"📊 <b>Arama sırası</b>: {len(rows)} ilandan {len(found)} tanesi kendi aramasında ilk 100'de.",
             "<i>Etsy'nin genel sıralamasıyla ölçülür; alıcıya göre değişen kişisel sıralama değildir.</i>\n"]
    if found:
        lines.append("<b>İlk 100'de olanlar</b>")
        lines += [f"#{r['rank']}{move(r)} · {esc(r['kw'])} · {r['total']:,} rakip · <code>{r['id']}</code>"
                  for r in found[:25]]
    if buried:
        lines.append(f"\n<b>Gömülü kalanlar</b> (ilk 100'de değil, {len(buried)} ilan). İlk 15:")
        lines += [f"{esc(r['kw'])} · {r['total']:,} rakip{move(r)} · <code>{r['id']}</code>" for r in buried[:15]]
        lines.append("\nGömülü ilanlarda genelde sorun ya çok kalabalık arama ya da zayıf kapak/başlık. "
                     "Rakibi az olanlardan başlamak en hızlı sonucu verir.")
    telegram.send("\n".join(lines))
    return rows
