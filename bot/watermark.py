"""Light diagonal shop-name watermark for the LISTING images only (delivered product files stay clean)."""
import io

from PIL import Image, ImageDraw

from .imgutil import font, jpeg_bytes

TEXT = "SEBASTEIA"
SKIP = ("how",)       # listing images whose name contains these words get no watermark
OPACITY = 46          # 0-255, low = subtle
ANGLE = 28


def _mark(im: Image.Image, text=TEXT) -> Image.Image:
    base = im.convert("RGBA")
    w, h = base.size
    diag = int((w * w + h * h) ** 0.5) + 40
    layer = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = max(26, int(w * 0.028))
    f = font("sans_bold", size)
    tw = d.textlength(text, font=f)
    step_x, step_y = int(tw + w * 0.16), int(w * 0.13)
    row = 0
    for y in range(0, diag, step_y):
        offset = (step_x // 2) if row % 2 else 0
        for x in range(-step_x, diag, step_x):
            xx = x + offset
            d.text((xx + 2, y + 2), text, font=f, fill=(0, 0, 0, OPACITY // 2))
            d.text((xx, y), text, font=f, fill=(255, 255, 255, OPACITY))
        row += 1
    layer = layer.rotate(ANGLE, resample=Image.BICUBIC)
    left, top = (diag - w) // 2, (diag - h) // 2
    base.alpha_composite(layer.crop((left, top, left + w, top + h)))
    return base.convert("RGB")


def apply_all(mockups):
    """mockups = [(name, jpeg bytes)] -> same list with a light watermark added."""
    out = []
    for name, data in mockups:
        if any(s in name.lower() for s in SKIP):
            out.append((name, data))
            continue
        try:
            im = Image.open(io.BytesIO(data))
            out.append((name, jpeg_bytes(_mark(im), 88, dpi=72)))
        except Exception as e:
            print(f"[watermark] {name} atlandı: {e}")
            out.append((name, data))
    return out
