"""Printable monthly bullet journal bundle (the model of the biggest journal shops on Etsy).

One listing = one month (e.g. "December 2026", one cozy theme) in a black & white version (cheap, colour it yourself)
or a pre-colored version (black & white included as a bonus). Every 4th journal, and the first one each autumn,
is the big YEAR bundle (12 months + year pages, 230+ pages) at a much higher price: a price ladder like
$3.49 -> $5.99 -> $19.99. Sometimes a Southern Hemisphere edition (seasons the other way round), which almost
nobody makes.

Pages are drawn by code in a hand-drawn bullet journal style (dated calendars, weekly spreads, habit / mood / sleep /
water trackers, gratitude, expenses, reading log, memories, review). Only the 12 small theme doodles are AI images;
the pre-colored version colours them in by code. Sizes: A4, A5 and US Letter PDFs."""
import calendar
import datetime as dt
import io
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import display_fonts as DF
from .. import images, mockups, storage
from ..bundle_cover import bundle_cover
from ..imgutil import font, hex2rgb, jpeg_bytes, make_zips, thumb_b64

LABEL_TR = "Yazdırılabilir aylık günlük paketi (bullet journal, A4 + A5 + Letter PDF)"
SPEC_FIELDS = """
  "journal_name": "theme name, 2-3 words, fits the month and the season (e.g. 'Cozy Winter', 'Snowy Forest', 'Fresh Start')",
  "doodles": [ exactly 12 objects {"name": "short name", "prompt": "English prompt for ONE small cute doodle object that fits the theme and the month (e.g. 'a steaming mug of cocoa with marshmallows', 'a knitted mitten'), no animals in clothes, no characters"} ]
"""
N_DOODLES = 12
SUFFIX = ("simple cute hand-drawn doodle, bullet journal style, clean black ink outline only, closed shapes, "
          "pure white background, no shading, no fill, no color, no text, no letters, one object, centered")
PRICES = {"bw": 3.49, "colour": 5.99, "year": 19.99}
MONTHS = list(calendar.month_name)[1:]
SOUTH_SEASON = {12: "summer", 1: "summer", 2: "summer", 3: "autumn", 4: "autumn", 5: "autumn",
                6: "winter", 7: "winter", 8: "winter", 9: "spring", 10: "spring", 11: "spring"}
NORTH_SEASON = {m: {"summer": "winter", "autumn": "spring", "winter": "summer", "spring": "autumn"}[s]
                for m, s in SOUTH_SEASON.items()}
A4 = (2480, 3508)
LETTER = (2550, 3300)
A5 = (1748, 2480)


# ---------------------------------------------------------------- plan (decided by code, before the AI writes the listing)
def prepare(idea, today=None):
    """Which journal to make now: month or year bundle, black & white or pre-colored, which month, which hemisphere.
    Changes the idea in place (niche, search phrase, brief for the AI) and returns fields for the spec."""
    today = today or dt.date.today()
    past = [p.get("spec", {}) for p in storage.all_products() if p.get("type") == "journal" and p.get("status") != "rejected"]
    rnd = random.Random(f"{today}{len(past)}")
    next_year = today.year + 1 if today.month >= 9 else today.year
    has_year = any(s.get("scope") == "year" and s.get("year") == next_year for s in past)
    if (today.month >= 9 and not has_year) or len(past) % 4 == 3:
        scope, variant, hemi = "year", "colour", "north"
        if has_year and rnd.random() < 0.5:
            hemi = "south"
        months, year = list(range(1, 13)), next_year
    else:
        scope = "month"
        months_done = [(s.get("month"), s.get("year"), s.get("variant")) for s in past if s.get("scope") == "month"]
        cands = []
        for k in (1, 2):
            m = (today.month - 1 + k) % 12 + 1
            y = today.year + (today.month - 1 + k) // 12
            cands.append((m, y))
        bw = sum(1 for _, _, v in months_done if v == "bw")
        variant = "bw" if bw <= len(months_done) - bw else "colour"
        m, year = min(cands, key=lambda c: sum(1 for d in months_done if d[:2] == c))
        months = [m]
        hemi = "south" if rnd.random() < 0.2 else "north"
    season = (SOUTH_SEASON if hemi == "south" else NORTH_SEASON)
    if scope == "year":
        what = f"a {year} YEAR journal bundle (all 12 months, 230+ printable bullet journal pages, pre-colored + black and white)"
        theme_hint = "ONE calm theme that works all year (e.g. 'Wildflower Meadow', 'Cozy Botanical', 'Little Things')"
        phrase = f"{year} bullet journal"
        must = (f"The title MUST start with '{year} Bullet Journal Bundle' and contain 'Printable' (the word 'journal' "
                "only once in the title, one comma at most)")
    else:
        mname = MONTHS[months[0] - 1]
        col = "pre-colored" if variant == "colour" else "black and white (color it yourself)"
        what = f"a {mname} {year} monthly journal bundle ({col}), printable bullet journal pages"
        theme_hint = (f"ONE cozy theme that fits {mname} in the {season[months[0]]} "
                      + ("of the SOUTHERN HEMISPHERE (Australia / New Zealand: seasons are the other way round)" if hemi == "south" else "")
                      + " (e.g. for December north: 'Cozy Winter', 'Snowy Pines'; for January: 'Fresh Start', 'Winter Walk')")
        phrase = f"{mname.lower()} journal"
        must = (f"The title MUST start with '{mname} {year} Bullet Journal' and contain 'Printable' "
                "(the word 'journal' only once in the title, one comma at most)"
                + (", and 'Pre-Colored'" if variant == "colour" else ", and 'Black and White'")
                + (", and 'Southern Hemisphere'" if hemi == "south" else ""))
    idea["niche"] = f"{what}"
    idea["search_query"] = phrase
    idea["brief"] = (f"JOURNAL PLAN (mandatory): {what}. Theme: {theme_hint}. {must}. "
                     "Pages are dated (calendar, weekly spreads) with trackers (habit, mood, sleep, water), gratitude, "
                     "expenses, reading log, memories and a month review; A4, A5 and US Letter PDFs. "
                     "Tags: bullet journal, printable journal, journal pages, journal bundle, monthly spread, "
                     f"habit tracker, mood tracker, {phrase}, {year} journal and similar.")
    return {"scope": scope, "variant": variant, "hemisphere": hemi, "months": months, "year": year,
            "month": months[0] if scope == "month" else None, "price_usd": PRICES["year" if scope == "year" else variant]}


