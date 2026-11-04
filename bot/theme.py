"""Shop focus: Sebasteia = vintage storybook snowy forest, Christmas and winter animal art.

Every new product stays inside this theme; the seasonal angle changes through the year so the
shop always has something buyers are shopping for (they shop 3-8 weeks ahead).
settings.json can override: "shop_theme", "shop_style", "christmas_share".
"""
import datetime as dt
import random

from . import config

SHOP_THEME = ("vintage storybook illustrations of snowy forests and winter woodland animals "
              "(reindeer, deer, red foxes, owls, bunnies, bear cubs, robins, cardinals, squirrels, hedgehogs) "
              "and cozy Christmas in the forest")

HOUSE_STYLE = ("vintage storybook illustration, soft gouache and watercolor texture, fine detailed brushwork, "
               "warm muted palette of forest green, deep red, cream and soft gold, gentle cozy light")

SUBJECTS = [
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
    ((5, 1), "summer forest and meadow animals in the same storybook style"),
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


def slot_theme(today: dt.date = None) -> str:
    return (f"SHOP THEME (mandatory): {theme()}. Season angle: {angle(today)}. "
            f"Subject idea to build on: {random.choice(SUBJECTS)}. "
            "No gnomes, no elves, no Grinch, no brand or film characters.")
