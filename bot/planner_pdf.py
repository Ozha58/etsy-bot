"""Undated, fully hyperlinked digital LIFE planner (iPad / Android, landscape PDF) built with reportlab.

Navigation on every page: top section tabs (Home, Year, Goals, Health, Finance, Life, Notes) and
side month tabs (Jan-Dec). Index page links to everything. Weekly and daily pages have
previous/next buttons. Light and dark mode, Sunday and Monday start. All text is drawn by us."""
import io

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl

from . import config

W, H = 1366, 1024  # 4:3 landscape
TAB_W = 82
TOP_H = 58
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
DAYS_SUN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
DAYS_MON = DAYS_SUN[1:] + DAYS_SUN[:1]
WEEKS = 5
SECTIONS = [("HOME", "index"), ("YEAR", "year"), ("GOALS", "goals"), ("HEALTH", "health"), ("FINANCE", "finance"),
            ("LIFE", "life"), ("NOTES", "notes")]
_FONTS = False


def _fonts():
    global _FONTS
    if _FONTS:
        return
    d = config.FONTS_DIR
    for name, f in (("Sans", "Poppins-Regular.ttf"), ("SansB", "Poppins-Bold.ttf"), ("SansL", "Poppins-Light.ttf"),
                    ("SansM", "Poppins-Medium.ttf"), ("Serif", "Lora-Variable.ttf")):
        try:
            pdfmetrics.registerFont(TTFont(name, str(d / f)))
        except Exception:
            pass
    _FONTS = True


def _rgb(c):
    return tuple(v / 255 for v in c)


def _mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


