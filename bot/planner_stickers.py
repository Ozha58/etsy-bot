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


EDITION_WORDS = {  # extra word labels for an edition's own stickers
    "migraine": ["Migraine day", "Headache", "Aura", "Took meds", "Rest day", "Dark room", "Ice pack", "Hydrate",
                 "Neurologist", "Doctor appt", "Flare day", "Low spoons", "Pain free!", "Good day", "Trigger",
                 "Weather change", "Poor sleep", "Screen break", "Caffeine", "Cycle day", "Stress", "Nausea",
                 "Light sensitive", "Sound sensitive", "Neck pain", "Rescue med", "Preventive", "Self care",
                 "Nap", "Quiet time", "Skipped meal", "Hormones", "Bad night", "Ask for help", "Be gentle"],
}


def pain_scale(n, size=240):
    """A 0-10 pain level sticker: green to red circle, the number and a small face."""
    t = n / 10
    col = tuple(int(a + (b - a) * t) for a, b in zip((120, 185, 120), (220, 85, 75)))
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((6, 6, size - 6, size - 6), fill=col + (255,), outline=(255, 255, 255, 255), width=10)
    f = font("sans_bold", int(size * 0.34))
    txt = str(n)
    tw = d.textlength(txt, font=f)
    d.text(((size - tw) / 2, size * 0.16), txt, font=f, fill=(255, 255, 255, 255))
    ex, ey, er = size * 0.36, size * 0.62, size * 0.035
    for x in (ex, size - ex):
        d.ellipse((x - er, ey - er, x + er, ey + er), fill=(255, 255, 255, 255))
    mw, my = size * 0.16, size * 0.76
    curve = 0.10 - 0.2 * t  # smile at 0, frown at 10
    d.arc((size / 2 - mw, my - abs(curve) * size, size / 2 + mw, my + abs(curve) * size),
          *((20, 160) if curve > 0 else (200, 340)), fill=(255, 255, 255, 255), width=int(size * 0.03))
    return im


def trigger_icon(kind, col, size=260):
    """Simple, clear trigger / care icons drawn by code."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, w = col + (255,), (255, 255, 255, 255)
    d.ellipse((4, 4, size - 4, size - 4), fill=_soft(col, 0.75) + (255,), outline=c, width=8)
    s = size
    if kind == "pill":
        d.rounded_rectangle((s * .22, s * .40, s * .78, s * .60), s * .1, fill=c)
        d.rectangle((s * .5, s * .40, s * .78, s * .60), fill=_dark(col, 0.25) + (255,))
        d.rounded_rectangle((s * .22, s * .40, s * .78, s * .60), s * .1, outline=_dark(col, 0.35) + (255,), width=4)
    elif kind == "water":
        d.polygon([(s * .5, s * .18), (s * .70, s * .52), (s * .30, s * .52)], fill=c)
        d.ellipse((s * .30, s * .38, s * .70, s * .78), fill=c)
    elif kind == "sleep":
        d.ellipse((s * .25, s * .22, s * .72, s * .70), fill=c)
        d.ellipse((s * .38, s * .16, s * .82, s * .62), fill=_soft(col, 0.75) + (255,))
    elif kind == "weather":
        for x, y, r in ((.40, .45, .16), (.58, .40, .19), (.70, .50, .13), (.30, .52, .12)):
            d.ellipse((s * (x - r), s * (y - r), s * (x + r), s * (y + r)), fill=c)
        for x in (.36, .52, .68):
            d.line((s * x, s * .66, s * (x - .05), s * .80), fill=c, width=int(s * .035))
    elif kind == "coffee":
        d.rounded_rectangle((s * .26, s * .36, s * .64, s * .74), s * .06, fill=c)
        d.ellipse((s * .58, s * .44, s * .78, s * .62), outline=c, width=int(s * .04))
        for x in (.36, .46, .56):
            d.arc((s * (x - .04), s * .16, s * (x + .04), s * .32), 90, 270, fill=c, width=int(s * .025))
    elif kind == "screen":
        d.rounded_rectangle((s * .34, s * .18, s * .66, s * .82), s * .05, fill=c)
        d.rectangle((s * .38, s * .25, s * .62, s * .72), fill=w)
    elif kind == "ice":
        d.rounded_rectangle((s * .24, s * .30, s * .76, s * .70), s * .12, fill=c)
        for a in range(3):
            import math
            ang = math.pi / 3 * a
            d.line((s * .5 - s * .14 * math.cos(ang), s * .5 - s * .14 * math.sin(ang),
                    s * .5 + s * .14 * math.cos(ang), s * .5 + s * .14 * math.sin(ang)), fill=w, width=int(s * .03))
    elif kind == "aura":
        d.polygon([(s * .56, s * .14), (s * .30, s * .54), (s * .48, s * .54), (s * .40, s * .86), (s * .70, s * .42),
                   (s * .52, s * .42)], fill=c)
    elif kind == "calendar":
        d.rounded_rectangle((s * .24, s * .28, s * .76, s * .76), s * .05, fill=w, outline=c, width=8)
        d.rectangle((s * .24, s * .28, s * .76, s * .40), fill=c)
        for k in range(6):
            x, y = s * (.32 + (k % 3) * .14), s * (.50 + (k // 3) * .12)
            d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=c)
    elif kind == "heart":
        _heart(d, s // 2, s // 2 + 12, int(s * .26), c)
    return im


TRIGGER_ICONS = ("pill", "water", "sleep", "weather", "coffee", "screen", "ice", "aura", "calendar", "heart")


def make_all(palette, themed=(), per_word=12, edition=None):
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
    words = EDITION_WORDS.get(edition or "", [])
    for wi, w in enumerate(words):  # the edition's own labels come first in the pack
        safe = w.lower().replace(" ", "-").replace("'", "").replace("!", "")
        for k in range(min(6, nc * 2)):
            out.append((f"08-{edition}-labels/{safe}-{k + 1}.png", label(w, cols[(wi + k) % nc], k % 3)))
    if edition == "migraine":
        for n in range(11):
            out.append((f"09-pain-scale/pain-{n:02d}.png", pain_scale(n)))
        for ci, c in enumerate(cols[:6]):
            for kind in TRIGGER_ICONS:
                out.append((f"10-trigger-icons/{kind}-{ci + 1}.png", trigger_icon(kind, c)))
    for i, name in enumerate(DAYS + MONTHS):
        for k in range(4):
            out.append((f"06-days-months/{name.lower()}-{k + 1}.png", label(name, cols[(i + k) % nc], k % 3)))
    return out
