"""Etsy Open API v3: OAuth 2.0 (PKCE), shop info, public search, listing publishing."""
import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse

import requests

from . import config, storage

API = "https://openapi.etsy.com/v3/application"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
SCOPES = "listings_w listings_r listings_d shops_r shops_w transactions_r"


class EtsyError(Exception):
    pass


def _api_key():
    if not (config.ETSY_KEYSTRING and config.ETSY_SHARED_SECRET):
        raise EtsyError("ETSY_KEYSTRING / ETSY_SHARED_SECRET tanımlı değil")
    return f"{config.ETSY_KEYSTRING}:{config.ETSY_SHARED_SECRET}"


# ---------------- OAuth ----------------

def _verifier(state: str) -> str:
    # derive the PKCE verifier from the state so nothing has to be stored between steps
    digest = hmac.new(config.STATE_KEY.encode(), ("etsy-pkce:" + state).encode(), hashlib.sha256).digest()
    digest += hmac.new(config.STATE_KEY.encode(), ("etsy-pkce2:" + state).encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:64]


def auth_url() -> str:
    redirect = config.etsy_redirect_uri()
    if not redirect:
        raise EtsyError("Yönlendirme adresi (callback) belirlenemedi")
    state = secrets.token_hex(12)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(_verifier(state).encode()).digest()).decode().rstrip("=")
    q = {
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": SCOPES,
        "client_id": config.ETSY_KEYSTRING,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return "https://www.etsy.com/oauth/connect?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def exchange(callback_url_or_code: str, state: str = None) -> dict:
    text = callback_url_or_code.strip()
    if "code=" in text:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(text).query)
        if "error" in qs:
            raise EtsyError(f"Etsy izin vermedi: {qs.get('error_description', qs['error'])[0]}")
        code = qs["code"][0]
        state = qs.get("state", [state])[0]
    else:
        code = text
    if not state:
        raise EtsyError("Bağlantı adresinde 'state' yok. Lütfen adres çubuğundaki adresin tamamını kopyalayın.")
    r = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": config.ETSY_KEYSTRING,
        "redirect_uri": config.etsy_redirect_uri(),
        "code": code,
        "code_verifier": _verifier(state),
    }, timeout=30)
    if r.status_code != 200:
        raise EtsyError(f"Etsy jetonu alınamadı: HTTP {r.status_code} {r.text[:300]}")
    tok = _store_token(r.json(), {})
    shop = get_shop(tok)
    tok.update({"shop_id": shop["shop_id"], "shop_name": shop.get("shop_name"), "shop_url": shop.get("url"),
                "currency": shop.get("currency_code", "USD")})
    storage.save_etsy(tok)
    return tok


def _store_token(data: dict, old: dict) -> dict:
    tok = dict(old)
    tok["access_token"] = data["access_token"]
    if data.get("refresh_token"):
        tok["refresh_token"] = data["refresh_token"]
        tok["refreshed_at"] = int(time.time())
    tok["expires_at"] = int(time.time()) + int(data.get("expires_in", 3600)) - 120
    tok["user_id"] = data["access_token"].split(".")[0]
    storage.save_etsy(tok)
    return tok


def token(force_refresh=False) -> dict:
    tok = storage.load_etsy()
    if not tok.get("refresh_token"):
        raise EtsyError("Etsy bağlı değil. Telegram'da /etsy yazarak bağlayın.")
    if force_refresh or time.time() >= tok.get("expires_at", 0):
        r = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": config.ETSY_KEYSTRING,
            "refresh_token": tok["refresh_token"],
        }, timeout=30)
        if r.status_code != 200:
            raise EtsyError(f"Etsy oturumu yenilenemedi (yeniden /etsy ile bağlayın): HTTP {r.status_code} {r.text[:200]}")
        tok = _store_token(r.json(), tok)
    return tok


def keepalive() -> bool:
    """Refresh tokens every few days so the 90-day refresh token never expires."""
    tok = storage.load_etsy()
    if tok.get("refresh_token") and time.time() - tok.get("refreshed_at", 0) > 5 * 86400:
        token(force_refresh=True)
        return True
    return False