# Templates: (key, title, section, layout list). Layout items are drawn left->right in two columns.
#   ("lines", label, n)        lined box            ("table", label, [cols], rows)
#   ("check", label, n)        checklist            ("grid", label, cols, rows)   empty box grid with labels
#   ("boxes", [labels])        equal boxes w/ lines ("circles", label, n)        tracker circles (n per row)
TEMPLATES = [
    # YEAR
    ("vision", "Vision Board", "year", [("grid", "", 3, 2)]),
    ("resolutions", "New Year Intentions", "year", [("boxes", ["Health", "Career", "Money", "Relationships", "Growth", "Fun"])]),
    ("bucket", "Bucket List", "year", [("check", "Things I want to do", 16), ("check", "Places I want to see", 16)]),
    ("keydates", "Birthdays & Key Dates", "year", [("table", "", ["Date", "Name / Event", "Gift idea"], 18)]),
    ("q1", "Quarter 1 Review", "year", [("boxes", ["Wins", "Lessons", "Keep doing", "Change", "Focus next", "Notes"])]),
    ("q2", "Quarter 2 Review", "year", [("boxes", ["Wins", "Lessons", "Keep doing", "Change", "Focus next", "Notes"])]),
    ("q3", "Quarter 3 Review", "year", [("boxes", ["Wins", "Lessons", "Keep doing", "Change", "Focus next", "Notes"])]),
    ("q4", "Quarter 4 Review", "year", [("boxes", ["Wins", "Lessons", "Keep doing", "Change", "Focus next", "Notes"])]),
    ("yearreview", "Year in Review", "year", [("boxes", ["Best moments", "Proud of", "Grateful for", "Learned", "Let go of", "Next year"])]),
    # GOALS
    ("lifegoals", "Life Goals", "goals", [("boxes", ["1 year", "3 years", "5 years", "10 years"])]),
    ("goal1", "Goal Planner", "goals", [("lines", "My goal", 3), ("check", "Action steps", 10), ("lines", "Why it matters", 4), ("table", "", ["Milestone", "Deadline", "Done"], 6)]),
    ("goal2", "Goal Planner", "goals", [("lines", "My goal", 3), ("check", "Action steps", 10), ("lines", "Why it matters", 4), ("table", "", ["Milestone", "Deadline", "Done"], 6)]),
    ("goal3", "Goal Planner", "goals", [("lines", "My goal", 3), ("check", "Action steps", 10), ("lines", "Why it matters", 4), ("table", "", ["Milestone", "Deadline", "Done"], 6)]),
    ("challenge30", "30 Day Challenge", "goals", [("lines", "Challenge", 2), ("circles", "Days", 30), ("lines", "Reflection", 6)]),
    ("brain", "Brain Dump", "goals", [("lines", "Everything on my mind", 18)]),
    ("projects", "Project Planner", "goals", [("lines", "Project", 2), ("table", "", ["Task", "Owner", "Due", "Status"], 14)]),
    # HEALTH
    ("workout", "Workout Planner", "health", [("table", "", ["Day", "Workout", "Sets / Reps", "Time", "Done"], 14)]),
    ("fitness", "Fitness Tracker", "health", [("table", "", ["Date", "Weight", "Steps", "Sleep", "Water", "Mood"], 16)]),
    ("meal", "Weekly Meal Planner", "health", [("table", "", ["Day", "Breakfast", "Lunch", "Dinner", "Snacks"], 7), ("check", "Grocery list", 12)]),
    ("grocery", "Grocery List", "health", [("check", "Produce", 10), ("check", "Dairy & eggs", 8), ("check", "Pantry", 10), ("check", "Other", 8)]),
    ("water", "Water & Sleep Tracker", "health", [("circles", "Glasses of water (31 days x 8)", 248), ("circles", "Hours of sleep", 31)]),
    ("selfcare", "Self-Care Checklist", "health", [("check", "Body", 9), ("check", "Mind", 9), ("check", "Soul", 9)]),
    ("cycle", "Cycle Tracker", "health", [("table", "", ["Start", "End", "Length", "Symptoms", "Notes"], 13)]),
    ("meds", "Medication & Vitamins", "health", [("table", "", ["Name", "Dose", "Time", "Notes"], 14)]),
    ("symptoms", "Symptom Log", "health", [("table", "", ["Date", "Symptom", "Severity", "Trigger", "Notes"], 15)]),
    # FINANCE
    ("budgetyear", "Yearly Budget Overview", "finance", [("table", "", ["Month", "Income", "Expenses", "Savings", "Notes"], 12)]),
    ("expenses", "Expense Tracker", "finance", [("table", "", ["Date", "Item", "Category", "Amount"], 18)]),
    ("bills", "Bill Tracker", "finance", [("table", "", ["Bill", "Due", "Amount", "Paid"], 16)]),
    ("subscriptions", "Subscriptions", "finance", [("table", "", ["Service", "Cost", "Renewal", "Keep?"], 16)]),
    ("savings", "Savings Tracker", "finance", [("lines", "Saving for", 2), ("circles", "Color one for every step", 100)]),
    ("debt", "Debt Payoff", "finance", [("table", "", ["Debt", "Balance", "Rate", "Min. payment", "Paid off"], 10), ("circles", "Progress", 50)]),
    ("nospend", "No Spend Challenge", "finance", [("circles", "No spend days", 31), ("lines", "What I saved for", 6)]),
    ("sinking", "Sinking Funds", "finance", [("boxes", ["Fund 1", "Fund 2", "Fund 3", "Fund 4", "Fund 5", "Fund 6"])]),
    # LIFE
    ("todo", "To Do List", "life", [("check", "Today", 14), ("check", "This week", 14)]),
    ("gratitude", "Gratitude Journal", "life", [("lines", "Today I am grateful for", 8), ("lines", "Something good that happened", 8)]),
    ("reading", "Reading Log", "life", [("table", "", ["Title", "Author", "Started", "Finished", "Rating"], 16)]),
    ("travel", "Travel Planner", "life", [("lines", "Destination", 2), ("table", "", ["Day", "Plan", "Booking"], 7), ("check", "Packing list", 12)]),
    ("cleaning", "Cleaning Schedule", "life", [("boxes", ["Daily", "Weekly", "Monthly", "Seasonal"])]),
    ("recipe", "Recipe Card", "life", [("lines", "Recipe", 1), ("check", "Ingredients", 12), ("lines", "Method", 12)]),
    ("meeting", "Meeting Notes", "life", [("lines", "Topic & attendees", 3), ("lines", "Notes", 12), ("check", "Action items", 8)]),
    ("contacts", "Contacts", "life", [("table", "", ["Name", "Phone", "Email", "Birthday"], 16)]),
    ("passwords", "Website Log (hints only)", "life", [("table", "", ["Website", "Username", "Hint"], 16)]),
    ("journal", "Journal", "life", [("lines", "Dear diary", 20)]),
]
PAPERS = ["Lined", "Dotted", "Grid", "Blank", "Cornell", "Lined", "Dotted", "Grid"]


