"""Automatic daily production makes only what the owner chose: vintage shirts, xmaskids, coloring (named / normal)."""
import datetime as dt
import unittest
from unittest import mock

from bot import config, presets, research, smart_niche, storage

DAY = dt.date(2026, 11, 12)


def product(preset, theme, day="2026-11-01", status="published"):
    return {"day": day, "status": status, "created_at": 1, "spec": {"preset": preset, "theme": theme}}


class DailyPlanTest(unittest.TestCase):
    def plan(self, products, day=DAY):
        with mock.patch.object(storage, "all_products", lambda: products), \
                mock.patch.object(research, "_score", lambda idea: None):
            return [(i["type"], i["preset"], i["theme"]) for i in smart_niche.daily_plan(day)]

    def test_settings_ask_for_exactly_the_three_daily_products(self):
        s = config.settings()
        self.assertTrue(s["auto_daily"])
        self.assertEqual(s["products_per_day"], 3)
        self.assertEqual(s["product_types"], {"coloring": 1})  # the open place is always a normal coloring book
        self.assertEqual(s["daily_presets"], [["sublimation:vintagexmas"], ["custom:xmaskids"], ["custom:boyama", ""]])
        for slot in s["daily_presets"]:
            for entry in filter(None, slot):
                ptype, name = entry.split(":")
                self.assertIsNotNone(presets.load(ptype, name), entry)

    def test_named_coloring_and_normal_coloring_take_turns(self):
        days = [self.plan([], DAY + dt.timedelta(days=k)) for k in range(4)]
        for d in days:
            self.assertEqual([x[1] for x in d[:2]], ["vintagexmas", "xmaskids"])
        self.assertEqual([len(d) for d in days].count(3), 2)  # boyama every second day ...
        self.assertEqual([len(d) for d in days].count(2), 2)  # ... the other days leave the place to /uret_coloring style
        self.assertNotEqual(len(days[0]), len(days[1]))

    def test_every_day_a_theme_that_is_not_in_the_shop_yet(self):
        first = self.plan([])[0]
        self.assertEqual(first, ("sublimation", "vintagexmas", "classic"))
        second = self.plan([product("vintagexmas", "classic")])[0]
        self.assertEqual(second[2], "cozy")
        third = self.plan([product("vintagexmas", "classic"), product("vintagexmas", "cozy")])[0]
        self.assertEqual(third[2], "kids")
        # all three themes are listed: no fourth copy of the same listing, the place goes to another product
        done = [product("vintagexmas", t) for t in ("classic", "cozy", "kids")]
        self.assertNotIn("vintagexmas", [x[1] for x in self.plan(done)])
        # a rejected one may be made again
        again = self.plan(done[:2] + [product("vintagexmas", "kids", status="rejected")])[0]
        self.assertEqual(again[2], "kids")

    def test_a_restart_on_the_same_day_does_not_repeat_a_preset(self):
        made = [product("vintagexmas", "classic", day=DAY.isoformat(), status="pending")]
        self.assertNotIn("vintagexmas", [x[1] for x in self.plan(made)])

    def test_plan_comes_first_and_ai_fills_the_rest(self):
        asked = []

        def ai(slots, used, today):
            asked.append([s["type"] for s in slots])
            return []
        with mock.patch.object(storage, "all_products", lambda: []), \
                mock.patch.object(research, "_score", lambda idea: None), \
                mock.patch.object(smart_niche, "daily_plan", lambda today: [
                    {"type": "sublimation", "niche": "a", "search_query": "a", "preset": "vintagexmas"},
                    {"type": "custom", "niche": "b", "search_query": "b", "preset": "xmaskids"}]), \
                mock.patch.object(smart_niche, "_ask", ai), \
                mock.patch.dict("os.environ", {"ONLY_TYPE": "", "ONLY_SUBJECT": ""}):
            ideas = smart_niche.find_trending_niches(3)
        self.assertEqual([i.get("preset") for i in ideas[:2]], ["vintagexmas", "xmaskids"])
        self.assertTrue(asked and set(asked[0]) == {"coloring"})  # only coloring ideas are asked from the AI


if __name__ == "__main__":
    unittest.main()
