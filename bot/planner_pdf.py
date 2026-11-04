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
    # extra templates (competitors offer 80+)
    ("qplan1", "Quarter 1 Plan", "year", [("boxes", ["Top goals", "Projects", "Habits to build", "Focus", "Dates", "Notes"])]),
    ("qplan2", "Quarter 2 Plan", "year", [("boxes", ["Top goals", "Projects", "Habits to build", "Focus", "Dates", "Notes"])]),
    ("qplan3", "Quarter 3 Plan", "year", [("boxes", ["Top goals", "Projects", "Habits to build", "Focus", "Dates", "Notes"])]),
    ("qplan4", "Quarter 4 Plan", "year", [("boxes", ["Top goals", "Projects", "Habits to build", "Focus", "Dates", "Notes"])]),
    ("wordyear", "Word of the Year", "year", [("lines", "My word", 2), ("lines", "Why this word", 8), ("lines", "How I will live it", 8)]),
    ("aboutme", "About Me", "year", [("boxes", ["Favorites", "Dreams", "Strengths", "Values", "Fun facts", "This year I want"])]),
    ("smart", "SMART Goals", "goals", [("table", "", ["Goal", "Specific", "Measurable", "Achievable", "Relevant", "Time"], 8)]),
    ("matrix", "Priority Matrix", "goals", [("boxes", ["Urgent & important", "Important, not urgent", "Urgent, not important", "Neither"])]),
    ("habitlist", "Habit Builder", "goals", [("table", "", ["Habit", "Cue", "Reward", "Start date"], 10), ("circles", "21 day streak", 21)]),
    ("pomodoro", "Pomodoro Tracker", "goals", [("table", "", ["Task", "Sessions", "Done"], 12), ("circles", "Focus sessions", 62)]),
    ("timelog", "Time Tracker", "goals", [("table", "", ["Time", "Activity", "Category", "Notes"], 18)]),
    ("weeklyreview", "Weekly Review", "goals", [("boxes", ["Went well", "To improve", "Learned", "Next week focus"])]),
    ("mood", "Mood Tracker", "health", [("circles", "Color a mood for every day of the year", 366)]),
    ("sleep", "Sleep Log", "health", [("table", "", ["Date", "Bedtime", "Wake up", "Hours", "Quality"], 16)]),
    ("steps", "Steps & Activity", "health", [("table", "", ["Date", "Steps", "Activity", "Minutes", "Feeling"], 16)]),
    ("measure", "Body Measurements", "health", [("table", "", ["Date", "Weight", "Waist", "Hips", "Notes"], 14)]),
    ("doctor", "Appointments", "health", [("table", "", ["Date", "Doctor", "Reason", "Notes"], 14)]),
    ("emergency", "Emergency Fund", "finance", [("lines", "My target", 2), ("circles", "Color one for every deposit", 100)]),
    ("invest", "Investment Tracker", "finance", [("table", "", ["Date", "Asset", "Amount", "Value", "Notes"], 15)]),
    ("income", "Income Tracker", "finance", [("table", "", ["Date", "Source", "Amount", "Notes"], 16)]),
    ("weeklybudget", "Weekly Budget", "finance", [("table", "", ["Day", "Planned", "Spent", "Notes"], 7), ("check", "Spending goals", 8)]),
    ("wishlistfin", "Saving For", "finance", [("table", "", ["Item", "Price", "Saved", "Bought"], 14)]),
    ("wishlist", "Wishlist", "life", [("check", "Things I want", 16), ("check", "Gift ideas", 16)]),
    ("parcels", "Order & Parcel Tracker", "life", [("table", "", ["Order", "Shop", "Ordered", "Arrived", "Return"], 16)]),
    ("movies", "Movie & Series Log", "life", [("table", "", ["Title", "Genre", "Watched", "Rating"], 16)]),
    ("tbr", "To Be Read", "life", [("check", "Books to read", 16), ("check", "Books I loved", 16)]),
    ("booknotes", "Book Notes", "life", [("lines", "Title & author", 2), ("lines", "Favorite quotes", 8), ("lines", "My thoughts", 8)]),
    ("packing", "Packing List", "life", [("check", "Clothes", 12), ("check", "Toiletries", 10), ("check", "Tech", 8), ("check", "Documents", 8)]),
    ("dream", "Dream Journal", "life", [("lines", "Last night I dreamed", 12), ("lines", "Feelings & meaning", 8)]),
    ("affirm", "Affirmations", "life", [("lines", "I am", 10), ("lines", "I can", 10)]),
    ("selfcareplan", "Self-Care Plan", "life", [("boxes", ["Morning", "Evening", "Weekly", "When I feel low"])]),
    ("chores", "Chore Chart", "life", [("table", "", ["Chore", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], 12)]),
    ("birthdays", "Gift Planner", "life", [("table", "", ["Person", "Occasion", "Gift", "Budget", "Bought"], 14)]),
    ("pets", "Pet Care", "life", [("table", "", ["Date", "Task", "Vet / food", "Notes"], 14)]),
    ("plants", "Plant Care", "life", [("table", "", ["Plant", "Water", "Sun", "Fertilize", "Notes"], 14)]),
    ("events", "Event Planner", "life", [("lines", "Event", 2), ("check", "To do", 10), ("table", "", ["Guest", "RSVP"], 10)]),
    ("habitsyear", "Yearly Habit Tracker", "goals", [("circles", "One habit, every day of the year", 366)]),
]
PAPERS = ["Lined", "Dotted", "Grid", "Blank", "Cornell", "Music", "Lined", "Dotted"]
NB_PAPERS = ["Lined", "Dotted", "Grid", "Blank"]
NOTEBOOKS = 12


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
        self.c = rl.Canvas(self.buf, pagesize=(W, H), pageCompression=1)
        self.c.setTitle(title)
        self.pages = 0
        self.order = []
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
            if im.mode == "RGB":
                im.save(b, "JPEG", quality=86)  # photos: JPEG keeps the PDF small
            else:
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
        self.order.append(key)
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
        # small frosted card low on the page, so the art (the animal, the scene) stays fully visible
        cw, ch, cy = 640, 200, 46
        self._fill(self.card)
        self.c.setFillAlpha(0.88)
        self.c.roundRect(aw / 2 - cw / 2, cy, cw, ch, 26, stroke=0, fill=1)
        self.c.setFillAlpha(1)
        self._text(aw / 2, cy + ch - 42, "UNDATED DIGITAL PLANNER", "SansB", 18, self.pal[0], "c")
        size = 40 if len(self.title) <= 24 else 30
        self._text(aw / 2, cy + ch - 98, self.title, "Serif", size, self.ink, "c")
        self._button(aw / 2 - 100, cy + 22, 200, 44, "START HERE", "index", self.pal[0], True)
        self._end()

    def index(self):
        self._page("index", "index")
        top = self._header("Index", "tap anything to jump there", self.pal[0], 0)
        groups = [("CALENDAR", [("Year at a Glance", "year")] + [(m, f"m{i}") for i, m in enumerate(MONTHS)])]
        for sec, name in (("year", "YEAR"), ("goals", "GOALS"), ("health", "HEALTH"), ("finance", "FINANCE"), ("life", "LIFE")):
            groups.append((name, [(t[1], t[0]) for t in TEMPLATES if t[2] == sec]))
        groups.append(("NOTES", [("How to use", "guide"), ("All notes", "notes")] + [(f"{p} paper", f"note{k}") for k, p in enumerate(PAPERS[:6])]
                       + [(f"Notebook {n + 1}", f"nb{n}") for n in range(NOTEBOOKS)]))
        cols = len(groups)
        cw = (W - TAB_W - 80) / cols
        for g, (name, items) in enumerate(groups):
            x = 40 + g * cw
            col = self.pal[g % len(self.pal)]
            self._text(x, top - 30, name, "SansB", 18, col)
            step = min(46, (top - 90) / max(len(items), 1))
            for k, (lab, key) in enumerate(items):
                y = top - 78 - k * step
                fs = 16 if len(items) <= 18 else 13
                lab = lab if len(lab) <= 19 else lab[:18] + "…"
                self._text(x, y, lab, "Sans", fs, self.ink)
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
        links = [("At a glance", f"m{i}g")] + [(f"Week {w + 1}", f"m{i}w{w}") for w in range(WEEKS)] + \
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
                self._check(x + 16, t, y + 70, bw - 32, 6)
                self._button(x + 16, y + 18, bw - 32, 38, "Hourly schedule ›", f"m{i}w{w}s", col, True)
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

    def template(self, key, title, section, items, n, first=False):
        col = self.pal[n % len(self.pal)]
        self._page(key, section)
        if first and section != "year":  # the YEAR tab goes to "Year at a Glance"
            self.c.bookmarkPage(section)
        top = self._header(title, section.upper(), col, n)
        self._layout(items, top, col)
        self._end()

    def note_page(self, k, kind, title=None, prev=None, nxt=None):
        col = self.pal[(k if isinstance(k, int) else len(title or "")) % len(self.pal)]
        self._page(f"note{k}" if isinstance(k, int) else k, "notes")
        top = self._header(title or "Notes", kind.upper(), col, (k if isinstance(k, int) else 0) + 3,
                           prev=prev, nxt=nxt)
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
        elif kind == "Music":
            self._stroke(_mix(self.line, self.ink, 0.15), 1)
            y = y0 - 30
            while y - 48 > y1:
                for l in range(5):
                    self.c.line(x0, y - l * 12, x1, y - l * 12)
                y -= 110
        elif kind == "Cornell":
            self._stroke(col, 1.4)
            self.c.line(x0 + 300, y0, x0 + 300, y1 + 160)
            self.c.line(x0, y1 + 160, x1, y1 + 160)
            self._text(x0, y0 - 24, "CUES", "SansB", 14, col)
            self._text(x0 + 320, y0 - 24, "NOTES", "SansB", 14, col)
            self._text(x0, y1 + 130, "SUMMARY", "SansB", 14, col)
            self._lines(x0 + 320, y0 - 34, y1 + 170, x1 - x0 - 320)
        self._end()

    def guide(self):
        self._page("guide", "index")
        top = self._header("How to use your planner", "START HERE", self.pal[0], 2)
        steps = [("Navigate", "Tap the tabs at the top (Home, Year, Goals, Health, Finance, Life, Notes) and the month tabs on the right."),
                 ("Months", "Each month opens a calendar. Write the dates in the small circles: it is undated, so start any time."),
                 ("Weeks & days", "Month pages link to 5 weeks. Week pages link to an hourly schedule and to every single day."),
                 ("Arrows", "Use the arrows in the page header to go to the previous or next week, day or month."),
                 ("Templates", "80 extra pages for goals, health, money and life are in the top tabs. Duplicate any page in your app."),
                 ("Notebooks", "12 custom notebooks with lined, dotted, grid and blank paper are under NOTES. Rename them as you like."),
                 ("Stickers", "Import the PNG stickers into your note app's sticker or image library, then drag them onto any page.")]
        y = top - 20
        for k, (head, body) in enumerate(steps):
            col = self.pal[k % len(self.pal)]
            self._fill(col)
            self.c.circle(70, y - 26, 22, stroke=0, fill=1)
            self._text(70, y - 33, str(k + 1), "SansB", 20, (255, 255, 255), "c")
            self._text(110, y - 22, head.upper(), "SansB", 17, col)
            self._text(110, y - 50, body, "Sans", 16, self.ink)
            y -= 106
        self._button(W - TAB_W - 260, 50, 220, 44, "Open the index", "index", self.pal[0], True)
        self._end()

    def week_schedule(self, i, w):
        col = self.pal[i % len(self.pal)]
        self._page(f"m{i}w{w}s", "year", i)
        top = self._header(f"{MONTHS[i]} · Week {w + 1}", "SCHEDULE", col, i + w + 4, prev=f"m{i}w{w}", nxt=None)
        x0, x1 = 100, W - TAB_W - 40
        cw = (x1 - x0) / 7
        for d, name in enumerate(self.days):
            self._fill(_mix(self.card, col, 0.15))
            self.c.rect(x0 + d * cw, top - 40, cw, 40, stroke=0, fill=1)
            self._text(x0 + d * cw + cw / 2, top - 27, name[:3].upper(), "SansB", 14, col, "c")
            self._link(f"m{i}w{w}d{d}", (x0 + d * cw, top - 40, x0 + (d + 1) * cw, top))
        rows = 17
        rh = (top - 40 - 50) / rows
        self._stroke(self.line, 1)
        for r in range(rows + 1):
            y = top - 40 - r * rh
            self.c.line(x0, y, x1, y)
            if r < rows:
                h = r + 6
                self._text(40, y - rh / 2 - 5, f"{h % 12 or 12} {'am' if h < 12 else 'pm'}", "SansL", 13, self.soft)
        for d in range(8):
            self.c.line(x0 + d * cw, top - 40, x0 + d * cw, top - 40 - rows * rh)
        self._end()

    def glance(self, i):
        col = self.pal[i % len(self.pal)]
        self._page(f"m{i}g", "year", i)
        top = self._header(f"{MONTHS[i]} · At a Glance", "31 DAYS", col, i + 6)
        x0, x1 = 40, W - TAB_W - 40
        half = (x1 - x0 - 24) / 2
        rh = (top - 40) / 16
        for d in range(31):
            cx = x0 + (d // 16) * (half + 24)
            y = top - (d % 16 + 1) * rh
            self._fill(_mix(self.card, col, 0.18))
            self.c.roundRect(cx, y + 4, 52, rh - 8, 8, stroke=0, fill=1)
            self._text(cx + 26, y + rh / 2 - 6, str(d + 1), "SansB", 15, col, "c")
            self._stroke(self.line, 1)
            self.c.line(cx + 64, y + 6, cx + half, y + 6)
        self._end()

    def notes_hub(self):
        self._page("notes", "notes")
        top = self._header("Notes & Notebooks", "TAP TO OPEN", self.pal[0], 5)
        x0 = 40
        self._text(x0, top - 30, "NOTE PAPERS", "SansB", 16, self.pal[0])
        for k, kind in enumerate(PAPERS):
            self._button(x0 + (k % 4) * 270, top - 90 - (k // 4) * 60, 250, 44, f"{kind} paper", f"note{k}", self.pal[k % len(self.pal)])
        self._text(x0, top - 250, "MY NOTEBOOKS", "SansB", 16, self.pal[1 % len(self.pal)])
        bw, bh = (W - TAB_W - 80 - 5 * 16) / 6, 150
        for n in range(NOTEBOOKS):
            x = x0 + (n % 6) * (bw + 16)
            y = top - 290 - (n // 6 + 1) * (bh + 20)
            col = self.pal[n % len(self.pal)]
            self._fill(_mix(self.card, col, 0.35))
            self.c.roundRect(x, y, bw, bh, 16, stroke=0, fill=1)
            self._fill(col)
            self.c.roundRect(x, y, 22, bh, 8, stroke=0, fill=1)
            self._text(x + bw / 2 + 10, y + bh / 2 - 8, f"Notebook {n + 1}", "SansB", 16, self.ink, "c")
            self._link(f"nb{n}", (x, y, x + bw, y + bh))
        self._end()

    def notebook(self, n):
        col = self.pal[n % len(self.pal)]
        self._page(f"nb{n}", "notes")
        top = self._header(f"Notebook {n + 1}", "COVER", col, n + 2, prev="notes", nxt=f"nb{n}p0")
        self._fill(_mix(self.card, col, 0.25))
        self.c.roundRect(240, 140, W - TAB_W - 480, top - 220, 30, stroke=0, fill=1)
        self._text((W - TAB_W) / 2, top / 2 + 40, "NOTEBOOK TITLE", "SansB", 18, col, "c")
        self._stroke(col, 2)
        self.c.line((W - TAB_W) / 2 - 300, top / 2, (W - TAB_W) / 2 + 300, top / 2)
        self._deco(n, (W - TAB_W) / 2 - 70, 190, 140)
        for k, kind in enumerate(NB_PAPERS):
            self._button(260 + k * 150, 70, 140, 40, kind, f"nb{n}p{k}", col)
        self._end()
        for k, kind in enumerate(NB_PAPERS):
            self.note_page(f"nb{n}p{k}", kind, f"Notebook {n + 1}",
                           prev=f"nb{n}p{k - 1}" if k else f"nb{n}", nxt=f"nb{n}p{k + 1}" if k < len(NB_PAPERS) - 1 else None)

    def build(self):
        self.cover()
        self.index()
        self.guide()
        self.year()
        for i in range(12):
            self.month(i)
            self.glance(i)
            for w in range(WEEKS):
                self.week(i, w)
                self.week_schedule(i, w)
                for k in range(7):
                    self.day(i, w, k)
            self.habits(i)
            self.budget(i)
            self.reflection(i)
        order = [sec for _, sec in SECTIONS]
        seen = set()
        for n, (key, title, section, items) in enumerate(sorted(TEMPLATES, key=lambda t: order.index(t[2]))):
            self.template(key, title, section, items, n, first=section not in seen)
            seen.add(section)
        self.notes_hub()
        for k, kind in enumerate(PAPERS):
            self.note_page(k, kind)
        for n in range(NOTEBOOKS):
            self.notebook(n)
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


def page_index(key, planner=None):
    """Page number of a named page (planner.order is filled while building)."""
    return planner.order.index(key)