# ---------------------------------------------------------------- drawing helpers (hand-drawn look)
def _tint(c, k=0.72):
    return tuple(int(v + (255 - v) * k) for v in c)


class Pen:
    def __init__(self, size, pal, colour, seed, doodles):
        self.W, self.H = size
        self.u = self.W / 100.0
        self.ink = (38, 38, 42)
        self.soft = (150, 150, 155)
        self.pal = pal
        self.colour = colour
        self.rnd = random.Random(seed)
        self.doodles = doodles
        self.lw = max(3, int(self.u * 0.28))

    def new(self):
        im = Image.new("RGB", (self.W, self.H), (255, 255, 255))
        return im, ImageDraw.Draw(im)

    def f(self, kind, size):
        return DF.get(kind, size * self.u) if kind in ("hand", "serif") else font(kind, int(size * self.u))

    def line(self, d, x0, y0, x1, y1, w=None, col=None):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(2, int(L / (self.u * 6)))
        a = self.u * 0.12
        pts = []
        for i in range(n + 1):
            t = i / n
            j = 0 if i in (0, n) else self.rnd.uniform(-a, a)
            nx, ny = (-(y1 - y0) / L, (x1 - x0) / L) if L else (0, 0)
            pts.append((x0 + (x1 - x0) * t + nx * j, y0 + (y1 - y0) * t + ny * j))
        d.line(pts, fill=col or self.ink, width=w or self.lw, joint="curve")

    def rect(self, d, x0, y0, x1, y1, w=None, col=None, fill=None):
        if fill:
            d.rectangle((x0, y0, x1, y1), fill=fill)
        for a, b, c, e in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
            self.line(d, a, b, c, e, w, col)

    def c(self, i):
        return self.pal[i % len(self.pal)]

    def highlight(self, im, box, i=0):
        """Highlighter stroke behind a heading (pre-colored only)."""
        if not self.colour:
            return
        x0, y0, x1, y1 = box
        lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        dd.rounded_rectangle((x0, y0, x1, y1), radius=int(self.u * 1.2), fill=_tint(self.c(i), 0.45) + (200,))
        lay = lay.rotate(self.rnd.uniform(-1.2, 1.2), center=((x0 + x1) / 2, (y0 + y1) / 2))
        im.paste(lay, (0, 0), lay)

    def doodle(self, im, k, cx, cy, size):
        if not self.doodles:
            return
        dd = self.doodles[k % len(self.doodles)][1 if self.colour else 0].copy()
        dd.thumbnail((int(size), int(size)), Image.LANCZOS)
        im.paste(dd, (int(cx - dd.width / 2), int(cy - dd.height / 2)), dd)

    def header(self, im, d, title, sub="", k=0):
        u = self.u
        f = DF.fit(d, title, "hand", self.W - 34 * u, int(10 * u), int(5 * u))
        tw = d.textlength(title, font=f)
        self.highlight(im, (7 * u, 9 * u, 7 * u + tw + 3 * u, 14.2 * u), k)
        d = ImageDraw.Draw(im)
        d.text((8 * u, 12 * u), title, font=f, fill=self.ink, anchor="ls")
        if sub:
            d.text((8.4 * u, 15.6 * u), sub.upper(), font=self.f("sans_bold", 1.6), fill=self.soft, anchor="ls")
        self.line(d, 8 * u, 17.5 * u, self.W - 8 * u, 17.5 * u, col=self.soft, w=max(2, self.lw // 2))
        self.doodle(im, k, self.W - 15 * u, 9.5 * u, 13 * u)
        return d


# ---------------------------------------------------------------- doodles: AI line art -> black & white + coloured
def _doodle_pair(raw, pal, seed):
    from scipy import ndimage
    g = np.array(raw.convert("L"))
    ink = g < 140
    ink = ndimage.binary_dilation(ink, iterations=1)
    lab, n = ndimage.label(~ink)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    h, w = g.shape
    bw = np.full((h, w, 4), 255, np.uint8)
    bw[..., 3] = 0
    inside = ~np.isin(lab, list(border)) & ~ink
    bw[inside] = (255, 255, 255, 255)
    bw[ink] = (38, 38, 42, 255)
    col = bw.copy()
    rnd = random.Random(seed)
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(n + 1))
    for r in range(1, n + 1):
        if r in border or sizes[r] < 60:
            continue
        c = _tint(pal[rnd.randrange(len(pal))], rnd.choice((0.15, 0.3, 0.45)))
        col[lab == r] = c + (255,)
    out = []
    for arr in (bw, col):
        im = Image.fromarray(arr, "RGBA")
        bb = im.getbbox()
        out.append(im.crop(bb) if bb else im)
    return out


# ---------------------------------------------------------------- pages
DAYS = ["S", "M", "T", "W", "T", "F", "S"]


def p_cover(P, month, year, name, hemi):
    im, d = P.new()
    u = P.u
    if P.colour:
        d.rectangle((0, 0, P.W, P.H), fill=_tint(P.c(0), 0.86))
    for i in range(10):  # a garland of doodles above and below the title
        row, k = divmod(i, 5)
        x = (14 + k * 18) * u
        y = P.H * (0.2 if row == 0 else 0.8) + (5 * u if k % 2 else -3 * u) * (1 if row == 0 else -1)
        P.doodle(im, i, x, y, 16 * u)
    d = ImageDraw.Draw(im)
    if P.colour:
        d.ellipse((P.W / 2 - 38 * u, P.H / 2 - 24 * u, P.W / 2 + 38 * u, P.H / 2 + 22 * u), fill=(255, 255, 255))
    else:
        d.ellipse((P.W / 2 - 38 * u, P.H / 2 - 24 * u, P.W / 2 + 38 * u, P.H / 2 + 22 * u), outline=P.soft, width=P.lw)
    d = ImageDraw.Draw(im)
    title = MONTHS[month - 1] if month else str(year)
    f = DF.fit(d, title, "hand", 64 * u, int(24 * u), int(9 * u))
    d.text((P.W / 2, P.H / 2 - 2 * u), title, font=f, fill=P.ink, anchor="ms")
    sub = str(year) if month else "my year"
    d.text((P.W / 2, P.H / 2 + 7 * u), sub, font=DF.get("hand", 7 * u), fill=P.soft, anchor="ms")
    P.line(d, 30 * u, P.H / 2 + 10 * u, 70 * u, P.H / 2 + 10 * u, col=P.soft)
    if name:
        d.text((P.W / 2, P.H / 2 + 14 * u), name.upper(), font=P.f("sans_bold", 1.8), fill=P.soft, anchor="ms")
    return im


def p_calendar(P, month, year, start=6):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, MONTHS[month - 1], f"{year} · monthly calendar", 1)
    x0, x1, y0 = 8 * u, P.W - 8 * u, 21 * u
    cw = (x1 - x0) / 7
    cal = calendar.Calendar(firstweekday=start).monthdayscalendar(year, month)
    rows = len(cal)
    y1 = P.H - 22 * u
    rh = (y1 - y0 - 4 * u) / rows
    days = DAYS[start % 7:] + DAYS[:start % 7] if start != 6 else DAYS
    for i, dn in enumerate(days):
        d.text((x0 + cw * i + cw / 2, y0 + 2.6 * u), dn, font=P.f("sans_bold", 1.8), fill=P.ink, anchor="ms")
    for r, week in enumerate(cal):
        for i, day in enumerate(week):
            bx, by = x0 + cw * i, y0 + 4 * u + rh * r
            if day and P.colour and i in (0, 6):
                d.rectangle((bx, by, bx + cw, by + rh), fill=_tint(P.c(2), 0.85))
            if day:
                d.text((bx + 1.2 * u, by + 2.8 * u), str(day), font=P.f("sans", 1.7), fill=P.ink)
    for r in range(rows + 1):
        P.line(d, x0, y0 + 4 * u + rh * r, x1, y0 + 4 * u + rh * r)
    for i in range(8):
        P.line(d, x0 + cw * i, y0 + 4 * u, x0 + cw * i, y1)
    _lines_box(P, im, d, "notes", 8 * u, y1 + 2 * u, P.W - 8 * u, P.H - 6 * u, 3)
    return im


