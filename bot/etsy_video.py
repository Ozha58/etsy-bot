"""Etsy listing video: 4:3, no text or labels, soft crossfades, built from the listing photos."""
import os
import subprocess
import tempfile

import imageio_ffmpeg
from PIL import Image, ImageFilter

W, H, FPS = 1600, 1200, 24


def _frame(im):
    im = im.convert("RGB")
    bg = im.resize((W // 8, H // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
    s = min(W / im.width, H / im.height)
    fg = im.resize((max(2, int(im.width * s)), max(2, int(im.height * s))), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return bg


def make(photos, seconds_per=2.2, fade=0.5):
    """photos: list of PIL images. Returns mp4 bytes (about 12 s, no audio) or None."""
    frames = [_frame(im) for im in list(photos)[:5]]
    if not frames:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp.name]
    hold, nf = int(seconds_per * FPS), int(fade * FPS)
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        for i, f in enumerate(frames):
            raw = f.tobytes()
            for _ in range(hold):
                proc.stdin.write(raw)
            if i + 1 < len(frames):
                for k in range(1, nf + 1):
                    proc.stdin.write(Image.blend(f, frames[i + 1], k / (nf + 1)).tobytes())
        proc.stdin.close()
        proc.wait()
        with open(tmp.name, "rb") as fh:
            data = fh.read()
        return data or None
    finally:
        os.unlink(tmp.name)
