"""Read-only shop reports for Telegram (nothing on Etsy is changed):

/seo        every active listing scored out of 100 against Etsy's limits and how Etsy search reads a listing,
            weakest first, plus listings of ours that compete with each other for the same searches
/kar [AY]   the month's revenue, Etsy fees (from the payment-account ledger) and net, in USD and TL

Adapted from etsyotomasyon (MIT License, Copyright (c) 2026 etsyotomasyon contributors,
https://github.com/wj-sidiss/etsy-otomasyon-full-full-surum): seo.py audit_listing / audit_shop and
web/api/profit.py receipt_money / classify_ledger.
"""
import datetime as dt
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter

import requests

from . import etsy, telegram
from .telegram import esc

MAX_TITLE, MAX_TAGS, MAX_TAG_LEN = 140, 13, 20
VISIBLE = 40            # Etsy cuts titles in search results around here
DESC_MIN = 160
PHOTOS_MIN, PHOTOS_GOOD, MAIN_EDGE = 5, 10, 2000
SHARED_MIN, SHARED_WARN = 7, 9
WEIGHT = {"error": 25, "warn": 10, "info": 3}
STOP = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or",
        "that", "the", "this", "to", "with", "your", "you", "my", "our", "can", "will", "not", "but", "all"}
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?|\d+", re.UNICODE)


def _content(text):
    return [w.lower() for w in _WORD.findall(text or "") if w.lower() not in STOP and len(w) > 2]


# ---------------- SEO audit ----------------

def audit(listing, shared=None):
    """[(severity, Turkish message)] for one listing."""
    title = etsy.html_unescape(listing.get("title") or "").strip()
    desc = (listing.get("description") or "").strip()
    tags = [t for t in (listing.get("tags") or []) if t]
    out = []
    add = lambda sev, msg: out.append((sev, msg))

    if not title:
        add("error", "başlık boş")
    else:
        if len(title) > MAX_TITLE:
            add("error", f"başlık {len(title)} karakter, Etsy en fazla {MAX_TITLE} alır")
        elif len(title) < 40:
            add("warn", f"başlık sadece {len(title)} karakter, daha az aramaya çıkar")
        head, tail = set(_content(title[:VISIBLE])), set(_content(title[VISIBLE:]))
        if tail and not head:
            add("warn", f"ilk {VISIBLE} karakterde anahtar kelime yok (alıcı aramada sadece orayı görür)")
        stuffed = [w for w, c in Counter(_content(title)).items() if c >= 3]
        if stuffed:
            add("warn", f"başlıkta 3+ kez tekrar eden kelime: {', '.join(sorted(stuffed))}")
    if not tags:
        add("error", "hiç etiket yok (13 ücretsiz arama hakkı boşta)")
    else:
        if len(tags) < MAX_TAGS:
            add("warn", f"{len(tags)}/13 etiket kullanılmış, {MAX_TAGS - len(tags)} yer boş")
        long_ = [t for t in tags if len(t) > MAX_TAG_LEN]
        if long_:
            add("error", f"20 karakteri geçen etiket: {', '.join(long_[:3])}")
        low = [t.lower().strip() for t in tags]
        dup = {t for t in low if low.count(t) > 1}
        if dup:
            add("error", f"aynı etiket iki kez: {', '.join(sorted(dup))}")
        near = [(a, b) for i, a in enumerate(low) for b in low[i + 1:]
                if a != b and (a.rstrip("s") == b.rstrip("s") or a.replace(" ", "") == b.replace(" ", ""))]
        if near:
            add("info", "neredeyse aynı etiketler birbirinin yerini yiyor: " + ", ".join(f"{a}/{b}" for a, b in near[:2]))
        single = [t for t in tags if len(t.split()) == 1]
        if len(single) / len(tags) > 0.6:
            add("warn", f"{len(single)}/{len(tags)} etiket tek kelime (çok kelimeli etiketlerde rekabet çok daha az)")
        tw = set(_content(title))
        orphans = [t for t in tags if not (set(_content(t)) & tw)]
        if title and len(orphans) > len(tags) / 2:
            add("warn", f"{len(orphans)} etiket başlıkla hiç kelime paylaşmıyor (Etsy ikisi birbirini destekleyince üste çıkarır)")
        if shared:
            other, n = shared
            add("warn" if n >= SHARED_WARN else "info",
                f"{n} etiketi {other} numaralı ilanımızla aynı: Etsy aynı aramada bir mağazadan genelde tek ilan gösterir")
    if not desc:
        add("error", "açıklama boş")
    elif len(desc) < DESC_MIN:
        add("warn", f"açıklama sadece {len(desc)} karakter")
    elif title and not (set(_content(desc[:DESC_MIN])) & set(_content(title))):
        add("info", "açıklamanın ilk satırları başlıktaki kelimeleri içermiyor (Google o kısmı gösterir)")
    imgs = listing.get("images")
    if isinstance(imgs, list):
        if len(imgs) < PHOTOS_MIN:
            add("warn", f"sadece {len(imgs)} fotoğraf (10 ve üstü daha çok satar)")
        elif len(imgs) < PHOTOS_GOOD:
            add("info", f"{len(imgs)} fotoğraf, 10 ve üstü daha çok satar")
        no_alt = [i for i in imgs if not str(i.get("alt_text") or "").strip()]
        if imgs and no_alt:
            add("info", f"{len(no_alt)}/{len(imgs)} fotoğrafta açıklama (alt text) yok")
        if imgs:
            edge = min(imgs[0].get("full_width") or 0, imgs[0].get("full_height") or 0)
            if edge and edge < MAIN_EDGE:
                add("info", f"ana fotoğraf {imgs[0].get('full_width')}x{imgs[0].get('full_height')} px, Etsy en az 2000 px öneriyor")
    if listing.get("should_auto_renew") is False:
        add("info", "otomatik yenileme kapalı, ilan 4 ay sonra yayından kalkar")
    return out