def _lines_box(P, im, d, label, x0, y0, x1, y1, n, k=0):
    u = P.u
    P.highlight(im, (x0, y0, x0 + d.textlength(label, font=DF.get("hand", 3.6 * u)) + 2 * u, y0 + 4 * u), k)
    d = ImageDraw.Draw(im)
    d.text((x0 + u, y0 + 3.2 * u), label, font=DF.get("hand", 3.6 * u), fill=P.ink, anchor="ls")
    top = y0 + 5.5 * u
    step = (y1 - top) / max(1, n)
    for i in range(1, n + 1):
        P.line(d, x0, top + step * i, x1, top + step * i, col=P.soft, w=max(2, P.lw // 2))
    return d


def p_goals(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Month at a glance", f"{MONTHS[month - 1]} {year}", 2)
    mid = P.W / 2
    d = _lines_box(P, im, d, "goals", 8 * u, 21 * u, mid - 2 * u, 58 * u, 9, 0)
    d = _lines_box(P, im, d, "important dates", mid + 2 * u, 21 * u, P.W - 8 * u, 58 * u, 9, 1)
    d = _lines_box(P, im, d, "to do", 8 * u, 62 * u, mid - 2 * u, P.H - 8 * u, 16, 2)
    for i in range(16):
        y = 62 * u + 5.5 * u + (P.H - 8 * u - 67.5 * u) / 16 * (i + 1) - 2.6 * u
        P.rect(d, 8.6 * u, y, 10.4 * u, y + 1.8 * u, w=max(2, P.lw // 2))
    d = _lines_box(P, im, d, "looking forward to", mid + 2 * u, 62 * u, P.W - 8 * u, P.H - 38 * u, 7, 3)
    P.doodle(im, 5, mid + (P.W / 2 - 6 * u) / 2 + 2 * u, P.H - 22 * u, 22 * u)
    return im


def p_habits(P, month, year, habits):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Habit tracker", f"{MONTHS[month - 1]} {year}", 3)
    nd = calendar.monthrange(year, month)[1]
    x0, y0, x1 = 8 * u, 21 * u, P.W - 8 * u
    lab_w = 22 * u
    cw = (x1 - x0 - lab_w) / nd
    rh = (P.H - 14 * u - y0 - 3 * u) / len(habits)
    for i in range(nd):
        d.text((x0 + lab_w + cw * i + cw / 2, y0 + 2 * u), str(i + 1), font=P.f("sans", 1.1), fill=P.soft, anchor="ms")
    for r, h in enumerate(habits):
        y = y0 + 3 * u + rh * r
        if P.colour:
            d.rectangle((x0, y, x0 + lab_w, y + rh), fill=_tint(P.c(r), 0.8))
        d.text((x0 + u, y + rh / 2), h, font=DF.fit(d, h, "hand", lab_w - 2 * u, int(3.2 * u), int(1.6 * u)),
               fill=P.ink, anchor="lm")
    for r in range(len(habits) + 1):
        P.line(d, x0, y0 + 3 * u + rh * r, x1, y0 + 3 * u + rh * r, w=max(2, P.lw // 2))
    for i in range(nd + 1):
        P.line(d, x0 + lab_w + cw * i, y0 + 3 * u, x0 + lab_w + cw * i, y0 + 3 * u + rh * len(habits),
               w=max(1, P.lw // 3), col=P.soft)
    P.line(d, x0, y0 + 3 * u, x0, y0 + 3 * u + rh * len(habits))
    return im


def p_mood(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Mood tracker", f"{MONTHS[month - 1]} {year}", 4)
    nd = calendar.monthrange(year, month)[1]
    cx, cy, R, r0 = P.W / 2, 52 * u * P.H / P.W * 0.71, 36 * u, 11 * u
    cy = 21 * u + R + 4 * u
    for i in range(nd):
        a = -math.pi / 2 + 2 * math.pi * i / nd
        P.line(d, cx + math.cos(a) * r0, cy + math.sin(a) * r0, cx + math.cos(a) * R, cy + math.sin(a) * R,
               w=max(2, P.lw // 2))
        am = a + math.pi / nd
        d.text((cx + math.cos(am) * (R + 2.6 * u), cy + math.sin(am) * (R + 2.6 * u)), str(i + 1),
               font=P.f("sans", 1.3), fill=P.soft, anchor="mm")
    for rr in (r0, R):
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=P.ink, width=P.lw)
    P.doodle(im, 6, cx, cy, r0 * 1.5)
    moods = ["happy", "calm", "productive", "tired", "anxious", "sad"]
    ly = cy + R + 9 * u
    for i, m in enumerate(moods):
        x = 10 * u + (i % 3) * 28 * u
        y = ly + (i // 3) * 7 * u
        d.ellipse((x, y, x + 4 * u, y + 4 * u), outline=P.ink, width=P.lw,
                  fill=_tint(P.c(i), 0.35) if P.colour else None)
        d.text((x + 6 * u, y + 2 * u), m, font=DF.get("hand", 3.4 * u), fill=P.ink, anchor="lm")
    return im


def p_sleep_water(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Sleep & water", f"{MONTHS[month - 1]} {year}", 5)
    nd = calendar.monthrange(year, month)[1]
    x0, y0, x1 = 8 * u, 22 * u, 60 * u
    hours = ["8p", "", "10p", "", "12a", "", "2a", "", "4a", "", "6a", "", "8a", "", "10a"]
    cw = (x1 - x0 - 5 * u) / len(hours)
    rh = (P.H - 8 * u - y0 - 3 * u) / nd
    for i, h in enumerate(hours):
        if h:
            d.text((x0 + 5 * u + cw * i, y0 + 1.5 * u), h, font=P.f("sans", 1.1), fill=P.soft, anchor="ms")
    for r in range(nd):
        y = y0 + 3 * u + rh * r
        d.text((x0 + 2.4 * u, y + rh / 2), str(r + 1), font=P.f("sans", 1.15), fill=P.soft, anchor="mm")
        if P.colour and r % 2 == 0:
            d.rectangle((x0 + 5 * u, y, x1, y + rh), fill=_tint(P.c(1), 0.9))
    for i in range(len(hours) + 1):
        P.line(d, x0 + 5 * u + cw * i, y0 + 3 * u, x0 + 5 * u + cw * i, y0 + 3 * u + rh * nd, w=1, col=P.soft)
    for r in range(nd + 1):
        P.line(d, x0 + 5 * u, y0 + 3 * u + rh * r, x1, y0 + 3 * u + rh * r, w=max(1, P.lw // 3), col=P.soft)
    # water: 8 glasses a day
    wx = 66 * u
    d.text((wx, y0 + 1.5 * u), "water", font=DF.get("hand", 3.2 * u), fill=P.ink, anchor="ls")
    for r in range(nd):
        y = y0 + 3 * u + rh * r + rh * 0.18
        for k in range(8):
            gx = wx + k * 3.3 * u
            g = (gx, y, gx + 2.3 * u, y + rh * 0.64)
            d.polygon([(g[0], g[1]), (g[2], g[1]), (g[2] - 0.35 * u, g[3]), (g[0] + 0.35 * u, g[3])],
                      outline=P.ink, fill=_tint(P.c(3), 0.75) if P.colour and k < 2 else None)
    return im


def p_week(P, days, year, k):
    im, d = P.new()
    u = P.u
    a, b = days[0], days[-1]
    sub = f"{MONTHS[a.month - 1][:3]} {a.day} – {MONTHS[b.month - 1][:3]} {b.day}, {b.year}"
    d = P.header(im, d, "This week", sub, 7 + k)
    x0, y0 = 8 * u, 21 * u
    bw, bh = (P.W - 16 * u - 3 * u) / 2, (P.H - 8 * u - y0 - 3 * 3 * u) / 4
    for i, day in enumerate(days[:7]):
        c, r = i % 2, i // 2
        bx, by = x0 + c * (bw + 3 * u), y0 + r * (bh + 3 * u)
        P.rect(d, bx, by, bx + bw, by + bh, fill=_tint(P.c(i), 0.88) if P.colour else None)
        d.text((bx + 1.5 * u, by + 4 * u), day.strftime("%A"), font=DF.get("hand", 3.6 * u), fill=P.ink, anchor="ls")
        d.text((bx + bw - 1.5 * u, by + 4 * u), str(day.day), font=P.f("sans_bold", 2), fill=P.soft, anchor="rs")
        for j in range(1, 6):
            yy = by + 4 * u + (bh - 5 * u) / 6 * j + u
            P.line(d, bx + 1.5 * u, yy, bx + bw - 1.5 * u, yy, w=max(1, P.lw // 3), col=P.soft)
    bx, by = x0 + bw + 3 * u, y0 + 3 * (bh + 3 * u)
    d = _lines_box(P, im, d, "notes", bx, by, bx + bw, by + bh - 9 * u, 2, k)
    P.doodle(im, 8 + k, bx + bw * 0.75, by + bh - 6 * u, 11 * u)
    return im


def p_gratitude(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Gratitude log", f"{MONTHS[month - 1]} {year}", 9)
    nd = calendar.monthrange(year, month)[1]
    y0 = 21 * u
    rh = (P.H - 8 * u - y0) / nd
    for i in range(nd):
        y = y0 + rh * (i + 1)
        d.text((9 * u, y - rh * 0.25), f"{i + 1}", font=P.f("sans", 1.3), fill=P.soft, anchor="ls")
        P.line(d, 13 * u, y, P.W - 8 * u, y, w=max(1, P.lw // 3), col=P.soft)
    return im


def p_expenses(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Expenses", f"{MONTHS[month - 1]} {year}", 10)
    cols = [("date", 0.13), ("item", 0.47), ("category", 0.22), ("amount", 0.18)]
    x0, x1, y0 = 8 * u, P.W - 8 * u, 21 * u
    tw = x1 - x0
    budget_h = 12 * u
    P.rect(d, x0, y0, x1, y0 + budget_h, fill=_tint(P.c(0), 0.85) if P.colour else None)
    for i, t in enumerate(("budget", "spent", "left")):
        bx = x0 + tw / 3 * i
        d.text((bx + 2 * u, y0 + 4.5 * u), t, font=DF.get("hand", 3.4 * u), fill=P.ink, anchor="ls")
        if i:
            P.line(d, bx, y0, bx, y0 + budget_h, w=max(2, P.lw // 2))
    ty = y0 + budget_h + 4 * u
    x = x0
    for name, w in cols:
        d.text((x + u, ty + 3 * u), name, font=P.f("sans_bold", 1.5), fill=P.ink, anchor="ls")
        x += tw * w
    rows = 26
    rh = (P.H - 8 * u - ty - 5 * u) / rows
    for r in range(rows + 1):
        y = ty + 5 * u + rh * r
        P.line(d, x0, y, x1, y, w=max(1, P.lw // 3), col=P.soft if r else P.ink)
    x = x0
    for _, w in cols[:-1]:
        x += tw * w
        P.line(d, x, ty, x, ty + 5 * u + rh * rows, w=max(1, P.lw // 3), col=P.soft)
    return im


def p_reading(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Reading log", f"{MONTHS[month - 1]} {year}", 11)
    x0, y0 = 8 * u, 21 * u
    bw, bh = (P.W - 16 * u - 3 * u) / 2, (P.H - 8 * u - y0 - 3 * 2 * u) / 3
    for i in range(6):
        c, r = i % 2, i // 2
        bx, by = x0 + c * (bw + 3 * u), y0 + r * (bh + 3 * u)
        P.rect(d, bx, by, bx + bw * 0.34, by + bh, fill=_tint(P.c(i), 0.75) if P.colour else None)
        for j, lab in enumerate(("title", "author", "started", "finished")):
            yy = by + 4 * u + j * 5.4 * u
            d.text((bx + bw * 0.38, yy), lab, font=P.f("sans", 1.25), fill=P.soft, anchor="ls")
            P.line(d, bx + bw * 0.38, yy + 1.8 * u, bx + bw, yy + 1.8 * u, w=1, col=P.soft)
        for s in range(5):
            sx, sy = bx + bw * 0.4 + s * 4 * u, by + bh - 4 * u
            pts = [(sx + math.cos(-math.pi / 2 + q * math.pi / 5) * (1.5 * u if q % 2 == 0 else 0.65 * u),
                    sy + math.sin(-math.pi / 2 + q * math.pi / 5) * (1.5 * u if q % 2 == 0 else 0.65 * u)) for q in range(10)]
            d.polygon(pts, outline=P.ink)
    return im


def p_selfcare(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Self-care & brain dump", f"{MONTHS[month - 1]} {year}", 0)
    ideas = ["long walk", "early night", "read a book", "call a friend", "bubble bath", "no-phone hour",
             "stretch", "cook something new", "declutter a drawer", "journal", "fresh air", "say no"]
    if P.colour:
        d.rectangle((8 * u, 21 * u, P.W - 8 * u, 50 * u), fill=_tint(P.c(5), 0.88))
    for i, t in enumerate(ideas):
        x = 10 * u + (i % 2) * 41 * u
        y = 24 * u + (i // 2) * 4.4 * u
        P.rect(d, x, y, x + 2.2 * u, y + 2.2 * u, w=max(2, P.lw // 2))
        d.text((x + 4 * u, y + 1.4 * u), t, font=DF.get("hand", 3.2 * u), fill=P.ink, anchor="lm")
    d = _lines_box(P, im, d, "brain dump", 8 * u, 54 * u, P.W - 8 * u, P.H - 8 * u, 20, 1)
    return im


def p_memories(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Memories", f"{MONTHS[month - 1]} {year} highlights", 1)
    for i in range(4):
        c, r = i % 2, i // 2
        bx, by = 10 * u + c * 42 * u, 22 * u + r * 52 * u * P.H / P.W / 1.414
        w, h = 36 * u, 40 * u
        rot = Image.new("RGBA", (int(w + 4 * u), int(h + 4 * u)), (0, 0, 0, 0))
        dd = ImageDraw.Draw(rot)
        dd.rectangle((2 * u, 2 * u, w + 2 * u, h + 2 * u), fill=(255, 255, 255), outline=P.ink, width=P.lw)
        dd.rectangle((4.5 * u, 4.5 * u, w - 0.5 * u, h - 7 * u), outline=P.soft, width=max(2, P.lw // 2),
                     fill=_tint(P.c(i), 0.85) if P.colour else None)
        rot = rot.rotate(P.rnd.uniform(-5, 5), expand=True, resample=Image.BICUBIC)
        im.paste(rot, (int(bx), int(by)), rot)
    d = ImageDraw.Draw(im)
    P.doodle(im, 3, P.W - 16 * u, P.H - 14 * u, 14 * u)
    return im


def p_review(P, month, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Month review", f"{MONTHS[month - 1]} {year}", 2)
    qs = ["best moment", "what I learned", "proud of", "let go of", f"next month I want to"]
    top = 21 * u
    h = (P.H - 8 * u - top) / len(qs)
    for i, q in enumerate(qs):
        d = _lines_box(P, im, d, q, 8 * u, top + h * i, P.W - 8 * u, top + h * (i + 1) - 2 * u, 3, i)
    return im


def p_dots(P, title, sub, k):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, title, sub, k)
    step = 2.4 * u
    y = 21 * u
    while y < P.H - 7 * u:
        x = 8 * u
        while x < P.W - 7.5 * u:
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=P.soft)
            x += step
        y += step
    return im


def p_year_pixels(P, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Year in pixels", str(year), 3)
    x0, y0 = 14 * u, 24 * u
    cw, rh = (P.W - 8 * u - x0) / 12, (P.H - 22 * u - y0) / 31
    for m in range(12):
        d.text((x0 + cw * m + cw / 2, y0 - u), MONTHS[m][0], font=P.f("sans_bold", 1.6), fill=P.ink, anchor="ms")
        nd = calendar.monthrange(year, m + 1)[1]
        for r in range(31):
            if r < nd:
                P.rect(d, x0 + cw * m + 0.4 * u, y0 + rh * r + 0.2 * u, x0 + cw * (m + 1) - 0.4 * u,
                       y0 + rh * (r + 1) - 0.2 * u, w=max(1, P.lw // 3), col=P.soft)
    for r in range(31):
        d.text((x0 - 2 * u, y0 + rh * r + rh / 2), str(r + 1), font=P.f("sans", 1.15), fill=P.soft, anchor="rm")
    for i, m in enumerate(["amazing", "good", "okay", "tired", "bad"]):
        x = 10 * u + i * 17 * u
        d.ellipse((x, P.H - 15 * u, x + 3 * u, P.H - 12 * u), outline=P.ink, width=P.lw,
                  fill=_tint(P.c(i), 0.35) if P.colour else None)
        d.text((x + 4 * u, P.H - 13.5 * u), m, font=DF.get("hand", 3 * u), fill=P.ink, anchor="lm")
    return im


def p_year_glance(P, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, f"{year} at a glance", "yearly calendar", 4)
    x0, y0 = 8 * u, 21 * u
    bw, bh = (P.W - 16 * u - 4 * u) / 3, (P.H - 8 * u - y0 - 3 * 3 * u) / 4
    for m in range(12):
        c, r = m % 3, m // 3
        bx, by = x0 + c * (bw + 2 * u), y0 + r * (bh + 3 * u)
        if P.colour:
            d.rectangle((bx, by, bx + bw, by + 4.5 * u), fill=_tint(P.c(m), 0.7))
        d.text((bx + bw / 2, by + 3.4 * u), MONTHS[m], font=DF.get("hand", 3.4 * u), fill=P.ink, anchor="ms")
        cw = bw / 7
        for i, dn in enumerate(DAYS):
            d.text((bx + cw * i + cw / 2, by + 7 * u), dn, font=P.f("sans_bold", 1.1), fill=P.soft, anchor="ms")
        for rr, week in enumerate(calendar.Calendar(6).monthdayscalendar(year, m + 1)):
            for i, day in enumerate(week):
                if day:
                    d.text((bx + cw * i + cw / 2, by + 10 * u + rr * 2.6 * u), str(day), font=P.f("sans", 1.15),
                           fill=P.ink, anchor="ms")
    return im


def p_year_goals(P, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, f"{year} goals", "dream big, start small", 5)
    areas = ["health", "money", "home", "career", "relationships", "fun & travel"]
    top = 21 * u
    bw, bh = (P.W - 16 * u - 3 * u) / 2, (P.H - 8 * u - top - 2 * 3 * u) / 3
    for i, a in enumerate(areas):
        c, r = i % 2, i // 2
        bx, by = 8 * u + c * (bw + 3 * u), top + r * (bh + 3 * u)
        d = _lines_box(P, im, d, a, bx, by, bx + bw, by + bh, 5, i)
    return im


def p_birthdays(P, year):
    im, d = P.new()
    u = P.u
    d = P.header(im, d, "Birthdays", f"{year} · never forget again", 6)
    top = 21 * u
    bw, bh = (P.W - 16 * u - 4 * u) / 3, (P.H - 8 * u - top - 3 * 3 * u) / 4
    for m in range(12):
        c, r = m % 3, m // 3
        bx, by = 8 * u + c * (bw + 2 * u), top + r * (bh + 3 * u)
        P.rect(d, bx, by, bx + bw, by + bh, fill=_tint(P.c(m), 0.88) if P.colour else None)
        d.text((bx + 1.4 * u, by + 3.6 * u), MONTHS[m], font=DF.get("hand", 3.3 * u), fill=P.ink, anchor="ls")
        for j in range(1, 6):
            yy = by + 4.5 * u + (bh - 5.5 * u) / 5 * j
            P.line(d, bx + 1.4 * u, yy, bx + bw - 1.4 * u, yy, w=1, col=P.soft)
    return im


HABITS = ["8 glasses water", "move 30 min", "read 20 min", "sleep by 11", "no spend", "journal", "vitamins",
          "fresh air", "stretch", "skincare", "tidy 10 min", "screen-free hour"]


def month_pages(P, month, year, name, hemi, with_cover=True):
    pages = [("cover", p_cover(P, month, year, name, hemi))] if with_cover else []
    pages += [("calendar", p_calendar(P, month, year)), ("glance", p_goals(P, month, year)),
              ("habits", p_habits(P, month, year, HABITS)), ("mood", p_mood(P, month, year)),
              ("sleep", p_sleep_water(P, month, year))]
    first = dt.date(year, month, 1)
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)  # weeks start on Sunday
    k = 0
    while start.month == month or start < first:
        days = [start + dt.timedelta(days=i) for i in range(7)]
        pages.append((f"week{k + 1}", p_week(P, days, year, k)))
        start += dt.timedelta(days=7)
        k += 1
        if start.month != month and start > first:
            break
    pages += [("gratitude", p_gratitude(P, month, year)), ("expenses", p_expenses(P, month, year)),
              ("reading", p_reading(P, month, year)), ("selfcare", p_selfcare(P, month, year)),
              ("memories", p_memories(P, month, year)), ("notes", p_dots(P, "Notes", f"{MONTHS[month - 1]} {year}", 6)),
              ("review", p_review(P, month, year))]
    return pages


def year_pages(P, year, name):
    return [("cover", p_cover(P, None, year, name, "north")), ("glance", p_year_glance(P, year)),
            ("goals", p_year_goals(P, year)), ("pixels", p_year_pixels(P, year)), ("birthdays", p_birthdays(P, year)),
            ("books", p_dots(P, "Books to read", str(year), 7)), ("bucket", p_dots(P, "Bucket list", str(year), 8))]


PT = {"A4": (595.28, 841.89), "A5": (419.53, 595.28), "US-Letter": (612.0, 792.0)}
KEEP = ("cover", "calendar", "glance", "habits", "mood", "week1", "memories", "year-glance", "year-pixels")


def _png(im, colors=32):
    """Page as a small indexed PNG (line art + soft fills compress ~6x better than JPEG and stay crisp)."""
    b = io.BytesIO()
    im.quantize(colors, dither=Image.Dither.NONE).save(b, "PNG", optimize=True)
    return b.getvalue()


def _png_parts(data):
    import struct
    pos, ihdr, plte, idat = 8, None, b"", []
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if typ == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"IDAT":
            idat.append(body)
        pos += 12 + n
    return ihdr, plte, b"".join(idat)


def _pdf(pngs, pagesize):
    """A PDF with one indexed PNG per page, the PNG data embedded as it is (no re-encoding, tiny memory).
    The same page images fill an A4 or an A5 page (same shape), so A5 costs no extra drawing."""
    out = io.BytesIO()
    offs = []

    def obj(body, stream=None):
        offs.append(out.tell())
        out.write(f"{len(offs)} 0 obj\n".encode() + body)
        if stream is not None:
            out.write(b"\nstream\n" + stream + b"\nendstream")
        out.write(b"\nendobj\n")
        return len(offs)

    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    pw, ph = pagesize
    n = len(pngs)
    # object numbers: 1 catalog, 2 pages, then per page: image, content, page
    page_ids = [3 + i * 3 + 2 for i in range(n)]
    obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    obj(f"<< /Type /Pages /Count {n} /Kids [{' '.join(f'{k} 0 R' for k in page_ids)}] >>".encode())
    for i, png in enumerate(pngs):
        (w, h, bd, ct, _, _, _), plte, idat = _png_parts(png)
        if ct == 3:
            cs = f"[/Indexed /DeviceRGB {len(plte) // 3 - 1} <{plte.hex()}>]"
            colors = 1
        elif ct == 0:
            cs, colors = "/DeviceGray", 1
        else:
            cs, colors = "/DeviceRGB", 3
        img = obj(f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace {cs} /BitsPerComponent {bd} "
                  f"/Filter /FlateDecode /DecodeParms << /Predictor 15 /Colors {colors} /BitsPerComponent {bd} /Columns {w} >> "
                  f"/Length {len(idat)} >>".encode(), idat)
        content = f"q {pw:.2f} 0 0 {ph:.2f} 0 0 cm /Im0 Do Q".encode()
        cid = obj(f"<< /Length {len(content)} >>".encode(), content)
        obj(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.2f} {ph:.2f}] /Resources << /XObject << /Im0 {img} 0 R >> >> "
            f"/Contents {cid} 0 R >>".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(offs) + 1}\n0000000000 65535 f \n".encode())
    for o in offs:
        out.write(f"{o:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(offs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _fit_pdf(pngs, pagesize, limit=18.5e6):
    """Etsy allows 20 MB per file: if a PDF is too big, the pages are stored with fewer colours."""
    pdf = _pdf(pngs, pagesize)
    for colors in (16, 8):
        if len(pdf) <= limit:
            break
        print(f"[journal] PDF {len(pdf) / 1e6:.1f} MB, {colors} renk ile küçültülüyor")
        pngs = [_png(Image.open(io.BytesIO(p)).convert("RGB"), colors) for p in pngs]
        pdf = _pdf(pngs, pagesize)
    return pdf


def render(spec, doodles, pal, colour, scale=1.0):
    """Draws every page once per paper shape (A4/A5 share one shape) and keeps only JPEG bytes in memory.
    Returns ({"A4": [jpeg], "US-Letter": [jpeg]}, {page name: small PIL copy for the listing photos}, page count)."""
    out, kept = {}, {}
    name = spec.get("journal_name", "")
    for label, size in (("A4", A4), ("US-Letter", LETTER)):
        P = Pen((int(size[0] * scale), int(size[1] * scale)), pal, colour, name or "j", doodles)
        chunks = []
        if spec["scope"] == "year":
            chunks.append(lambda: [(f"year-{n}", im) for n, im in year_pages(P, spec["year"], name)])
            for m in spec["months"]:
                chunks.append(lambda m=m: [(f"{MONTHS[m - 1].lower()}-{n}", im)
                                           for n, im in month_pages(P, m, spec["year"], name, spec["hemisphere"])])
        else:
            chunks.append(lambda: month_pages(P, spec["months"][0], spec["year"], name, spec["hemisphere"]))
        jpgs = []
        for ch in chunks:
            for n, im in ch():
                jpgs.append(_png(im))
                if label == "A4" and (n in KEEP or n.startswith("year-") or
                                      n.startswith("january-") and n.split("-", 1)[1] in KEEP):
                    small = im.copy()
                    small.thumbnail((1400, 1980), Image.LANCZOS)
                    kept[n] = small
                im.close()
        out[label] = jpgs
    return out, kept, len(out["A4"])


# ---------------------------------------------------------------- build
def build(spec, slug):
    spec.setdefault("scope", "month")
    spec.setdefault("year", dt.date.today().year)
    spec.setdefault("months", [spec.get("month") or dt.date.today().month % 12 + 1])
    spec.setdefault("variant", "colour")
    spec.setdefault("hemisphere", "north")
    pal = [hex2rgb(c) for c in spec.get("palette", [])][:6] or [(176, 132, 112), (132, 154, 128), (196, 170, 120)]
    while len(pal) < 6:
        pal.append(tuple(int(v * 0.85) for v in pal[len(pal) % 3]))
    doodles = []
    for i, t in enumerate(spec.get("doodles", [])[:N_DOODLES]):
        raw = images.try_generate(f"{t['prompt']}, {SUFFIX}", 768, 768)
        if raw is None and images.quota_exhausted():
            break
        if raw is not None:
            doodles.append(_doodle_pair(raw, pal, i))
    images.need(len(doodles), N_DOODLES, ratio=0.5)

    year_scope = spec["scope"] == "year"
    versions = [("Pre-Colored", True), ("Black-and-White", False)] if spec["variant"] == "colour" else [("Black-and-White", False)]
    scale = 1.0
    files, shown, n_pages = [], {}, 0
    base = (f"{spec['year']}-Journal" if year_scope else f"{MONTHS[spec['months'][0] - 1]}-{spec['year']}-Journal")
    for label, colour in versions:
        jp, kept, n_pages = render(spec, doodles, pal, colour, scale)
        files.append((f"{base}-{label}-A4.pdf", _fit_pdf(jp["A4"], PT["A4"])))
        if colour or not year_scope:  # Etsy allows 5 files: the year bundle's B&W version comes in A4 + Letter
            files.append((f"{base}-{label}-A5.pdf", _fit_pdf(jp["A4"], PT["A5"])))
        files.append((f"{base}-{label}-US-Letter.pdf", _fit_pdf(jp["US-Letter"], PT["US-Letter"])))
        shown[colour] = list(kept.items())
        del jp
    readme = (f"{spec['title']}\n\nThank you for your purchase!\n\n"
              f"- {n_pages} printable bullet journal pages" + (" (pre-colored + black and white versions)" if len(versions) > 1 else "") + "\n"
              "- Sizes: A4, A5 and US Letter (one PDF per size)\n\n"
              "Printing: open the PDF, choose the size you need, print at 100% / actual size. A5 pages can be printed "
              "two per A4 sheet. Works for ring binders, discbound and traveler's notebooks.\n"
              "Digital use: you can also import the PDF into a note-taking app.\n\n"
              "Personal use only. Please do not share or resell the files.\n")
    delivery = make_zips(slug, files, readme)

    # ---- photos
    hexpal = ["#%02x%02x%02x" % c for c in pal]
    main = shown.get(True) or shown[False]
    other = shown.get(False) if True in shown else None

    def get(key):
        return next((im for n, im in main if n.endswith(key)), main[0][1])
    thumbs = [im.copy() for _, im in main]
    for t in thumbs:
        t.thumbnail((700, 990))
    name_word = (f"{spec['year']} JOURNAL" if year_scope else f"{MONTHS[spec['months'][0] - 1].upper()} {spec['year']}")
    cover_items = [get("cover"), get("calendar"), get("mood"), get("habits"), get("week1"), get("memories")]
    mock = [
        ("01-bundle.jpg", bundle_cover(cover_items + thumbs, n_pages, "JOURNAL PAGES", spec.get("journal_name", ""), hexpal,
                                       bundle_word=name_word[:22], ribbon="PRINTABLE",
                                       sticker=("A4", "A5", "LETTER"),
                                       features=["DATED PAGES", "TRACKERS", "A4 · A5 · LETTER"])),
        ("02-spread.jpg", _spread(get("calendar"), get("glance"), pal)),
        ("03-inside.jpg", mockups.grid(thumbs[:12], f"{n_pages} Pages Inside", hexpal, cols=4)),
        ("04-trackers.jpg", _spread(get("mood"), get("habits"), pal)),
        ("05-week.jpg", _spread(get("week1"), get("memories"), pal)),
    ]
    if other:
        mock.append(("06-versions.jpg", _versions(get("cover"), next((im for n, im in other if n.endswith("mood")), other[0][1]), pal)))
    mock.append(("07-sizes.jpg", mockups.info_card("PRINT AT HOME", ["A4, A5 and US Letter PDFs", "Print at actual size",
                                                                      "Binder, discbound or notebook"], hexpal, get("calendar"))))
    mock.append(("08-how.jpg", mockups.how_it_works(hexpal)))
    if year_scope:
        mock.insert(2, ("02b-year.jpg", _spread(get("year-glance"), get("year-pixels"), pal)))
    mock = mock[:10]
    months_txt = "all 12 months" if year_scope else MONTHS[spec["months"][0] - 1]
    return {
        "delivery": delivery,
        "mockups": [(nm, jpeg_bytes(im, 88, dpi=72)) for nm, im in mock],
        "thumb": thumb_b64(mock[0][1]),
        "preview": mock[0][1],
        "included": [f"{n_pages} printable journal pages ({months_txt} {spec['year']}, dated)"]
                    + (["Pre-colored version + black and white version"] if len(versions) > 1 else ["Black and white, color it yourself"])
                    + ["A4, A5 and US Letter PDFs", "Delivered as ZIP"],
        "details": ["Calendar, weekly spreads, habit / mood / sleep / water trackers, gratitude, expenses, reading log, memories, review"]
                   + (["Southern Hemisphere seasons"] if spec["hemisphere"] == "south" else []),
        "usage": ["Print at home or at a print shop at actual size", "A5: print two per A4 sheet and cut",
                  "Also works as a PDF in note-taking apps"],
        "license": "Personal use only. Please do not share or resell the files.",
        "taxonomy": ["Planners & Stickers", "Calendars & Planners", "Digital Prints"],
        "taxonomy_fallback_id": 6844,
        "is_supply": False,
        "skip_attributes": ["room"],
        "count": n_pages,
        "cover_items": cover_items,
        "cover_unit": "PAGES",
        "cover_kicker": f"{name_word.title()} · printable journal",
        "cover_features": ["Dated pages", "Habit & mood trackers", "A4 · A5 · Letter",
                           "Pre-colored + B&W" if len(versions) > 1 else "Color it yourself"],
    }


def _bg(pal, size=(2400, 1800)):
    bg = Image.new("RGB", size, _tint(pal[0], 0.82))
    d = ImageDraw.Draw(bg)
    rnd = random.Random(1)
    for _ in range(40):
        x, y, r = rnd.randrange(size[0]), rnd.randrange(size[1]), rnd.randrange(4, 10)
        d.ellipse((x - r, y - r, x + r, y + r), fill=_tint(pal[1], 0.6))
    return bg


def _paper(im, h):
    p = im.copy()
    p.thumbnail((int(h / 1.414) + 10, h), Image.LANCZOS)
    return p


def _spread(a, b, pal):
    bg = _bg(pal)
    for i, pg in enumerate((a, b)):
        p = _paper(pg, 1500)
        x = 1200 - p.width - 30 if i == 0 else 1230
        y = 150
        sh = Image.new("RGBA", (p.width + 80, p.height + 80), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((40, 50, p.width + 40, p.height + 50), fill=(0, 0, 0, 70))
        sh = sh.filter(ImageFilter.GaussianBlur(18))
        bg.paste(sh, (x - 40, y - 40), sh)
        bg.paste(p, (x, y))
    return bg


def _versions(colour_page, bw_page, pal):
    bg = _bg(pal)
    d = ImageDraw.Draw(bg)
    for i, (pg, t) in enumerate(((colour_page, "PRE-COLORED"), (bw_page, "BLACK & WHITE"))):
        p = _paper(pg, 1350)
        x = 1200 - p.width - 60 if i == 0 else 1260
        bg.paste(p, (x, 120))
        f = font("sans_bold", 64)
        d.text((x + p.width / 2, 1620), t, font=f, fill=(60, 60, 60), anchor="ms")
    d.text((1200, 1730), "BOTH VERSIONS INCLUDED", font=font("sans_bold", 44), fill=(90, 90, 90), anchor="ms")
    return bg
