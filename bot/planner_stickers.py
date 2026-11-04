"""Functional digital planner stickers made with Pillow (no image quota): washi tapes, sticky notes,
word labels, date circles, weekday / month labels and icons, in the planner's palette. ~500 PNGs."""
import math

from PIL import Image, ImageDraw, ImageFilter

from .imgutil import font

WORDS = ["To Do", "Important", "Don't forget", "Meeting", "Appointment", "Deadline", "Birthday", "Anniversary",
         "Pay day", "Bills due", "Rent", "Groceries", "Workout", "Gym", "Yoga", "Walk", "Doctor", "Dentist",
         "Self care", "Me time", "Rest day", "Date night", "Family", "Friends", "Party", "Holiday", "Travel",
         "Vacation", "Work", "Study", "Exam", "Homework", "Project", "Call", "Email", "Shopping", "Cleaning",
         "Laundry", "Meal prep", "Cook", "Reading", "Movie night", "Coffee", "Water", "Sleep", "Journal",
         "Goals", "Habits", "Notes", "Ideas", "Priority", "Done", "In progress", "Waiting", "Cancelled",
         "Reminder", "Weekend", "Celebrate", "Grateful", "Focus"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def _soft(c, t=0.55):
    return tuple(int(v + (255 - v) * t) for v in c)


def _dark(c, t=0.35):
    return tuple(int(v * (1 - t)) for v in c)


def _shadow(im, r=6):
    a = im.split()[-1]
    sh = Image.new("RGBA", (im.width + r * 4, im.height + r * 4), (0, 0, 0, 0))
    m = Image.new("L", sh.size, 0)
    m.paste(a, (r * 2, r * 2 + 3))
    sh.putalpha(m.point(lambda v: v * 50 // 255).filter(ImageFilter.GaussianBlur(r)))
    sh.alpha_composite(im, (r * 2, r * 2))
    return sh


def washi(col, kind, w=900, h=150):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    teeth = [(0, 0)]
    for y in range(0, h + 1, 15):
        teeth.append((10 if (y // 15) % 2 else 0, y))
    right = [(w - (10 if (y // 15) % 2 else 0), y) for y in range(h, -1, -15)]
    d.polygon(teeth + [(0, h)] + right, fill=_soft(col, 0.35) + (215,))
    pat = _dark(col, 0.15) + (170,)
    if kind == "stripes":
        for x in range(-h, w, 40):
            d.polygon([(x, h), (x + 18, h), (x + 18 + h, 0), (x + h, 0)], fill=pat)
    elif kind == "dots":
        for y in range(18, h, 38):
            for x in range(20 + (y // 38 % 2) * 19, w - 10, 38):
                d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=pat)
    elif kind == "grid":
        for x in range(0, w, 30):
            d.line((x, 0, x, h), fill=pat, width=2)
        for y in range(0, h, 30):
            d.line((0, y, w, y), fill=pat, width=2)
    elif kind == "hearts":
        for x in range(40, w - 20, 80):
            _heart(d, x, h // 2, 18, pat)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(teeth + [(0, h)] + right, fill=255)
    im.putalpha(Image.fromarray(__import__("numpy").minimum(__import__("numpy").asarray(im.split()[-1]),
                                                          __import__("numpy").asarray(mask))))
    return im


def _heart(d, cx, cy, r, fill):
    d.ellipse((cx - r, cy - r, cx, cy), fill=fill)
    d.ellipse((cx, cy - r, cx + r, cy), fill=fill)
    d.polygon([(cx - r, cy - r // 2), (cx + r, cy - r // 2), (cx, cy + r)], fill=fill)


def sticky(col, shape, w=520):
    h = w if shape != "wide" else int(w * 0.55)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 10, fill=_soft(col, 0.6) + (255,))
    d.rectangle((0, 0, w, int(h * 0.12)), fill=_soft(col, 0.4) + (255,))
    for y in range(int(h * 0.3), h - 30, 52):
        d.line((30, y, w - 30, y), fill=_soft(col, 0.25) + (255,), width=3)
    if shape == "pin":
        d.ellipse((w / 2 - 22, 8, w / 2 + 22, 52), fill=_dark(col, 0.2) + (255,))
    return _shadow(im)


def label(text, col, style):
    f = font("sans_bold", 64)
    tw = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text.upper(), font=f))
    w, h = tw + 110, 130
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), text.upper(), font=f)
    ty = (h - (bb[3] - bb[1])) / 2 - bb[1]
    if style == 0:
        d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=col + (255,))
        d.text((55, ty), text.upper(), font=f, fill=(255, 255, 255, 255))
    elif style == 1:
        d.rounded_rectangle((0, 0, w - 1, h - 1), 22, fill=_soft(col, 0.7) + (255,), outline=col + (255,), width=6)
        d.text((55, ty), text.upper(), font=f, fill=_dark(col, 0.25) + (255,))
    else:
        d.polygon([(0, 0), (w - 40, 0), (w, h / 2), (w - 40, h), (0, h)], fill=col + (255,))
        d.text((45, ty), text.upper(), font=f, fill=(255, 255, 255, 255))
    return im


def date_circle(n, col, filled):
    s = 220
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if filled:
        d.ellipse((4, 4, s - 4, s - 4), fill=col + (255,))
    else:
        d.ellipse((6, 6, s - 6, s - 6), fill=(255, 255, 255, 255), outline=col + (255,), width=10)
    f = font("sans_bold", 100)
    t = str(n)
    tw = d.textlength(t, font=f)
    bb = d.textbbox((0, 0), t, font=f)
    d.text(((s - tw) / 2, (s - (bb[3] - bb[1])) / 2 - bb[1]), t, font=f, fill=(255, 255, 255, 255) if filled else col + (255,))
    return im


def icon(kind, col):
    s = 260
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = col + (255,)
    if kind == "heart":
        _heart(d, s // 2, s // 2 + 10, 100, c)
    elif kind == "star":
        pts = []
        for k in range(10):
            r = 120 if k % 2 == 0 else 50
            a = -math.pi / 2 + k * math.pi / 5
            pts.append((s / 2 + r * math.cos(a), s / 2 + r * math.sin(a)))
        d.polygon(pts, fill=c)
    elif kind == "check":
        d.ellipse((10, 10, s - 10, s - 10), fill=c)
        d.line((70, 135, 115, 180, 195, 85), fill=(255, 255, 255, 255), width=26, joint="curve")
    elif kind == "arrow":
        d.polygon([(20, 100), (150, 100), (150, 40), (245, 130), (150, 220), (150, 160), (20, 160)], fill=c)
    elif kind == "highlight":
        d.rounded_rectangle((0, 80, s, 180), 30, fill=col + (140,))
    elif kind == "clip":
        d.rounded_rectangle((90, 10, 170, 250), 40, outline=c, width=16)
        d.rounded_rectangle((115, 50, 145, 200), 15, outline=c, width=12)
    return im


def make_all(palette, themed=(), per_word=12):
    """palette: list of rgb (any length, more colors = more stickers); themed: AI sticker images (RGBA).
    Returns [(filename, PIL RGBA)]."""
    cols = list(dict.fromkeys(tuple(c) for c in palette))
    base = len(cols)
    while len(cols) < 6:
        cols.append(_dark(cols[len(cols) % max(1, base)], 0.25))
    nc = len(cols)
    out = []
    for i, t in enumerate(themed, 1):
        out.append((f"01-themed/themed-{i:02d}.png", t))
    for ci, c in enumerate(cols):
        for kind in ("solid", "stripes", "dots", "grid", "hearts"):
            out.append((f"02-washi-tape/washi-{kind}-{ci + 1}.png", washi(c, kind)))
        for shape in ("square", "wide", "pin"):
            out.append((f"03-sticky-notes/note-{shape}-{ci + 1}.png", sticky(c, shape)))
        for kind in ("heart", "star", "check", "arrow", "highlight", "clip"):
            out.append((f"07-icons/{kind}-{ci + 1}.png", icon(kind, c)))
    for wi, w in enumerate(WORDS):
        safe = w.lower().replace(" ", "-").replace("'", "")
        for k in range(min(per_word, nc * 3)):
            out.append((f"04-labels/{safe}-{k + 1}.png", label(w, cols[(wi + k) % nc], k % 3)))
    for n in range(1, 32):
        for k, filled in enumerate((True, False)):
            out.append((f"05-dates/date-{n:02d}-{'filled' if filled else 'outline'}.png", date_circle(n, cols[n % nc], filled)))
    for i, name in enumerate(DAYS + MONTHS):
        for k in range(4):
            out.append((f"06-days-months/{name.lower()}-{k + 1}.png", label(name, cols[(i + k) % nc], k % 3)))
    return out
