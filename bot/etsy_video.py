"""Etsy listing video: fast, punchy, about 10 s, 4:3, no audio and no extra text overlays.

Timeline (30 fps):
  1. cover punches in (zoom 1.25 -> 1.0 with a white flash), short hold with a slow push-in
  2. rapid montage of the real product items (0.28 s each), each pops in with a small bounce
  3. listing photos 2-5, each with a Ken Burns zoom, joined by fast whip-pan slides
  4. cover again with a pulse and a flash, so the video loops nicely on Etsy
"""
import io
import math
import os
import random
import subprocess
import tempfile
import zipfile

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

W, H, FPS = 1600, 1200, 30


# ---------------------------------------------------------------- helpers
def _ease_out(t):
    return 1 - (1 - t) ** 3


def _back_out(t, s=1.9):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def _fit(im):
    """Letterbox an image into W x H over a blurred copy of itself."""
    im = im.convert("RGB")
    bg = im.resize((W // 8, H // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
    s = min(W / im.width, H / im.height)
    fg = im.resize((max(2, int(im.width * s)), max(2, int(im.height * s))), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return bg


def _zoom(frame, z, cx=0.5, cy=0.5):
    """Zoom into a W x H frame (z >= 1) around (cx, cy)."""
    if abs(z - 1) < 1e-3:
        return frame
    cw, ch = W / z, H / z
    x0 = min(max(0, W * cx - cw / 2), W - cw)
    y0 = min(max(0, H * cy - ch / 2), H - ch)
    return frame.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))


def _scaled(frame, z):
    """Scale a frame around the centre; z < 1 shows it smaller on black (used for the punch-in)."""
    if z >= 1:
        return _zoom(frame, z)
    out = Image.new("RGB", (W, H), (0, 0, 0))
    t = frame.resize((int(W * z), int(H * z)), Image.BILINEAR)
    out.paste(t, ((W - t.width) // 2, (H - t.height) // 2))
    return out


def _flash(frame, amount):
    if amount <= 0:
        return frame
    return Image.blend(frame, Image.new("RGB", (W, H), (255, 255, 255)), min(1.0, amount))


def _slide(a, b, t):
    """Whip-pan: a slides out left, b slides in from the right, with motion blur in the middle."""
    e = _ease_out(t) if t > 0.5 else t * t * 2  # fast in the middle
    off = int(W * e)
    out = Image.new("RGB", (W, H))
    out.paste(a, (-off, 0))
    out.paste(b, (W - off, 0))
    blur = math.sin(math.pi * t) * 18
    if blur > 1:
        out = out.filter(ImageFilter.BoxBlur(blur)) if blur > 6 else out.filter(ImageFilter.GaussianBlur(blur / 3))
    return out


def _item_stage(cover):
    """Dark blurred cover used behind the item montage, so the items pop."""
    bg = cover.resize((W // 10, H // 10), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3)).resize((W, H), Image.BILINEAR)
    bg = ImageEnhance.Brightness(bg).enhance(0.55)
    vign = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(v * 0.75))
    return Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), bg, vign)


def _item_card(item, max_w, max_h):
    """White rounded card holding one product item (keeps transparent PNGs readable)."""
    item = item.convert("RGBA")
    item.thumbnail((int(max_w * 0.86), int(max_h * 0.86)), Image.LANCZOS)
    cw, ch = int(max_w), int(max_h)
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=40, fill=(255, 255, 255, 255))
    card.alpha_composite(item, ((cw - item.width) // 2, (ch - item.height) // 2))
    return card


def _pop(stage, card, t, angle):
    """Item card pops in with a bounce."""
    s = max(0.05, _back_out(min(1.0, t)))
    c = card.resize((max(2, int(card.width * s)), max(2, int(card.height * s))), Image.BILINEAR)
    c = c.rotate(angle * (1 - min(1.0, t)), expand=True, resample=Image.BILINEAR)
    out = stage.copy()
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    sh.putalpha(c.getchannel("A").point(lambda v: v * 0.5))
    out.paste(sh.filter(ImageFilter.GaussianBlur(16)), ((W - c.width) // 2 + 12, (H - c.height) // 2 + 24), sh.filter(ImageFilter.GaussianBlur(16)))
    out.paste(c, ((W - c.width) // 2, (H - c.height) // 2), c)
    return out


# ---------------------------------------------------------------- items from the delivery files
def items_from_delivery(delivery, limit=14):
    """Pick product images out of the buyer's delivery ZIPs / PDFs (every folder represented, evenly spread)."""
    names = []
    for fname, data in delivery:
        low = fname.lower()
        try:
            if low.endswith(".zip"):
                z = zipfile.ZipFile(io.BytesIO(data))
                for n in sorted(z.namelist()):
                    if n.lower().endswith((".png", ".jpg", ".jpeg")):
                        names.append(("zip", z, n))
            elif low.endswith(".pdf") and not names:
                import pypdfium2 as pdfium
                doc = pdfium.PdfDocument(data)
                for i in range(min(len(doc), limit)):
                    names.append(("pdf", doc, i))
        except Exception as e:
            print(f"[video] {fname} okunamadı: {e}")
    if not names:
        return []
    # round-robin over the folders (pages, cards, tags, stamps, stickers, papers... / each ZIP) so every kind of
    # piece the buyer gets shows up, then spread evenly inside each folder
    groups = {}
    for kind, src, key in names:
        folder = (id(src), key.rsplit("/", 1)[0] if kind == "zip" and "/" in key else "")
        groups.setdefault(folder, []).append((kind, src, key))
    queues = []
    for g in groups.values():
        share = max(1, -(-limit // len(groups)))
        step = max(1.0, len(g) / share)
        queues.append([g[int(i * step)] for i in range(min(share, len(g)))] + g)  # spread picks first, rest as spare
    picks, seen = [], set()
    while len(picks) < min(limit, len(names)) and any(queues):
        for q in queues:
            while q:
                it = q.pop(0)
                if (id(it[1]), it[2]) not in seen:
                    seen.add((id(it[1]), it[2]))
                    picks.append(it)
                    break
            if len(picks) >= limit:
                break
    out = []
    for kind, src, key in picks:
        try:
            if kind == "zip":
                im = Image.open(io.BytesIO(src.read(key)))
                im.draft("RGB", (900, 900))
                im = im.convert("RGBA")
            else:
                im = src[key].render(scale=1.0).to_pil().convert("RGBA")
            im.thumbnail((900, 900), Image.LANCZOS)
            out.append(im)
        except Exception as e:
            print(f"[video] öğe atlandı: {e}")
    return out


# ---------------------------------------------------------------- main
def make(photos, items=None):
    """photos: listing photos (PIL), the first one is the cover. items: optional product images.
    Returns mp4 bytes (about 10 s, no audio) or None."""
    photos = [p for p in list(photos)[:5] if p is not None]
    if not photos:
        return None
    first = photos[0].convert("RGB")
    # bundle covers (4:5 or square) keep all text inside the 4:3 centre band, so fill the frame instead of letterboxing
    cover = ImageOps.fit(first, (W, H), Image.LANCZOS) if 0.78 <= first.width / first.height <= 1.05 else _fit(first)
    rest = [_fit(p) for p in photos[1:5]]
    items = list(items or [])[:14]
    rnd = random.Random(7)

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp.name]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        put = lambda f: proc.stdin.write(f.tobytes())

        # 1. cover punch-in + flash, then a slow push-in
        n = int(0.35 * FPS)
        for i in range(n):
            t = (i + 1) / n
            put(_flash(_scaled(cover, 1.25 - 0.25 * _ease_out(t)), 0.8 * (1 - t)))
        n = int(0.75 * FPS)
        for i in range(n):
            put(_zoom(cover, 1 + 0.04 * i / n))
        last = _zoom(cover, 1.04)

        # 2. rapid item montage
        if items:
            stage = _item_stage(cover)
            per = max(5, int(0.28 * FPS))
            cards = [_item_card(it, W * 0.62, H * 0.82) for it in items]
            # quick hand-over from the cover to the stage
            for i in range(4):
                put(Image.blend(last, stage, (i + 1) / 4))
            for c in cards:
                ang = rnd.choice((-8, -5, 5, 8))
                for i in range(per):
                    last = _pop(stage, c, (i + 1) / (per * 0.6), ang)
                    put(last)

        # 3. listing photos with Ken Burns zoom and whip-pan slides
        hold, trans = int(1.0 * FPS), int(0.22 * FPS)
        for k, ph in enumerate(rest):
            cx, cy = rnd.choice(((0.5, 0.5), (0.4, 0.45), (0.6, 0.45), (0.5, 0.4)))
            first = _zoom(ph, 1.0, cx, cy)
            for i in range(trans):
                put(_slide(last, first, (i + 1) / trans))
            for i in range(hold):
                last = _zoom(ph, 1 + 0.07 * i / hold, cx, cy)
                put(last)

        # 4. back to the cover: slide in, pulse and flash (loops nicely)
        for i in range(trans):
            put(_slide(last, cover, (i + 1) / trans))
        n = int(1.1 * FPS)
        for i in range(n):
            t = i / n
            z = 1 + 0.06 * math.sin(math.pi * min(1, t * 1.6))
            put(_flash(_zoom(cover, z), 0.5 * max(0, 1 - t * 5)))
        proc.stdin.close()
        proc.wait()
        with open(tmp.name, "rb") as fh:
            data = fh.read()
        return data or None
    finally:
        os.unlink(tmp.name)
