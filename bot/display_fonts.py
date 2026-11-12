"""Display fonts for designs with words on them (sublimation / shirt PNGs).

Open-licence Google Fonts (SIL OFL), downloaded once per run from the Google Fonts GitHub repo into the work
folder. If the download fails the shop fonts (Lora / Poppins) are used, so a product never breaks on a font."""
import requests
from PIL import ImageFont

from . import config

BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {  # kind -> (path in the google/fonts repo, fallback shop font)
    "script": ("pacifico/Pacifico-Regular.ttf", "Lora-Italic-Variable.ttf"),
    "elegant": ("greatvibes/GreatVibes-Regular.ttf", "Lora-Italic-Variable.ttf"),
    "retro": ("lobster/Lobster-Regular.ttf", "Lora-Variable.ttf"),
    "bold": ("bebasneue/BebasNeue-Regular.ttf", "Poppins-Bold.ttf"),
    "serif": ("abrilfatface/AbrilFatface-Regular.ttf", "Lora-Variable.ttf"),
    "rounded": ("fredoka/Fredoka%5Bwdth,wght%5D.ttf", "Poppins-Bold.ttf"),
    "hand": ("caveat/Caveat%5Bwght%5D.ttf", "Lora-Italic-Variable.ttf"),
    "brush": ("caveatbrush/CaveatBrush-Regular.ttf", "Poppins-Bold.ttf"),
}
_cache = {}


def path(kind):
    if kind in _cache:
        return _cache[kind]
    rel, fallback = FONTS.get(kind, FONTS["bold"])
    d = config.WORK_DIR / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    f = d / rel.rsplit("/", 1)[-1].replace("%5B", "[").replace("%5D", "]")
    if not f.exists():
        try:
            r = requests.get(BASE + rel, timeout=30)
            r.raise_for_status()
            f.write_bytes(r.content)
        except Exception as e:
            print(f"[fonts] {kind} indirilemedi, yedek font: {e}")
            f = config.FONTS_DIR / fallback
    _cache[kind] = f
    return f


def get(kind, size):
    try:
        return ImageFont.truetype(str(path(kind)), int(size))
    except Exception:
        return ImageFont.truetype(str(config.FONTS_DIR / FONTS.get(kind, FONTS["bold"])[1]), int(size))


def fit(draw, text, kind, max_w, start, min_size=60):
    s = start
    while s > min_size:
        f = get(kind, s)
        if draw.textlength(text, font=f) <= max_w:
            return f
        s -= max(4, s // 20)
    return get(kind, min_size)
