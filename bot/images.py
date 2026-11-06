"""AI image generation with free providers, tried in order:
1. Cloudflare Workers AI – FLUX.2 [klein] (free daily allowance, needs CF account)
2. Cloudflare Workers AI – FLUX.1 [schnell] (square 1024, cropped to the requested ratio)
3. Pollinations.ai (free, may be slow/rate limited)
"""
import base64
import io
import random
import time
import urllib.parse

import requests
from PIL import Image, ImageOps

from . import config

CF_MULTIPART_MODELS = ["@cf/black-forest-labs/flux-2-klein-4b"]
CF_JSON_MODELS = ["@cf/black-forest-labs/flux-1-schnell"]

_disabled = set()  # providers that hit a daily quota during this run
_auth_fail = set()  # providers whose key was refused (not a quota problem)
stats = {"cloudflare": 0, "pollinations": 0, "failed": 0, "neurons": 0.0}
DAILY_NEURONS = 10000  # Cloudflare free allowance, resets 00:00 UTC (03:00 Istanbul)


class ImageError(Exception):
    pass


QUOTA_MSG = "Cloudflare günlük ücretsiz görsel kotası doldu (her gün 03:00'te yenilenir)"


def quota_exhausted():
    """True when every image provider is out for today."""
    return all(m in _disabled for m in CF_MULTIPART_MODELS + CF_JSON_MODELS) and "pollinations" in _disabled


def _snap(v: int) -> int:
    v = max(256, min(1920, int(v)))
    return v - v % 16


def fit_size(aspect: float, long_side: int = 1920):
    """Width/height for an aspect ratio (w/h) within provider limits."""
    if aspect >= 1:
        w, h = long_side, long_side / aspect
    else:
        w, h = long_side * aspect, long_side
    return _snap(w), _snap(h)


def _decode(b64: str) -> Image.Image:
    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    img.load()
    return img.convert("RGB")


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    return ImageOps.fit(img, (w, h), Image.LANCZOS)


def _quota_error(text: str) -> bool:
    t = text.lower()
    # only the real daily free-allowance error; "capacity temporarily exceeded" is transient and retried
    return any(k in t for k in ("neuron", "quota", "daily", "allocation", "4006"))