def score(issues):
    return max(0, 100 - sum(WEIGHT[s] for s, _ in issues))


def _shared_tags(listings):
    per = {int(x["listing_id"]): {t.strip().lower() for t in x.get("tags") or [] if t.strip()} for x in listings}
    found = {}
    for lid, tags in per.items():
        if len(tags) < SHARED_MIN:
            continue
        best = None
        for other, ot in per.items():
            if other == lid:
                continue
            n = len(tags & ot)
            if n >= SHARED_MIN and (best is None or n > best[1]):
                best = (other, n)
        if best:
            found[lid] = best
    return found


def _listings_with_images():
    tok = etsy.token()
    out, offset = [], 0
    while True:
        res = etsy._req("GET", f"/shops/{tok['shop_id']}/listings", tok,
                        params={"state": "active", "limit": 100, "offset": offset, "includes": "Images"})
        out += res.get("results", [])
        offset += 100
        if offset >= res.get("count", 0) or not res.get("results"):
            return out


def seo_report(top=10):
    listings = _listings_with_images()
    if not listings:
        telegram.send("⚠️ Aktif ilan bulunamadı.")
        return None
    shared = _shared_tags(listings)
    rows = []
    for x in listings:
        lid = int(x["listing_id"])
        iss = audit(x, shared.get(lid))
        rows.append((score(iss), lid, etsy.html_unescape(x.get("title", "")), iss))
    rows.sort(key=lambda r: r[0])
    avg = sum(r[0] for r in rows) / len(rows)
    good = sum(1 for r in rows if r[0] >= 85)
    lines = [f"🔍 <b>SEO denetimi</b>: {len(rows)} aktif ilan, ortalama puan <b>{avg:.0f}/100</b>",
             f"İyi (85+): {good} · Orta (60-84): {sum(1 for r in rows if 60 <= r[0] < 85)} · Zayıf: {sum(1 for r in rows if r[0] < 60)}",
             f"Birbiriyle yarışan ilan: {len(shared)}\n",
             f"<b>En zayıf {min(top, len(rows))} ilan</b>"]
    for sc, lid, title, iss in rows[:top]:
        main = [m for s, m in iss if s != "info"][:3] or [m for _, m in iss][:2]
        lines.append(f"\n<b>{sc}</b> · {esc(title[:60])} · <code>{lid}</code>")
        lines += [f"  • {esc(m)}" for m in main]
    lines.append("\n<i>Sadece rapor; hiçbir ilan değiştirilmedi.</i>")
    telegram.send("\n".join(lines)[:4000])
    return rows


# ---------------- profit ----------------

LEDGER_RULES = (
    (r"label|postage", "kargo etiketi"),
    (r"sales[ _-]?tax|vat[ _-]?tax|tax[ _-]?remit|remittance|marketplace[ _-]?tax", None),
    (r"prolist|promoted|offsite|\bads?\b|_ads?\b|\bads?_|advert", "reklam"),
    (r"processing|payment[ _-]?fee|card[ _-]?fee|cc[ _-]?fee", "ödeme işlem"),
    (r"transaction", "satış komisyonu"),
    (r"listing|renew", "ilan ücreti"),
    (r"fee|vat|subscription|plus|pattern|regulatory|conversion", "diğer"),
    (r"payment|refund|disburse|deposit|reserve|recoup|payout|credit|sale\b|sales\b|bill", None),
)
_RULES = [(re.compile(p), b) for p, b in LEDGER_RULES]
_CREDIT = re.compile(r"refund|credit|revers|return|fee|void|adjust")


def classify(entry):
    text = " ".join(str(entry.get(f) or "") for f in ("ledger_type", "description")).lower()
    for pat, bucket in _RULES:
        if pat.search(text):
            return bucket
    amt = entry.get("amount")
    return "diğer" if isinstance(amt, (int, float)) and amt < 0 else None


def _money(m):
    if not isinstance(m, dict) or m.get("amount") is None:
        return 0.0
    return int(m["amount"]) / int(m.get("divisor") or 100)


