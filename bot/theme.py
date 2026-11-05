"""Shop focus: Sebasteia = realistic, detailed printables about one charming subject each.

Every new product stays inside this theme; the seasonal angle changes through the year so the
shop always has something buyers are shopping for (they shop 3-8 weeks ahead).
settings.json can override: "shop_theme", "shop_style", "christmas_share".
"""
import datetime as dt
import random

from . import config

SHOP_THEME = ("realistic, detailed printables, each product about ONE charming subject "
              "(honey bees, lighthouses and the seaside, mushrooms, unicorns, dogs, birds, botanicals, cottages, "
              "tea time, butterflies, woodland animals)")

HOUSE_STYLE = ("highly detailed realistic illustration, true-to-life colors and textures, fine detail, "
               "soft natural light, crisp and clean, high quality")

SUBJECTS = [
    "honey bees and beehives", "lighthouse by the sea", "seaside and shells", "mushrooms in the forest", "unicorns",
    "dogs", "garden birds", "vintage botanicals", "tea time", "butterflies and moths", "country cottage garden",
    "reindeer in a snowy pine forest", "deer family in falling snow", "red fox curled up in the snow",
    "snowy owl on a frosted branch", "winter bunnies under pine trees", "bear cub in a snowy clearing",
    "robins and cardinals on snowy branches", "squirrel with pinecones in winter", "hedgehog in a winter forest",
    "moose by a frozen lake", "snowy cottage village deep in the forest", "lantern-lit woodland path at dusk",
    "forest animals gathered around a decorated tree", "Santa Claus visiting the forest animals",
    "horse-drawn sleigh through a snowy pine forest", "woodland animals in a cozy cabin by the fire",
]

# (from month, from day) -> seasonal angle; the date used is ~3 weeks ahead of today
ANGLES = [
    ((1, 1), "cozy deep winter in the snowy forest, no Christmas items"),
    ((1, 25), "late winter forest, woodland animal couples with little red hearts for Valentine's Day"),
    ((2, 20), "first spring in the forest: bunnies, birds, melting snow, early blossoms, Easter"),
    ((5, 1), "summer forest and meadow animals"),
    ((8, 15), "autumn woodland: foxes, owls, falling leaves, mushrooms, cute cozy Halloween (never scary)"),
    ((10, 25), "Christmas in the snowy forest"),
    ((12, 31), "cozy deep winter in the snowy forest, no Christmas items"),
]


def theme():
    return config.settings().get("shop_theme") or SHOP_THEME


def style():
    return config.settings().get("shop_style") or HOUSE_STYLE


def angle(today: dt.date = None) -> str:
    target = (today or dt.date.today()) + dt.timedelta(days=21)
    current = ANGLES[0][1]
    for (m, d), text in ANGLES:
        if (target.month, target.day) >= (m, d):
            current = text
    if current.startswith("Christmas"):
        try:
            share = float(config.settings().get("christmas_share", 0.7))
        except Exception:
            share = 0.7
        if random.random() >= share:
            current = "cozy snowy winter forest, no Christmas items"
    return current


# Planners sell on an AESTHETIC, not on an animal (BrighterPlans & co: neutral, boho, floral, minimal, dark).
PLANNER_STYLES = [
    "neutral boho: beige, terracotta and dried pampas grass", "minimalist cream and beige, soft linen texture",
    "soft watercolor wildflowers", "sage green botanical leaves", "pastel rainbow aesthetic",
    "dark academia: old books, candlelight, deep green and brown", "cottagecore: wildflowers, linen and sunlight",
    "elegant white marble with gold accents", "calm coastal: soft blue waves and sand", "lavender fields at sunset",
    "cozy autumn leaves and warm tones", "cozy coffee, books and a knitted blanket", "japandi zen: stone, bamboo, soft light",
    "romantic pink peonies", "night sky with moon and stars", "golden sunflower field", "abstract earth-tone shapes",
    "blush pink and gold minimal", "tropical palm leaves", "vintage roses on cream paper",
]


PLANNER_EDITIONS = {  # what the planner is FOR: every planner in the shop is a different product
    "life": "an all-in-one life planner", "budget": "a budget / finance planner", "student": "a student / college planner",
    "adhd": "an ADHD-friendly planner", "wellness": "a health & wellness / fitness planner",
    "business": "a small business planner", "migraine": "a migraine & headache tracker planner",
}


def planner_theme() -> str:
    ed = random.choice(list(PLANNER_EDITIONS))
    return (f"PLANNER EDITION (mandatory): {PLANNER_EDITIONS[ed]} (edition '{ed}'); put the edition word in the niche, "
            f"name and title (e.g. 'boho {ed if ed != 'life' else 'life'} planner'). "
            f"PLANNER STYLE (mandatory): {random.choice(PLANNER_STYLES)}. Make it look like the best-selling aesthetic "
            "planners on Etsy: calm, pretty, adult. The cover art is a texture, a pattern, flowers or a calm scene. "
            "NO animals, NO characters, NO people, NO Christmas. Name it by the aesthetic "
            "(e.g. 'Neutral Boho Planner', 'Sage Botanical Planner', 'Dark Academia Planner').")


def slot_theme(today: dt.date = None, ptype: str = None) -> str:
    if ptype == "planner":
        return planner_theme()
    if ptype == "journal":  # the exact month / year bundle is decided by products.journal.prepare()
        return ("PRINTABLE BULLET JOURNAL (mandatory): a cozy seasonal theme for the coming months' journal pages "
                "(e.g. 'cozy winter', 'snowy pines', 'fresh start', 'winter botanicals'), calm and pretty, "
                "no characters, no brands, no Christmas-only theme.")
    return (f"SHOP THEME (mandatory): {theme()}. Season angle: {angle(today)}. "
            f"Subject idea to build on: {random.choice(SUBJECTS)}. "
            "No gnomes, no elves, no Grinch, no brand or film characters.")