class Planner:
    def __init__(self, title, palette, cover_img, deco, week_start="sun", dark=False):
        _fonts()
        self.title = title
        self.pal = (palette + [(120, 140, 120), (150, 110, 90), (90, 120, 150)])[:6]
        self.dark = dark
        if dark:
            self.paper, self.card, self.ink, self.soft, self.line = (30, 31, 36), (42, 44, 50), (236, 234, 230), (150, 150, 160), (70, 72, 80)
            self.pal = [_mix(c, (255, 255, 255), 0.18) for c in self.pal]
        else:
            self.paper, self.card, self.ink, self.soft, self.line = (251, 250, 247), (255, 255, 255), (52, 52, 58), (140, 140, 150), (214, 214, 220)
        self.cover_img = cover_img
        self.deco = deco
        self.days = DAYS_SUN if week_start == "sun" else DAYS_MON
        self.buf = io.BytesIO()
        self.c = rl.Canvas(self.buf, pagesize=(W, H))
        self.c.setTitle(title)
        self.pages = 0
        self._imgcache = {}

    # ---------- primitives ----------
    def _fill(self, col):
        self.c.setFillColorRGB(*_rgb(col))

    def _stroke(self, col, w=1):
        self.c.setStrokeColorRGB(*_rgb(col))
        self.c.setLineWidth(w)

    def _text(self, x, y, s, font="Sans", size=20, col=None, anchor="l"):
        self._fill(col or self.ink)
        self.c.setFont(font, size)
        {"c": self.c.drawCentredString, "r": self.c.drawRightString}.get(anchor, self.c.drawString)(x, y, s)

    def _img(self, key, im, x, y, w, h):
        if key not in self._imgcache:
            b = io.BytesIO()
            im.save(b, "PNG")
            b.seek(0)
            self._imgcache[key] = ImageReader(b)
        self.c.drawImage(self._imgcache[key], x, y, w, h, mask="auto")

    def _deco(self, i, x, y, size):
        if not self.deco:
            return
        k = i % len(self.deco)
        o = self.deco[k]
        s = size / max(o.width, o.height)
        small = o.copy()
        small.thumbnail((int(size * 2), int(size * 2)), Image.LANCZOS)
        self._img(f"deco{k}", small, x, y, o.width * s, o.height * s)

    def _link(self, key, rect):
        self.c.linkRect("", key, rect, relative=0, thickness=0)

    def _button(self, x, y, w, h, label, key, col, filled=False, arrow=None):
        self._fill(col if filled else self.card)
        self._stroke(col, 1.4)
        self.c.roundRect(x, y, w, h, h / 2, stroke=1, fill=1)
        tc = (255, 255, 255) if filled else col
        if label in ("‹", "›"):
            d = -1 if label == "‹" else 1
            cx, cy = x + w / 2, y + h / 2
            self._stroke(arrow or tc, 3)
            self.c.line(cx - 5 * d, cy + 9, cx + 5 * d, cy)
            self.c.line(cx + 5 * d, cy, cx - 5 * d, cy - 9)
        else:
            self._text(x + w / 2, y + h / 2 - 6, label, "SansB", 15, tc, "c")
        self._link(key, (x, y, x + w, y + h))

    # ---------- navigation ----------
    def _nav(self, section=None, month=None):
        # side month tabs
        x0 = W - TAB_W
        self._fill(_mix(self.paper, self.ink, 0.04))
        self.c.rect(x0, 0, TAB_W, H, stroke=0, fill=1)
        th = (H - TOP_H - 30) / 12
        for i, m in enumerate(MONTHS):
            y = H - TOP_H - 10 - (i + 1) * th
            on = month == i
            col = self.pal[i % len(self.pal)]
            self._fill(col if on else _mix(self.paper, self.ink, 0.09))
            self.c.roundRect(x0 + 8, y + 3, TAB_W - 14, th - 6, 10, stroke=0, fill=1)
            self._text(x0 + TAB_W / 2 + 3, y + th / 2 - 6, m[:3].upper(), "SansB", 15,
                       (255, 255, 255) if on else self.soft, "c")
            self._link(f"m{i}", (x0 + 8, y + 3, x0 + TAB_W - 6, y + th - 3))
        # top section tabs
        tw = (W - TAB_W - 60) / len(SECTIONS)
        for k, (lab, key) in enumerate(SECTIONS):
            x = 30 + k * tw
            on = section == key
            self._fill(self.pal[k % len(self.pal)] if on else _mix(self.paper, self.ink, 0.07))
            self.c.roundRect(x + 4, H - TOP_H + 8, tw - 8, TOP_H - 18, 12, stroke=0, fill=1)
            self._text(x + tw / 2, H - TOP_H + 25, lab, "SansB", 15, (255, 255, 255) if on else self.soft, "c")
            self._link(key, (x + 4, H - TOP_H + 8, x + tw - 4, H - 10))

    def _page(self, key=None, section=None, month=None):
        self._fill(self.paper)
        self.c.rect(0, 0, W, H, stroke=0, fill=1)
        if key:
            self.c.bookmarkPage(key)
        self._nav(section, month)

    def _end(self):
        self.c.showPage()
        self.pages += 1

    def _header(self, title, sub="", col=None, deco_i=0, prev=None, nxt=None):
        col = col or self.pal[0]
        top = H - TOP_H - 12
        self._fill(col)
        self.c.roundRect(30, top - 74, W - TAB_W - 60, 74, 18, stroke=0, fill=1)
        self._text(58, top - 50, title, "Serif", 36, (255, 255, 255))
        right = W - TAB_W - 54
        if nxt:
            self._button(right - 52, top - 56, 52, 38, "›", nxt, (255, 255, 255), False, col)
            right -= 62
        if prev:
            self._button(right - 52, top - 56, 52, 38, "‹", prev, (255, 255, 255), False, col)
            right -= 62
        if sub:
            self._text(right - 6, top - 44, sub, "SansB", 15, (255, 255, 255), "r")
            right -= self.c.stringWidth(sub, "SansB", 15) + 20
        self._deco(deco_i, right - 96, top - 80, 88)
        return top - 96  # content top

    # ---------- content helpers ----------
    def _box(self, x, y, w, h, label=None, col=None):
        self._fill(self.card)
        self._stroke(self.line, 1.2)
        self.c.roundRect(x, y, w, h, 14, stroke=1, fill=1)
        if label:
            self._text(x + 16, y + h - 32, label.upper(), "SansB", 14, col or self.pal[0])
        return y + h - (46 if label else 16)

    def _lines(self, x, y0, y1, w, step=32):
        self._stroke(self.line, 1)
        y = y0 - step
        while y > y1 + 6:
            self.c.line(x, y, x + w, y)
            y -= step

    def _check(self, x, y0, y1, w, n):
        step = min(40, (y0 - y1) / max(1, n))
        for k in range(n):
            y = y0 - (k + 1) * step + 8
            if y < y1:
                break
            self._stroke(self.line, 1.2)
            self.c.roundRect(x, y, 16, 16, 4, stroke=1, fill=0)
            self.c.line(x + 28, y, x + w, y)

    def _table(self, x, y0, y1, w, cols, rows, col):
        rh = min(42, (y0 - y1) / (rows + 1))
        cw = w / len(cols)
        self._fill(_mix(self.card, col, 0.15))
        self.c.rect(x, y0 - rh, w, rh, stroke=0, fill=1)
        for k, c in enumerate(cols):
            self._text(x + k * cw + 12, y0 - rh + 13, c.upper(), "SansB", 13, col)
        self._stroke(self.line, 1)
        for r in range(rows + 1):
            yy = y0 - rh - r * rh
            self.c.line(x, yy, x + w, yy)
        for k in range(1, len(cols)):
            self.c.line(x + k * cw, y0, x + k * cw, y0 - rh * (rows + 1))

    def _circles(self, x, y0, y1, w, n, col):
        per = min(n, 31 if n > 31 else n)
        size = min(30, w / per - 6)
        rows = (n + per - 1) // per
        step_y = min(size + 12, (y0 - y1) / max(rows, 1))
        self._stroke(col, 1.2)
        for k in range(n):
            cx = x + (k % per) * (w / per) + w / per / 2
            cy = y0 - (k // per) * step_y - size / 2 - 4
            if cy < y1:
                break
            self.c.circle(cx, cy, size / 2, stroke=1, fill=0)

    def _layout(self, items, top, col):
        left, right = 40, W - TAB_W - 40
        gap = 22
        if len(items) == 1 or items[0][0] in ("boxes", "grid"):
            areas = [(left, right, top, 40)]
        else:
            mid = (left + right) / 2
            n = len(items)
            if n == 2:
                areas = [(left, mid - gap / 2, top, 40), (mid + gap / 2, right, top, 40)]
            elif n == 3:
                hm = (top + 40) / 2
                areas = [(left, mid - gap / 2, top, 40), (mid + gap / 2, right, top, hm + gap / 2),
                         (mid + gap / 2, right, hm - gap / 2, 40)]
            else:
                hm = (top + 40) / 2
                areas = [(left, mid - gap / 2, top, hm + gap / 2), (mid + gap / 2, right, top, hm + gap / 2),
                         (left, mid - gap / 2, hm - gap / 2, 40), (mid + gap / 2, right, hm - gap / 2, 40)]
        for it, (x0, x1, y0, y1) in zip(items, areas):
            kind = it[0]
            if kind == "boxes":
                labels = it[1]
                cols = 3 if len(labels) > 4 else 2
                rows = (len(labels) + cols - 1) // cols
                bw, bh = (x1 - x0 - gap * (cols - 1)) / cols, (y0 - y1 - gap * (rows - 1)) / rows
                for k, lab in enumerate(labels):
                    bx = x0 + (k % cols) * (bw + gap)
                    by = y0 - (k // cols + 1) * bh - (k // cols) * gap
                    t = self._box(bx, by, bw, bh, lab, self.pal[k % len(self.pal)])
                    self._lines(bx + 16, t, by + 10, bw - 32)
            elif kind == "grid":
                cols, rows = it[2], it[3]
                bw, bh = (x1 - x0 - gap * (cols - 1)) / cols, (y0 - y1 - gap * (rows - 1)) / rows
                for k in range(cols * rows):
                    bx = x0 + (k % cols) * (bw + gap)
                    by = y0 - (k // cols + 1) * bh - (k // cols) * gap
                    self._box(bx, by, bw, bh)
                    self._deco(k, bx + bw / 2 - 40, by + bh / 2 - 40, 80) if k == 0 else None
            else:
                t = self._box(x0, y1, x1 - x0, y0 - y1, it[1] if len(it) > 1 else None, col)
                ix, iw = x0 + 16, x1 - x0 - 32
                if kind == "lines":
                    self._lines(ix, t, y1 + 8, iw)
                elif kind == "check":
                    self._check(ix, t, y1 + 12, iw, it[2])
                elif kind == "table":
                    self._table(ix, t, y1 + 12, iw, it[2], it[3], col)
                elif kind == "circles":
                    self._circles(ix, t, y1 + 12, iw, it[2], col)

    # ---------- pages ----------
    def cover(self):
        self._page("cover")
        art = self.cover_img.convert("RGB")
        aw, ah = W - TAB_W, H - TOP_H
        s = max(aw / art.width, ah / art.height)
        art = art.resize((int(art.width * s), int(art.height * s)), Image.LANCZOS)
        l, t = (art.width - aw) // 2, (art.height - ah) // 2
        self._img("cover", art.crop((l, t, l + aw, t + ah)), 0, 0, aw, ah)
        self._fill(self.card)
        self.c.setFillAlpha(0.92)
        self.c.roundRect(aw / 2 - 380, ah / 2 - 150, 760, 300, 30, stroke=0, fill=1)
        self.c.setFillAlpha(1)
        self._text(aw / 2, ah / 2 + 70, "UNDATED DIGITAL PLANNER", "SansB", 22, self.pal[0], "c")
        size = 50 if len(self.title) <= 24 else 38
        self._text(aw / 2, ah / 2 + 5, self.title, "Serif", size, self.ink, "c")
        self._button(aw / 2 - 110, ah / 2 - 95, 220, 50, "START HERE", "index", self.pal[0], True)
        self._end()

    def index(self):
        self._page("index", "index")
        top = self._header("Index", "tap anything to jump there", self.pal[0], 0)
        groups = [("CALENDAR", [("Year at a Glance", "year")] + [(m, f"m{i}") for i, m in enumerate(MONTHS)])]
        for sec, name in (("year", "YEAR"), ("goals", "GOALS"), ("health", "HEALTH"), ("finance", "FINANCE"), ("life", "LIFE")):
            groups.append((name, [(t[1], t[0]) for t in TEMPLATES if t[2] == sec]))
        groups.append(("NOTES", [(f"{p} paper", f"note{k}") for k, p in enumerate(PAPERS)] + [("Daily pages", "m0w0d0")]))
        cols = len(groups)
        cw = (W - TAB_W - 80) / cols
        for g, (name, items) in enumerate(groups):
            x = 40 + g * cw
            col = self.pal[g % len(self.pal)]
            self._text(x, top - 30, name, "SansB", 18, col)
            step = min(46, (top - 90) / max(len(items), 1))
            for k, (lab, key) in enumerate(items):
                y = top - 78 - k * step
                lab = lab if len(lab) <= 17 else lab[:16] + "…"
                self._text(x, y, lab, "Sans", 16, self.ink)
                self._link(key, (x - 4, y - 8, x + cw - 12, y + 20))
        self._end()

    def year(self):
        self._page("year", "year")
        top = self._header("Year at a Glance", "", self.pal[0], 1)
        cw, ch = (W - TAB_W - 80 - 3 * 16) / 4, (top - 40 - 2 * 16) / 3
        for i, m in enumerate(MONTHS):
            x = 40 + (i % 4) * (cw + 16)
            y = top - (i // 4 + 1) * ch - (i // 4) * 16
            col = self.pal[i % len(self.pal)]
            t = self._box(x, y, cw, ch, m, col)
            self._lines(x + 16, t, y + 8, cw - 32, 28)
            self._link(f"m{i}", (x, y, x + cw, y + ch))
        self._end()

    def month(self, i):
        m, col = MONTHS[i], self.pal[i % len(self.pal)]
        self._page(f"m{i}", "year", i)
        top = self._header(m, "MONTHLY", col, i, prev=f"m{i - 1}" if i else None, nxt=f"m{i + 1}" if i < 11 else None)
        gx, gw = 40, W - TAB_W - 380
        cw = gw / 7
        for d, name in enumerate(self.days):
            self._text(gx + d * cw + cw / 2, top - 24, name[:3].upper(), "SansB", 14, self.soft, "c")
        rh = (top - 40 - 40) / 6
        self._stroke(self.line, 1.2)
        for r in range(6):
            for d in range(7):
                x, y = gx + d * cw, 40 + (5 - r) * rh
                self._fill(self.card)
                self.c.rect(x, y, cw, rh, stroke=1, fill=1)
                self._stroke(self.line, 0.9)
                self.c.circle(x + 18, y + rh - 18, 11, stroke=1, fill=0)
                self._stroke(self.line, 1.2)
        sx, sw = gx + gw + 24, W - TAB_W - 40 - (gx + gw + 24)
        t = self._box(sx, top - 250, sw, 250, "Goals", col)
        self._lines(sx + 16, t, top - 250 + 8, sw - 32, 30)
        self._text(sx, top - 290, "THIS MONTH", "SansB", 14, col)
        links = [(f"Week {w + 1}", f"m{i}w{w}") for w in range(WEEKS)] + \
                [("Habits & Mood", f"m{i}h"), ("Budget", f"m{i}b"), ("Reflection", f"m{i}r")]
        for k, (lab, key) in enumerate(links):
            y = top - 345 - k * 50
            self._button(sx, y, sw, 40, lab, key, col)
        self._end()

    def week(self, i, w):
        col = self.pal[i % len(self.pal)]
        prev = f"m{i}w{w - 1}" if w else (f"m{i - 1}w{WEEKS - 1}" if i else None)
        nxt = f"m{i}w{w + 1}" if w < WEEKS - 1 else (f"m{i + 1}w0" if i < 11 else None)
        self._page(f"m{i}w{w}", "year", i)
        top = self._header(f"{MONTHS[i]} · Week {w + 1}", "WEEKLY", col, i + w + 2, prev, nxt)
        gap = 14
        bw, bh = (W - TAB_W - 80 - 3 * gap) / 4, (top - 40 - gap) / 2
        for k in range(8):
            x = 40 + (k % 4) * (bw + gap)
            y = 40 + (1 - k // 4) * (bh + gap)
            if k < 7:
                name = self.days[k]
                t = self._box(x, y, bw, bh, name, col)
                self._lines(x + 16, t - 4, y + 8, bw - 32, 30)
                self._link(f"m{i}w{w}d{k}", (x, y + bh - 44, x + bw, y + bh))
                self._text(x + bw - 16, y + bh - 32, "open ›", "Sans", 12, self.soft, "r")
            else:
                t = self._box(x, y, bw, bh, "Priorities", col)
                self._check(x + 16, t, y + 12, bw - 32, 8)
        self._end()

    def day(self, i, w, k):
        col = self.pal[i % len(self.pal)]
        key = f"m{i}w{w}d{k}"
        prev = f"m{i}w{w}d{k - 1}" if k else None
        nxt = f"m{i}w{w}d{k + 1}" if k < 6 else None
        self._page(key, "year", i)
        top = self._header(f"{self.days[k]}", f"{MONTHS[i].upper()} · WEEK {w + 1}", col, i + k, prev, nxt)
        self._button(W - TAB_W - 40 - 160, 44, 160, 34, "‹ back to week", f"m{i}w{w}", col)
        mid = 40 + (W - TAB_W - 80) * 0.48
        t = self._box(40, 40, mid - 52, top - 40, "Schedule", col)
        step = (t - 52) / 16
        for h in range(16):
            y = t - (h + 1) * step + 6
            self._text(56, y + 6, f"{(h + 6) % 12 or 12} {'am' if h + 6 < 12 else 'pm'}", "SansL", 13, self.soft)
            self._stroke(self.line, 1)
            self.c.line(110, y, mid - 30, y)
        x2, w2 = mid, W - TAB_W - 40 - mid
        h3 = (top - 40 - 2 * 16 - 50) / 3
        y = top - h3
        t = self._box(x2, y, w2, h3, "Top 3", col)
        self._check(x2 + 16, t, y + 10, w2 - 32, 3)
        y2 = y - 16 - h3
        t = self._box(x2, y2, w2 / 2 - 8, h3, "To do", col)
        self._check(x2 + 16, t, y2 + 10, w2 / 2 - 40, 5)
        t = self._box(x2 + w2 / 2 + 8, y2, w2 / 2 - 8, h3, "Grateful for", col)
        self._lines(x2 + w2 / 2 + 24, t, y2 + 8, w2 / 2 - 40)
        y3 = y2 - 16 - h3
        t = self._box(x2, y3, w2 / 2 - 8, h3, "Water · Mood", col)
        self._circles(x2 + 16, t, y3 + 50, w2 / 2 - 40, 8, col)
        for j, mood in enumerate(["great", "good", "ok", "low", "bad"]):
            self._text(x2 + 30 + j * (w2 / 2 - 40) / 5, y3 + 18, mood, "SansL", 12, self.soft, "c")
        t = self._box(x2 + w2 / 2 + 8, y3, w2 / 2 - 8, h3, "Notes", col)
        self._lines(x2 + w2 / 2 + 24, t, y3 + 8, w2 / 2 - 40)
        self._end()

    def habits(self, i):
        col = self.pal[i % len(self.pal)]
        self._page(f"m{i}h", "year", i)
        top = self._header(f"{MONTHS[i]} · Habits & Mood", "TRACKER", col, i + 1)
        x0, xw = 40, W - TAB_W - 80
        t = self._box(x0, top - 470, xw, 470, "Habits", col)
        cw = (xw - 260) / 31
        for d in range(31):
            self._text(250 + d * cw + cw / 2, t - 4, str(d + 1), "SansL", 11, self.soft, "c")
        for r in range(9):
            y = t - 40 - r * 42
            self._stroke(self.line, 1)
            self.c.line(x0 + 16, y, 230, y)
            for d in range(31):
                self._stroke(_mix(self.line, self.ink, 0.15), 0.8)
                self.c.circle(250 + d * cw + cw / 2, y + 9, min(9, cw / 2 - 2), stroke=1, fill=0)
        t = self._box(x0, 40, xw, top - 470 - 56, "Mood", col)
        moods = ["great", "good", "okay", "low", "awful"]
        for j, mname in enumerate(moods):
            self._fill(_mix(self.card, col, 0.25 + j * 0.15))
            self.c.roundRect(x0 + 16 + j * 110, 52, 100, 26, 8, stroke=0, fill=1)
            self._text(x0 + 66 + j * 110, 60, mname, "SansM", 12, self.ink, "c")
        for d in range(31):
            self._stroke(self.line, 1)
            self.c.roundRect(250 + d * cw + 2, 100, cw - 4, t - 110, 6, stroke=1, fill=0)
        self._end()

    def budget(self, i):
        col = self.pal[i % len(self.pal)]
        self._page(f"m{i}b", "finance", i)
        top = self._header(f"{MONTHS[i]} · Budget", "MONTHLY", col, i + 3)
        self._layout([("table", "Income", ["Source", "Expected", "Actual"], 6),
                      ("table", "Bills", ["Bill", "Due", "Amount", "Paid"], 6),
                      ("table", "Spending", ["Category", "Budget", "Actual"], 6),
                      ("table", "Savings", ["Goal", "Saved", "Left"], 6)], top, col)
        self._end()

    def reflection(self, i):
        col = self.pal[i % len(self.pal)]
        self._page(f"m{i}r", "year", i)
        top = self._header(f"{MONTHS[i]} · Reflection", "", col, i + 4)
        self._layout([("boxes", ["Highlights", "Wins", "Challenges", "Lessons", "Grateful for", "Next month"])], top, col)
        self._end()

    def template(self, key, title, section, items, n):
        col = self.pal[n % len(self.pal)]
        first = n == 0 or TEMPLATES[n - 1][2] != section
        self._page(None, section)
        if first:
            self.c.bookmarkPage(section)
        self.c.bookmarkPage(key)
        top = self._header(title, section.upper(), col, n)
        self._layout(items, top, col)
        self._end()

    def note_page(self, k, kind):
        col = self.pal[k % len(self.pal)]
        self._page(f"note{k}", "notes")
        if k == 0:
            self.c.bookmarkPage("notes")
        top = self._header("Notes", kind.upper(), col, k + 3)
        x0, x1, y0, y1 = 40, W - TAB_W - 40, top - 10, 40
        if kind == "Lined":
            self._lines(x0, y0, y1, x1 - x0)
        elif kind == "Dotted":
            self._fill(_mix(self.line, self.ink, 0.2))
            for y in range(int(y1), int(y0), 30):
                for x in range(int(x0), int(x1), 30):
                    self.c.circle(x, y, 1.6, stroke=0, fill=1)
        elif kind == "Grid":
            self._stroke(self.line, 0.7)
            for x in range(int(x0), int(x1) + 1, 30):
                self.c.line(x, y1, x, y0)
            for y in range(int(y1), int(y0) + 1, 30):
                self.c.line(x0, y, x1, y)
        elif kind == "Cornell":
            self._stroke(col, 1.4)
            self.c.line(x0 + 300, y0, x0 + 300, y1 + 160)
            self.c.line(x0, y1 + 160, x1, y1 + 160)
            self._text(x0, y0 - 24, "CUES", "SansB", 14, col)
            self._text(x0 + 320, y0 - 24, "NOTES", "SansB", 14, col)
            self._text(x0, y1 + 130, "SUMMARY", "SansB", 14, col)
            self._lines(x0 + 320, y0 - 34, y1 + 170, x1 - x0 - 320)
        self._end()

    def build(self):
        self.cover()
        self.index()
        self.year()
        for i in range(12):
            self.month(i)
            for w in range(WEEKS):
                self.week(i, w)
                for k in range(7):
                    self.day(i, w, k)
            self.habits(i)
            self.budget(i)
            self.reflection(i)
        for n, (key, title, section, items) in enumerate(TEMPLATES):
            self.template(key, title, section, items, n)
        for k, kind in enumerate(PAPERS):
            self.note_page(k, kind)
        self.c.save()
        return self.buf.getvalue()


def render_pages(pdf_bytes, page_numbers, width=1200):
    """PDF pages -> PIL images (for listing photos)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_bytes)
    out = []
    for n in page_numbers:
        if 0 <= n < len(doc):
            pg = doc[n]
            out.append(pg.render(scale=width / pg.get_width()).to_pil().convert("RGB"))
    return out


def page_index(key, week_start="sun"):
    """Page number of a named page in the built PDF (same order as build())."""
    order = ["cover", "index", "year"]
    for i in range(12):
        order.append(f"m{i}")
        for w in range(WEEKS):
            order.append(f"m{i}w{w}")
            order += [f"m{i}w{w}d{k}" for k in range(7)]
        order += [f"m{i}h", f"m{i}b", f"m{i}r"]
    order += [t[0] for t in TEMPLATES]
    order += [f"note{k}" for k in range(len(PAPERS))]
    return order.index(key)