def receipt_revenue(r):
    """Items + shipping + gift wrap - refunds (tax is not revenue). Cancelled / fully refunded = 0."""
    status = str(r.get("status") or "").lower()
    if status in ("canceled", "fully refunded"):
        return 0.0
    base = _money(r.get("subtotal")) + _money(r.get("total_shipping_cost")) + _money(r.get("gift_wrap_price"))
    tax = _money(r.get("total_tax_cost")) + _money(r.get("total_vat_cost"))
    refunds = sum(_money(x.get("amount")) for x in r.get("refunds") or []
                  if str(x.get("status") or "").lower() not in ("failed", "canceled", "cancelled"))
    gross = base + tax
    refunded_tax = min(tax, refunds * tax / gross) if gross > 0 and tax > 0 else 0.0
    return base - min(max(base, 0.0), max(refunds - refunded_tax, 0.0))


def _paged(path, tok, params):
    out, offset = [], 0
    while True:
        res = etsy._req("GET", path, tok, params={**params, "limit": 100, "offset": offset})
        out += res.get("results", [])
        offset += 100
        if offset >= res.get("count", 0) or not res.get("results") or offset >= 5000:
            return out
        time.sleep(0.2)


def usd_try():
    try:
        r = requests.get("https://www.tcmb.gov.tr/kurlar/today.xml", timeout=8)
        for c in ET.fromstring(r.content).findall("Currency"):
            if c.get("CurrencyCode") == "USD":
                return float(c.findtext("ForexSelling"))
    except Exception as e:
        print(f"[kar] TCMB kuru alınamadı: {e}")
    return None


def profit_report(month=None):
    now = dt.datetime.now(dt.timezone.utc)
    if month:
        m = re.match(r"^(\d{4})-(\d{1,2})$", month.strip())
        if not m:
            telegram.send("Kullanım: <code>/kar</code> (bu ay) veya <code>/kar 2026-10</code>")
            return None
        y, mo = int(m.group(1)), int(m.group(2))
    else:
        y, mo = now.year, now.month
    start = dt.datetime(y, mo, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=dt.timezone.utc)
    lo, hi = int(start.timestamp()), int(min(end, now).timestamp())
    tok = etsy.token()
    sid = tok["shop_id"]
    receipts = _paged(f"/shops/{sid}/receipts", tok, {"min_created": lo, "max_created": hi, "was_paid": "true"})
    revenue = sum(receipt_revenue(r) for r in receipts)
    orders = sum(1 for r in receipts if str(r.get("status") or "").lower() not in ("canceled", "fully refunded"))
    fees, ledger_ok = Counter(), True
    rate = usd_try()
    other_cur = set()
    try:
        for e in _paged(f"/shops/{sid}/payment-account/ledger-entries", tok, {"min_created": lo, "max_created": hi}):
            b = classify(e)
            amt = e.get("amount")
            if not b or not isinstance(amt, (int, float)):
                continue
            text = f"{e.get('ledger_type', '')} {e.get('description', '')}".lower()
            if amt > 0 and not _CREDIT.search(text):
                continue
            cur = str(e.get("currency") or "USD").upper()
            value = -amt / 100.0
            if cur == "TRY" and rate:
                value /= rate  # a Turkish payment account keeps its ledger in TL
            elif cur not in ("USD", "TRY"):
                other_cur.add(cur)
            fees[b] += value
    except Exception as e:
        ledger_ok = False
        print(f"[kar] ödeme defteri okunamadı: {e}")
        fees["tahmini (satış %6.5 + ödeme %3 + 0.25$ + 0.20$)"] = revenue * 0.095 + orders * 0.45
    total_fees = sum(fees.values())
    net = revenue - total_fees
    tl = lambda v: f" ({v * rate:,.0f} TL)" if rate else ""
    lines = [f"💰 <b>Kâr-Zarar {y}-{mo:02d}</b>" + (" (ay devam ediyor)" if end > now else ""),
             f"Sipariş: <b>{orders}</b>",
             f"Gelir: <b>${revenue:,.2f}</b>{tl(revenue)}",
             f"Etsy kesintileri: <b>${total_fees:,.2f}</b>{tl(total_fees)}"]
    lines += [f"  • {k}: ${v:,.2f}" for k, v in fees.most_common() if abs(v) >= 0.005]
    lines.append(f"Net: <b>${net:,.2f}</b>{tl(net)}")
    if orders:
        lines.append(f"Sipariş başı net: ${net / orders:,.2f}")
    if not ledger_ok:
        lines.append("\n<i>Etsy ödeme defteri okunamadı, kesintiler standart oranlarla tahmin edildi.</i>")
    if other_cur:
        lines.append(f"<i>Bazı kesintiler {', '.join(sorted(other_cur))} cinsinden, dolara çevrilmedi.</i>")
    if rate:
        lines.append(f"<i>Kur: 1$ = {rate:.2f} TL (TCMB bugün)</i>")
    lines.append("<i>Vergi gelire dahil değil. İade edilen siparişler düşüldü.</i>")
    telegram.send("\n".join(lines))
    return {"revenue": revenue, "fees": dict(fees), "net": net, "orders": orders}