def _cloudflare(prompt, w, h, seed):
    if not (config.CLOUDFLARE_ACCOUNT_ID and config.CLOUDFLARE_API_TOKEN):
        raise ImageError("Cloudflare anahtarı yok")
    base = f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/"
    headers = {"Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}"}
    errs = []
    for model in CF_MULTIPART_MODELS:
        if model in _disabled:
            continue
        for attempt in range(4):
            try:
                files = {
                    "prompt": (None, prompt[:2000]),
                    "width": (None, str(w)),
                    "height": (None, str(h)),
                }
                r = requests.post(base + model, headers=headers, files=files, timeout=180)
                if r.status_code == 200:
                    data = r.json()
                    img_b64 = (data.get("result") or {}).get("image")
                    if img_b64:
                        stats["neurons"] += 26.05 * (-(-w // 512)) * (-(-h // 512))
                        return _decode(img_b64)
                    errs.append(f"{model.split('/')[-1]}: boş yanıt")
                else:
                    errs.append(f"{model.split('/')[-1]}: HTTP {r.status_code} {r.text[:160]}")
                    print(f"[images] {errs[-1]}", flush=True)
                    if r.status_code in (401, 403):
                        _disabled.add(model)
                        _auth_fail.add("cloudflare")
                        break
                    if _quota_error(r.text):
                        _disabled.add(model)
                        break
            except Exception as e:
                errs.append(f"{model.split('/')[-1]}: {e}")
            time.sleep(8 * (attempt + 1))
    for model in CF_JSON_MODELS:
        if model in _disabled:
            continue
        try:
            r = requests.post(base + model, headers=headers, json={"prompt": prompt[:2000], "steps": 8}, timeout=180)
            if r.status_code == 200:
                img_b64 = (r.json().get("result") or {}).get("image")
                if img_b64:
                    stats["neurons"] += 4.8 * 4 + 9.6 * 8
                    return _cover(_decode(img_b64), w, h)
            errs.append(f"{model.split('/')[-1]}: HTTP {r.status_code} {r.text[:160]}")
            print(f"[images] {errs[-1]}", flush=True)
            if _quota_error(r.text) or r.status_code in (401, 403):
                _disabled.add(model)
        except Exception as e:
            errs.append(f"{model.split('/')[-1]}: {e}")
    if all(m in _disabled for m in CF_MULTIPART_MODELS + CF_JSON_MODELS) and not errs:
        raise ImageError(QUOTA_MSG)
    raise ImageError(" / ".join(errs) or "Cloudflare kullanılamıyor")


def _pollinations(prompt, w, h, seed):
    if "pollinations" in _disabled:
        raise ImageError("Pollinations devre dışı")
    q = urllib.parse.quote(prompt[:1500], safe="")
    params = {"width": w, "height": h, "seed": seed, "model": "flux", "nologo": "true", "private": "true"}
    urls = []
    headers = {}
    if config.POLLINATIONS_TOKEN:
        headers["Authorization"] = f"Bearer {config.POLLINATIONS_TOKEN}"
        urls.append(f"https://gen.pollinations.ai/image/{q}")
    urls.append(f"https://image.pollinations.ai/prompt/{q}")
    last = ""
    for url in urls:
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=240)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                    img = Image.open(io.BytesIO(r.content))
                    img.load()
                    return _cover(img.convert("RGB"), w, h)
                last = f"HTTP {r.status_code} {r.text[:150]}"
                if r.status_code in (401, 402, 403):
                    if r.status_code == 402:
                        _disabled.add("pollinations")  # free limit used up for now
                    break
            except Exception as e:
                last = str(e)
            time.sleep(15 * (attempt + 1))
    raise ImageError(f"Pollinations: {last}")


MAX_SIDE = 1024  # Cloudflare bills per 512x512 output tile: 1024px = 4 tiles, 1920px = 12-16 tiles


def generate(prompt: str, width: int, height: int, seed: int = None) -> Image.Image:
    w, h = _snap(width), _snap(height)
    # generate small (cheap on the free daily allowance) and upscale locally; every product
    # resizes to its print size afterwards anyway
    k = min(1.0, MAX_SIDE / max(w, h))
    gw, gh = _snap(w * k), _snap(h * k)
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    errors = []
    for name, fn in (("cloudflare", _cloudflare), ("pollinations", _pollinations)):
        try:
            img = fn(prompt, gw, gh, seed)
            if img.size != (w, h):
                img = img.resize((w, h), Image.LANCZOS)
            stats[name] += 1
            return img
        except Exception as e:
            errors.append(f"{name}: {e}")
    stats["failed"] += 1
    if "cloudflare" in _auth_fail:
        raise ImageError("Görsel üretilemedi → Cloudflare anahtarı reddedildi (kota değil; /kota ile kontrol et) | "
                         + " | ".join(errors))
    if quota_exhausted():
        raise ImageError("Görsel üretilemedi → " + QUOTA_MSG)
    raise ImageError("Görsel üretilemedi → " + " | ".join(errors))


def try_generate(prompt: str, width: int, height: int):
    """Like generate(), but returns None instead of failing, so one bad image does not waste a whole pack."""
    try:
        return generate(prompt, width, height)
    except Exception as e:
        print(f"[images] görsel atlandı: {e}")
        return None


def need(have: int, wanted: int, ratio: float = 0.8):
    """Stop the product only when too many images failed (keeps packs with e.g. 13 of 15 images)."""
    if have < max(1, int(wanted * ratio + 0.999)):
        raise ImageError(f"Görsel üretilemedi → sadece {have}/{wanted} görsel çıktı"
                         + (f" ({QUOTA_MSG})" if quota_exhausted() else ""))


def usage_today() -> dict:
    """Add this run's Cloudflare usage to today's total (stored in meta). Returns {"used", "left_images"}."""
    import datetime as _dt
    from . import storage
    day = _dt.datetime.utcnow().date().isoformat()
    meta = storage.load_meta()
    u = meta.get("cf_usage") or {}
    if u.get("day") != day:
        u = {"day": day, "neurons": 0.0}
    u["neurons"] = round(u.get("neurons", 0.0) + stats["neurons"], 1)
    stats["neurons"] = 0.0
    if quota_exhausted() or any(m in _disabled for m in CF_MULTIPART_MODELS):
        u["exhausted"] = True  # Cloudflare itself said the free allowance is used up
    meta["cf_usage"] = u
    storage.save_meta(meta)
    used = DAILY_NEURONS if u.get("exhausted") else min(DAILY_NEURONS, u["neurons"])
    return {"used": int(used), "left_images": int((DAILY_NEURONS - used) // 104), "exhausted": bool(u.get("exhausted"))}


def _explain(code, text):
    t = text.lower()
    if code in (401, 403) or "authentication" in t or "unauthorized" in t:
        return "anahtar (API token) geçersiz, süresi dolmuş ya da Workers AI izni yok"
    if "4006" in t or "neuron" in t or "allocation" in t:
        return "günlük ücretsiz kota dolu"
    if code == 402:
        return "ücretsiz limit doldu"
    if code == 429:
        return "çok sık istek, birkaç dakika sonra düzelir"
    return text[:160]


def probe() -> list:
    """One tiny real request to each image provider (~0.3% of the daily allowance), so the user sees the real answer."""
    out = []
    if not (config.CLOUDFLARE_ACCOUNT_ID and config.CLOUDFLARE_API_TOKEN):
        out.append("❌ Cloudflare: anahtar GitHub secrets'ta yok (CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN)")
    else:
        base = f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/"
        try:
            r = requests.post(base + CF_MULTIPART_MODELS[0], headers={"Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}"},
                              files={"prompt": (None, "a small red apple"), "width": (None, "512"), "height": (None, "512")},
                              timeout=120)
            if r.status_code == 200 and (r.json().get("result") or {}).get("image"):
                stats["neurons"] += 26.05
                out.append("✅ Cloudflare: çalışıyor, resim çizebiliyor")
            else:
                out.append(f"❌ Cloudflare: HTTP {r.status_code} → {_explain(r.status_code, r.text)}")
                print(f"[images] probe cloudflare: {r.status_code} {r.text[:300]}", flush=True)
        except Exception as e:
            out.append(f"❌ Cloudflare: bağlantı hatası ({str(e)[:120]})")
    try:
        headers = {"Authorization": f"Bearer {config.POLLINATIONS_TOKEN}"} if config.POLLINATIONS_TOKEN else {}
        url = ("https://gen.pollinations.ai/image/" if config.POLLINATIONS_TOKEN else "https://image.pollinations.ai/prompt/") + "a%20small%20red%20apple"
        r = requests.get(url, params={"width": 256, "height": 256, "model": "flux", "nologo": "true", "private": "true"},
                         headers=headers, timeout=180)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            out.append("✅ Pollinations (yedek): çalışıyor")
        else:
            out.append(f"❌ Pollinations (yedek): HTTP {r.status_code} → {_explain(r.status_code, r.text)}")
            print(f"[images] probe pollinations: {r.status_code} {r.text[:300]}", flush=True)
    except Exception as e:
        out.append(f"❌ Pollinations (yedek): bağlantı hatası ({str(e)[:120]})")
    try:  # text AI (titles, descriptions): Google Gemini, its own quota renews at 11:00 Turkey time
        from . import llm
        if not config.GEMINI_API_KEY:
            out.append("❌ Yazı (Gemini): anahtar yok")
        else:
            m = (llm.gemini_models() or ["gemini-flash-latest"])[0]
            r = requests.post(f"{llm.GEMINI_BASE}/models/{m}:generateContent", params={"key": config.GEMINI_API_KEY},
                              json={"contents": [{"parts": [{"text": "Say OK"}]}]}, timeout=60)
            if r.status_code == 200:
                out.append("✅ Yazı (Gemini): çalışıyor")
            elif r.status_code == 429:
                out.append("❌ Yazı (Gemini): günlük kota dolu → her gün 11:00'de yenilenir")
            else:
                out.append(f"❌ Yazı (Gemini): HTTP {r.status_code} → {_explain(r.status_code, r.text)}")
    except Exception as e:
        out.append(f"❌ Yazı (Gemini): bağlantı hatası ({str(e)[:100]})")
    return out


def quota_report() -> str:
    """Telegram text for /kota: today's use, images left, and exactly when the allowance resets."""
    import datetime as _dt
    live = probe()
    u = usage_today()
    now = _dt.datetime.now(_dt.timezone.utc)
    reset = (now + _dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    left = reset - now
    hh, mm = left.seconds // 3600, left.seconds % 3600 // 60
    cf_ok = live[0].startswith("✅")
    state = ("⛔ <b>Şu an Cloudflare resim çizmiyor</b> (sebebi aşağıdaki testte)" if not cf_ok else
             "⛔ <b>Bugünkü kota doldu.</b>" if u["exhausted"] else
             f"✅ Yaklaşık <b>{u['left_images']} görsel</b> hakkın kaldı.")
    return (f"🔋 <b>Görsel kotası</b> (Cloudflare, günde {DAILY_NEURONS:,} birim ≈ 96 görsel)\n"
            f"{state}\nBugün kullanılan: ~{u['used']:,}/{DAILY_NEURONS:,}\n"
            f"♻️ Yenilenme: her gün <b>03:00</b> (Türkiye saati) → <b>{hh} sa {mm} dk</b> sonra\n\n"
            "🔎 <b>Şu anki canlı test:</b>\n" + "\n".join(live) + "\n\n"
            "Yaklaşık harcama:\n"
            "• /kapak_konu → 6 görsel (6 ilan)\n"
            "• /uret_journal → 12 görsel\n"
            "• /uret_stickers → 8 görsel\n"
            "• /uret_junk → 14 görsel\n"
            "• diğer ürünler → 10-20 görsel\n"
            "• 11:15 otomatik üretim (4 ürün) → ~50-60 görsel\n\n"
            "Not: Yazı kotası (Gemini) ayrı: her gün 11:00'de yenilenir.")