def _req(method, path, tok=None, **kw):
    headers = kw.pop("headers", {})
    headers["x-api-key"] = _api_key()
    if tok:
        headers["Authorization"] = f"Bearer {tok['access_token']}"
    timeout = kw.pop("timeout", 120)
    for attempt in range(4):
        r = requests.request(method, API + path, headers=headers, timeout=timeout, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 415 and "json" in kw:
            # endpoint wants form encoding
            body = kw.pop("json")
            kw["data"] = {k: (",".join(v) if isinstance(v, list) else str(v).lower() if isinstance(v, bool) else v)
                          for k, v in body.items()}
            continue
        break
    if r.status_code >= 400:
        raise EtsyError(f"{method} {path}: HTTP {r.status_code} {r.text[:400]}")
    return r.json() if r.content else {}


def get_shop(tok=None) -> dict:
    tok = tok or token()
    return _req("GET", f"/users/{tok['user_id']}/shops", tok)


# ---------------- public market data ----------------

def search_active(keywords: str, limit=25) -> dict:
    return _req("GET", "/listings/active", params={
        "keywords": keywords, "limit": limit, "sort_on": "score", "sort_order": "desc",
    }, timeout=30)


_TAXONOMY = None


# Categories that the best-selling competitors use (checked on Etsy, Nov 2026).
# A name can be a leaf name ("Coloring Books") or a path suffix ("Paper > Scrapbooking Ephemera").
TAXONOMY_BY_TYPE = {
    "junk_journal": ["Paper > Scrapbooking Ephemera", "Clip Art & Image Files"],
    "pattern": ["Paper > Decorative Paper", "Clip Art & Image Files"],
    "wallpaper": ["Drawing & Illustration > Digital", "Digital Prints"],
    "planner": ["Templates > Planner Templates", "Planner Templates"],
    "stickers": ["Paper > Stickers", "Stickers", "Clip Art & Image Files"],
    "sublimation": ["Clip Art & Image Files", "Digital Prints"],
    "custom": ["Clip Art & Image Files", "Digital Prints"],
    "tattoo": ["Digital Prints", "Drawing & Illustration"],
    "journal": ["Templates > Planner Templates", "Planner Templates", "Calendars & Planners"],
    "coloring": ["Books > Coloring Books", "Digital Prints"],
    "clipart": ["Clip Art & Image Files"],
    "scenes": ["Clip Art & Image Files"],
    "tumbler": ["Clip Art & Image Files"],
    "wall_art": ["Prints > Digital Prints"],
}


def _taxonomy_paths():
    """[(lowercase 'a > b > c' path, id, is_leaf)] for every Etsy seller category."""
    global _TAXONOMY
    if _TAXONOMY is None:
        nodes = _req("GET", "/seller-taxonomy/nodes").get("results", [])
        flat = []

        def walk(ns, parents):
            for n in ns:
                path = parents + [n["name"].strip().lower()]
                flat.append((" > ".join(path), n["id"], not n.get("children")))
                walk(n.get("children") or [], path)
        walk(nodes, [])
        _TAXONOMY = flat
    return _TAXONOMY


def taxonomy_id(names: list, fallback: int) -> int:
    try:
        paths = _taxonomy_paths()
        for name in names:
            want = " > ".join(x.strip() for x in name.lower().split(">"))
            hits = [(leaf, pid) for path, pid, leaf in paths if path == want or path.endswith(" > " + want)]
            if hits:
                hits.sort(key=lambda h: not h[0])  # leaf categories first
                return hits[0][1]
    except Exception as e:
        print(f"[etsy] kategori listesi alınamadı: {e}")
    return fallback


def taxonomy_for(ptype: str, build_meta: dict) -> int:
    names = TAXONOMY_BY_TYPE.get(ptype or "") or build_meta.get("taxonomy", [])
    return taxonomy_id(names, build_meta.get("taxonomy_fallback_id", 2078))


_SMALL = {"a", "an", "and", "or", "the", "of", "for", "with", "in", "on", "to", "by", "at"}


def nice_title(title: str) -> str:
    """'cute penguin clipart bundle' -> 'Cute Penguin Clipart Bundle'. Titles that already use capitals are kept."""
    t = " ".join((title or "").split())
    words = t.split(" ")
    if not t or sum(w[:1].isupper() for w in words) >= max(2, len(words) // 2):
        return t
    out = []
    for i, w in enumerate(words):
        if i and w.lower() in _SMALL:
            out.append(w.lower())
        elif w[:1].islower():
            out.append(w[:1].upper() + w[1:])
        else:
            out.append(w)
    return " ".join(out)


# ---------------- publishing ----------------

_FX = {}


def usd_to(currency: str, usd: float) -> float:
    currency = (currency or "USD").upper()
    if currency == "USD":
        return round(usd, 2)
    if currency not in _FX:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=30)
        r.raise_for_status()
        _FX.update(r.json()["rates"])
    v = usd * float(_FX[currency])
    # friendly price ending in .99 (or whole numbers for big currencies)
    if v >= 100:
        return float(int(v)) + 0.99 if currency not in ("JPY", "KRW") else float(round(v))
    return round(int(v) + 0.99 if v >= 2 else v, 2)


def _clean_tags(tags):
    out, seen = [], set()
    for t in tags:
        t = "".join(c for c in str(t) if c.isalnum() or c in " -'").strip()[:20].strip()
        if t and t.lower() not in seen:
            out.append(t)
            seen.add(t.lower())
    return out[:13]


def _clean_styles(styles):
    """Etsy 'styles': up to 2 short style words (e.g. Vintage, Watercolor) that also count in search."""
    out = []
    for st in styles or []:
        st = "".join(c for c in str(st) if c.isalnum() or c == " ").strip()[:45]
        if st and st.lower() not in [o.lower() for o in out]:
            out.append(st)
    return out[:2]


_ALT = {"bundle": "bundle cover with all items", "cover": "cover preview", "mosaic": "all designs included", "all": "all designs included",
        "wall": "framed on a wall", "room": "shown in a room", "lifestyle": "printed page on a desk",
        "info": "what is included", "sizes": "included sizes", "example": "colored example", "page": "page preview",
        "detail": "close-up detail", "how": "how to download", "print": "print preview", "flatlay": "all prints together"}


def _alt_text(title, photo_name):
    key = "".join(c for c in photo_name.lower().rsplit(".", 1)[0] if c.isalpha())
    label = next((v for k, v in _ALT.items() if key.startswith(k)), "preview")
    return f"{title} - {label}"[:250]


SECTIONS = {"scenes": "Illustration Packs", "wall_art": "Printable Wall Art",
            "wallpaper": "Phone Wallpapers", "coloring": "Coloring Pages",
            "clipart": "Clipart", "pattern": "Digital Paper", "tumbler": "Tumbler Wraps",
            "junk_journal": "Junk Journal Kits", "planner": "Digital Planners", "stickers": "Digital Stickers",
            "journal": "Printable Journal Pages", "sublimation": "Sublimation PNG Designs",
            "custom": "Custom Name PNG", "tattoo": "Custom Tattoo Designs"}


def section_for(ptype, tok, shop_id):
    """Shop section for a product type (created once when missing). None if anything fails."""
    title = SECTIONS.get(ptype or "")
    if not title:
        return None
    try:
        for sec in _req("GET", f"/shops/{shop_id}/sections", tok).get("results", []):
            if (sec.get("title") or "").strip().lower() == title.lower():
                return sec["shop_section_id"]
        res = _req("POST", f"/shops/{shop_id}/sections", tok, data={"title": title})
        return res.get("shop_section_id")
    except Exception as e:
        print(f"[etsy] mağaza bölümü ayarlanamadı: {e}")
        return None


def _when_made():
    y = time.gmtime().tm_year
    return f"{y - y % 10}_{y}" if y % 10 else "made_to_order"


def _create(shop_id, tok, data):
    try:
        return _req("POST", f"/shops/{shop_id}/listings", tok, json=data)
    except EtsyError as e:
        if "HTTP 415" not in str(e) and "content type" not in str(e).lower():
            raise
    form = {k: (",".join(v) if isinstance(v, list) else str(v).lower() if isinstance(v, bool) else v) for k, v in data.items()}
    return _req("POST", f"/shops/{shop_id}/listings", tok, data=form)


import re as _re

_TEXT_WORDS = _re.compile(r"\b(quotes?|sayings?|typography|lettering|affirmations?)\b", _re.I)


def _strip_text_claims(p: dict) -> dict:
    """Our artwork never contains text. If the AI used words like 'quote' in the title/tags,
    remove them so the listing does not promise text, and add a short clarification."""
    hay = f"{p.get('title', '')} {p.get('niche', '')} {' '.join(p.get('tags', []))}"
    if not _TEXT_WORDS.search(hay):
        return p
    q = dict(p)
    t = _TEXT_WORDS.sub("", q["title"])
    t = _re.sub(r"\s{2,}", " ", t)
    t = _re.sub(r"\s+([,|])", r"\1", t)
    t = _re.sub(r"([,|])\s*([,|])", r"\1", t).strip(" ,|-")
    q["title"] = t
    q["tags"] = [x for x in (_re.sub(r"\s{2,}", " ", _TEXT_WORDS.sub("", tg)).strip() for tg in q.get("tags", [])) if len(x) >= 3]
    note = "Please note: these designs are artwork only and do not include any quotes or text."
    if note not in q.get("description", ""):
        q["description"] = q.get("description", "") + "\n\n" + note
    return q


def publish(p: dict, delivery: list, photos: list, build_meta: dict, mode="active", video=None) -> dict:
    """delivery: [(name, bytes)] files, photos: [(name, bytes)] jpgs. Returns {listing_id, url, state}."""
    p = _strip_text_claims(p)
    tok = token()
    shop_id = tok.get("shop_id") or get_shop(tok)["shop_id"]
    price = round(float(p["price_usd"]), 2)
    data = {
        "quantity": 999,
        "title": nice_title(p["title"])[:140],
        "description": p["description"],
        "price": price,
        "who_made": "i_did",
        "when_made": _when_made(),
        "taxonomy_id": taxonomy_for(p.get("type"), build_meta),
        "type": "download",
        "is_supply": bool(build_meta.get("is_supply")),
        "tags": _clean_tags(p.get("tags", [])),
        "should_auto_renew": True,
    }
    styles = _clean_styles(p.get("styles") or p.get("spec", {}).get("styles"))
    if styles:
        data["styles"] = styles
    sec = config.settings().get("shop_section_id") or section_for(p.get("type"), tok, shop_id)
    if sec:
        data["shop_section_id"] = sec
    data.update(build_meta.get("listing", {}))  # e.g. personalization for made-to-order custom PNGs
    listing_id = p.get("etsy", {}).get("listing_id")
    if not listing_id:
        try:
            res = _create(shop_id, tok, data)
        except EtsyError as e:
            if "personaliz" in str(e).lower() and build_meta.get("listing"):
                print(f"[etsy] kişiselleştirme alanı reddedildi, ilan alansız açılıyor (Etsy'den elle aç): {e}")
                for k in build_meta["listing"]:
                    data.pop(k, None)
                res = _create(shop_id, tok, data)
            elif "when_made" in str(e):
                data["when_made"] = "made_to_order"
                res = _create(shop_id, tok, data)
            elif "styles" in str(e).lower() and "styles" in data:
                data.pop("styles")
                res = _create(shop_id, tok, data)
            else:
                raise
        listing_id = res["listing_id"]
        p.setdefault("etsy", {})["listing_id"] = listing_id
        storage.save_product(p)
    lid = listing_id
    existing = _req("GET", f"/listings/{lid}/images", tok).get("count", 0)
    if not existing:
        for rank, (name, data_bytes) in enumerate(photos[:10], 1):
            _req("POST", f"/shops/{shop_id}/listings/{lid}/images", tok,
                 files={"image": (name, data_bytes, "image/jpeg")},
                 data={"rank": rank, "alt_text": _alt_text(p["title"], name)}, timeout=300)
    if video:
        try:
            try:
                have_video = _req("GET", f"/listings/{lid}/videos", tok).get("count", 0)
            except Exception:
                have_video = 0
            if not have_video:
                _req("POST", f"/shops/{shop_id}/listings/{lid}/videos", tok,
                     files={"video": ("video.mp4", video, "video/mp4")}, data={"name": "video.mp4"}, timeout=600)
        except Exception as e:
            print(f"[etsy] video yüklenemedi, devam: {e}")
    have_files = _req("GET", f"/shops/{shop_id}/listings/{lid}/files", tok).get("count", 0)
    if not have_files:
        for rank, (name, data_bytes) in enumerate(delivery[:5], 1):
            if len(data_bytes) > 20 * 1024 * 1024:
                raise EtsyError(f"{name} 20 MB'tan büyük")
            ctype = "application/pdf" if name.endswith(".pdf") else "application/zip"
            _req("POST", f"/shops/{shop_id}/listings/{lid}/files", tok,
                 files={"file": (name, data_bytes, ctype)}, data={"name": name, "rank": rank}, timeout=600)
    attrs = p.get("etsy", {}).get("attributes")
    if not attrs:
        from . import attributes
        attrs = attributes.fill(lambda m, path, **kw: _req(m, path, tok, **kw), shop_id, lid, data["taxonomy_id"], p,
                                skip=build_meta.get("skip_attributes", ()))
    state = "draft"
    if mode == "active":
        _req("PATCH", f"/shops/{shop_id}/listings/{lid}", tok, json={"state": "active"})
        state = "active"
    return {"listing_id": lid, "url": f"https://www.etsy.com/listing/{lid}", "state": state, "price": price,
            "currency": "USD", "attributes": attrs}


# ---------------- maintenance ----------------

def replace_main_image(listing_id, data: bytes, alt_text=""):
    """Swap the first listing photo for a new JPEG (delete old rank-1 photo, upload new as rank 1)."""
    tok = token()
    shop_id = tok.get("shop_id") or get_shop(tok)["shop_id"]
    imgs = _req("GET", f"/listings/{listing_id}/images", tok).get("results", [])
    imgs.sort(key=lambda i: i.get("rank", 99))
    if imgs:
        _req("DELETE", f"/shops/{shop_id}/listings/{listing_id}/images/{imgs[0]['listing_image_id']}", tok)
    _req("POST", f"/shops/{shop_id}/listings/{listing_id}/images", tok,
         files={"image": ("cover.jpg", data, "image/jpeg")}, data={"rank": 1, "alt_text": alt_text[:250]}, timeout=300)


def replace_all_images(listing_id, photos: list, title=""):
    """Swap every listing photo for new JPEGs [(name, bytes)] (max 10). Etsy keeps max 10, so: drop old 2..n,
    add new 2..n, then swap the first one; the listing is never left without a photo."""
    tok = token()
    shop_id = tok.get("shop_id") or get_shop(tok)["shop_id"]
    old = _req("GET", f"/listings/{listing_id}/images", tok).get("results", [])
    old.sort(key=lambda i: i.get("rank", 99))
    for im in old[1:]:
        _req("DELETE", f"/shops/{shop_id}/listings/{listing_id}/images/{im['listing_image_id']}", tok)
    for rank, (name, data) in enumerate(photos[1:10], 2):
        _req("POST", f"/shops/{shop_id}/listings/{listing_id}/images", tok,
             files={"image": (name, data, "image/jpeg")}, data={"rank": rank, "alt_text": _alt_text(title, name)}, timeout=300)
    if old:
        _req("DELETE", f"/shops/{shop_id}/listings/{listing_id}/images/{old[0]['listing_image_id']}", tok)
    name, data = photos[0]
    _req("POST", f"/shops/{shop_id}/listings/{listing_id}/images", tok,
         files={"image": (name, data, "image/jpeg")}, data={"rank": 1, "alt_text": _alt_text(title, name)}, timeout=300)


def replace_video(listing_id, video: bytes):
    """Swap the listing video for a new mp4 (Etsy keeps one video per listing)."""
    tok = token()
    shop_id = tok.get("shop_id") or get_shop(tok)["shop_id"]
    try:
        old = _req("GET", f"/listings/{listing_id}/videos", tok).get("results", [])
    except Exception:
        old = []
    for v in old:
        vid = v.get("video_id") or v.get("listing_video_id")
        if vid:
            _req("DELETE", f"/shops/{shop_id}/listings/{listing_id}/videos/{vid}", tok)
    _req("POST", f"/shops/{shop_id}/listings/{listing_id}/videos", tok,
         files={"video": ("video.mp4", video, "video/mp4")}, data={"name": "video.mp4"}, timeout=600)


def replace_files(listing_id, delivery: list):
    """Swap the digital files of a listing for new ones [(name, bytes)] (max 5 x 20 MB)."""
    for name, data in delivery:
        if len(data) > 20 * 1024 * 1024:
            raise EtsyError(f"{name} 20 MB'tan büyük")
    tok = token()
    shop_id = tok.get("shop_id") or get_shop(tok)["shop_id"]
    old = _req("GET", f"/shops/{shop_id}/listings/{listing_id}/files", tok).get("results", [])
    for f in old:
        _req("DELETE", f"/shops/{shop_id}/listings/{listing_id}/files/{f['listing_file_id']}", tok)
    for rank, (name, data) in enumerate(delivery[:5], 1):
        ctype = "application/pdf" if name.endswith(".pdf") else "application/zip"
        _req("POST", f"/shops/{shop_id}/listings/{listing_id}/files", tok,
             files={"file": (name, data, ctype)}, data={"name": name, "rank": rank}, timeout=600)


def update_listing(listing_id, **fields) -> dict:
    tok = token()
    shop_id = tok.get("shop_id") or get_shop(tok)["shop_id"]
    return _req("PATCH", f"/shops/{shop_id}/listings/{listing_id}", tok, json=fields)


_GUESS = [("tattoo", "tattoo"), ("custom", "custom"), ("personalized", "custom"), ("sublimation", "sublimation"), ("shirt design", "sublimation"), ("junk journal", "junk_journal"), ("sticker", "stickers"), ("bullet journal", "journal"),
          ("journal bundle", "journal"), ("planner", "planner"), ("wallpaper", "wallpaper"), ("lock screen", "wallpaper"),
          ("coloring", "coloring"), ("colouring", "coloring"), ("clipart", "clipart"), ("clip art", "clipart"),
          ("tumbler", "tumbler"), ("digital paper", "pattern"), ("wall art", "wall_art"), ("poster", "wall_art"),
          ("print", "wall_art"), ("illustration", "scenes")]


def fix_sections() -> dict:
    """Puts every active listing without a shop section into the section of its product type."""
    from . import storage
    tok = token()
    shop_id = tok.get("shop_id") or get_shop(tok)["shop_id"]
    by_id = {str(p.get("etsy", {}).get("listing_id")): p.get("type") for p in storage.all_products()}
    done, skipped, failed = {}, [], []
    for l in shop_listings():
        if l.get("shop_section_id"):
            continue
        lid = str(l["listing_id"])
        ptype = by_id.get(lid)
        if not ptype:
            t = (l.get("title") or "").lower()
            ptype = next((v for k, v in _GUESS if k in t), None)
        sec = section_for(ptype, tok, shop_id) if ptype else None
        if not sec:
            skipped.append(l.get("title", lid)[:50])
            continue
        try:
            _req("PATCH", f"/shops/{shop_id}/listings/{lid}", tok, json={"shop_section_id": sec})
            done[SECTIONS[ptype]] = done.get(SECTIONS[ptype], 0) + 1
        except Exception as e:
            failed.append(f"{lid}: {str(e)[:80]}")
    return {"done": done, "skipped": skipped, "failed": failed}


def shop_listings(state="active") -> list:
    tok = token()
    out, offset = [], 0
    while True:
        res = _req("GET", f"/shops/{tok['shop_id']}/listings", tok,
                   params={"state": state, "limit": 100, "offset": offset})
        out += res.get("results", [])
        offset += 100
        if offset >= res.get("count", 0) or not res.get("results"):
            return out


def _type_from_title(title: str):
    t = (title or "").lower()
    for words, ptype in ((("junk journal", "ephemera"), "junk_journal"), (("digital planner", "planner"), "planner"),
                         (("wallpaper", "lock screen", "lockscreen"), "wallpaper"),
                         (("digital paper", "seamless pattern", "scrapbook paper"), "pattern"),
                         (("coloring", "colouring"), "coloring"), (("tumbler",), "tumbler"),
                         (("wall art", "art print", "prints"), "wall_art"),
                         (("clipart", "clip art", "illustration pack", "scenes"), "clipart")):
        if any(w in t for w in words):
            return ptype
    return None


def fix_listings() -> list:
    """One-off repair of live listings: wrong category (e.g. junk journals in 'Digital Prints')
    and lower-case titles. Attributes are filled again for the new category. Returns change notes."""
    from . import attributes
    tok = token()
    shop_id = tok["shop_id"]
    by_lid = {str(p.get("etsy", {}).get("listing_id")): p for p in storage.all_products() if p.get("etsy", {}).get("listing_id")}
    notes = []
    for state in ("active", "draft"):
        try:
            listings = shop_listings(state)
        except Exception as e:
            print(f"[etsy] {state} ilanlar alınamadı: {e}")
            continue
        for li in listings:
            lid = li["listing_id"]
            p = by_lid.get(str(lid)) or {}
            ptype = p.get("type") or _type_from_title(li.get("title"))
            if ptype not in TAXONOMY_BY_TYPE:
                continue
            want = taxonomy_id(TAXONOMY_BY_TYPE[ptype], li.get("taxonomy_id"))
            change = {}
            if want and want != li.get("taxonomy_id"):
                change["taxonomy_id"] = want
            title = html_unescape(li.get("title") or "")
            if nice_title(title) != title:
                change["title"] = nice_title(title)
            if not change:
                continue
            try:
                _req("PATCH", f"/shops/{shop_id}/listings/{lid}", tok, json=change)
                if "taxonomy_id" in change:
                    attributes.fill(lambda m, path, **kw: _req(m, path, tok, **kw), shop_id, lid, want,
                                    p or {"title": title, "type": ptype, "tags": li.get("tags", [])},
                                    skip=("room",) if ptype in ("junk_journal", "planner") else ())
                notes.append(f"{title[:50]} → " + ", ".join(
                    ("kategori düzeltildi" if k == "taxonomy_id" else "başlık düzeltildi") for k in change))
            except Exception as e:
                notes.append(f"{title[:50]} → HATA: {str(e)[:120]}")
    return notes


def html_unescape(s):
    import html
    return html.unescape(s or "")


def update_title(listing_id, title: str) -> dict:
    tok = token()
    return _req("PATCH", f"/shops/{tok['shop_id']}/listings/{listing_id}", tok, json={"title": title})


def sold_listings(limit=100) -> dict:
    """{listing_id: {"title", "sales"}} from the shop's recent transactions."""
    import html
    tok = token()
    res = _req("GET", f"/shops/{tok['shop_id']}/transactions", tok, params={"limit": limit})
    out = {}
    for t in res.get("results", []):
        lid = str(t.get("listing_id"))
        e = out.setdefault(lid, {"title": html.unescape(t.get("title") or ""), "sales": 0})
        e["sales"] += int(t.get("quantity") or 1)
    return out
