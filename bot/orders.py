"""Personalized orders: when someone buys a "custom" listing, the bot writes the buyer's name into the designs and
sends the finished files to Telegram. The shop owner then uploads them to the order in the Etsy app."""
import re
import time

from . import etsy, storage, telegram
from .telegram import esc

MADE_TO_ORDER = ("custom", "tattoo")  # product types whose files are made per order from the buyer's text


def _module(p):
    from .products import TYPES
    return TYPES[p["type"]]


def _personalization(t):
    for v in t.get("variations") or []:
        if "ersonali" in (v.get("formatted_name") or "") or "ersonali" in str(v.get("property_id", "")):
            return (v.get("formatted_value") or "").strip()
    return (t.get("personalization") or "").strip()


def check() -> bool:
    customs = {str(p["etsy"]["listing_id"]): p for p in storage.all_products()
               if p.get("type") in MADE_TO_ORDER and p.get("etsy", {}).get("listing_id")}
    if not customs:
        return False
    meta = storage.load_meta()
    done = set(meta.get("custom_done", []))
    since = int(meta.get("custom_since") or time.time() - 7 * 86400)
    tok = etsy.token()
    shop_id = tok.get("shop_id") or etsy.get_shop(tok)["shop_id"]
    res = etsy._req("GET", f"/shops/{shop_id}/receipts", tok,
                    params={"was_paid": "true", "min_created": since, "limit": 50})
    changed = False
    for r in res.get("results", []):
        for t in r.get("transactions", []):
            tid, lid = str(t.get("transaction_id")), str(t.get("listing_id"))
            if tid in done or lid not in customs:
                continue
            p = customs[lid]
            name = _personalization(t)
            buyer = r.get("name") or "alıcı"
            if not name:
                telegram.send(f"⚠️ Kişiye özel sipariş #{r['receipt_id']} ({esc(buyer)}): isim yazılmamış. "
                              "Etsy'den alıcıya mesaj atıp ismi sor, sonra Telegram'a "
                              f"<code>/ozel {r['receipt_id']} İsim</code> yaz.")
                done.add(tid)
                changed = True
                continue
            _send(p, name, r["receipt_id"], buyer)
            done.add(tid)
            changed = True
    meta["custom_done"] = sorted(done)[-1000:]
    meta["custom_since"] = int(time.time()) - 2 * 86400
    storage.save_meta(meta)
    return changed


def _send(p, name, receipt_id, buyer=""):
    from .imgutil import make_zips
    try:
        files = _module(p).render(p, name)
    except ValueError as e:
        telegram.send(f"⚠️ Kişiye özel sipariş #{receipt_id} ({esc(buyer)}): {esc(str(e))} (yazılan: <code>{esc(name)}</code>). "
                      "Etsy'den alıcıya mesaj atıp sor, sonra Telegram'a "
                      f"<code>/ozel {receipt_id} Doğru metin</code> yaz.")
        return
    if not files:
        telegram.send(f"⚠️ #{receipt_id}: tasarım çizimleri bulunamadı, dosya hazırlanamadı.")
        return
    safe = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "name"
    zips = make_zips(f"{safe}-{receipt_id}", files,
                     f"Your personalized design for: {name}\nThank you for your order!\n")
    telegram.send(f"📦 <b>Yeni kişiye özel sipariş</b> #{receipt_id}\n👤 {esc(buyer)}\n✏️ İsim: <b>{esc(name)}</b>\n"
                  f"🛍 {esc(p['title'][:70])}\n\n"
                  "Aşağıdaki ZIP'i Etsy uygulamasında bu siparişe yükle:\n"
                  "Shop Manager → Orders → sipariş → <b>Upload files</b> (digital) → Complete order.\n"
                  "Etsy kuralı: en geç 3 gün içinde (biz 24 saat dedik).")
    for zn, data in zips:
        telegram.document(zn, data, caption=f"#{receipt_id} · {esc(name)}")


def manual(arg) -> bool:
    """/ozel <receipt_id or listing_id> <name>: make the files by hand (e.g. the buyer sent the name by message)."""
    parts = arg.split(maxsplit=1)
    if len(parts) < 2:
        telegram.send("Kullanım: <code>/ozel &lt;sipariş no&gt; İsim</code>  (ör. /ozel 3456789012 Mrs. Johnson)")
        return False
    key, name = parts
    customs = [p for p in storage.all_products() if p.get("type") in MADE_TO_ORDER and p.get("etsy", {}).get("listing_id")]
    p = next((q for q in customs if str(q["etsy"]["listing_id"]) == key or q["id"] == key), None)
    if p is None:
        try:
            tok = etsy.token()
            shop_id = tok.get("shop_id") or etsy.get_shop(tok)["shop_id"]
            r = etsy._req("GET", f"/shops/{shop_id}/receipts/{key}", tok)
            lids = {str(t.get("listing_id")) for t in r.get("transactions", [])}
            p = next((q for q in customs if str(q["etsy"]["listing_id"]) in lids), None)
        except Exception as e:
            print(f"[orders] sipariş okunamadı: {e}")
    if p is None and len(customs) == 1:
        p = customs[0]
    if p is None:
        telegram.send("Bu siparişte kişiye özel ürün bulunamadı.")
        return False
    _send(p, name, key)
    return False
