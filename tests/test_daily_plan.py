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
        self.assertEqual(s["products_per_day"], 4)
        self.assertEqual(s["product_types"], {"coloring": 1})  # the open place is always a normal coloring book
        self.assertEqual(s["daily_presets"], [["sublimation:vintagexmas"], ["custom:xmaskids"], ["custom:boyama"]])
        for slot in s["daily_presets"]:
            for entry in filter(None, slot):
                ptype, name = entry.split(":")
                self.assertIsNotNone(presets.load(ptype, name), entry)

    def test_every_day_one_of_each_of_the_four_kinds(self):
        for k in range(3):
            d = self.plan([], DAY + dt.timedelta(days=k))
            self.assertEqual([x[1] for x in d], ["vintagexmas", "xmaskids", "boyama"])  # + 1 normal coloring by AI

    def test_closed_uret_commands_are_refused(self):
        from bot import poller
        for only, subj in (("coloring", ""), ("coloring", "bees"), ("sublimation", "vintagexmas"),
                           ("sublimation", "vintagexmas cozy"), ("custom", "xmaskids dino"), ("custom", "boyama")):
            self.assertTrue(poller.uret_allowed(only, subj), (only, subj))
        for only, subj in (("junk_journal", ""), ("stickers", "migraine"), ("tattoo", ""), ("custom", "teacher"),
                           ("sublimation", ""), ("clipart", ""), (None, "")):
            self.assertFalse(poller.uret_allowed(only, subj), (only, subj))
        sent = []
        with mock.patch.object(poller.telegram, "send", lambda t, *a, **k: sent.append(t)), \
                mock.patch.object(poller, "_dispatch_generate", lambda *a, **k: self.fail("closed type started")):
            poller._handle_message({"text": "/uret_junk"}, {})
            poller._handle_message({"text": "/uret_tattoo"}, {})
        self.assertTrue(all("kapalı" in t for t in sent) and len(sent) == 2)
        started = []
        with mock.patch.object(poller.telegram, "send", lambda t, *a, **k: None), \
                mock.patch.object(poller, "_dispatch_generate", lambda *a, **k: started.append(a)):
            for c in ("/uret_custom_boyama", "/uret_sublimation_vintagexmas_kids", "/uret_coloring", "/uret", "/uret_2"):
                poller._handle_message({"text": c}, {})
        self.assertEqual(len(started), 5)
        self.assertNotIn("/uret_junk", poller.HELP)
        self.assertNotIn("/uret_tattoo", poller.HELP)

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


class OnlyTypeTest(unittest.TestCase):
    def test_requested_type_is_kept_when_the_text_ai_is_down(self):
        from bot import etsy_miner, llm
        mined = [{"type": "scenes", "niche": "cottage clipart, realistic detailed style", "search_query": "cottage clipart",
                  "score": 1.0, "etsy_results": 900}]
        with mock.patch.dict("os.environ", {"ONLY_TYPE": "tattoo", "ONLY_SUBJECT": ""}), \
                mock.patch.object(smart_niche, "_ask", side_effect=llm.LLMError("quota")), \
                mock.patch.object(etsy_miner, "find", lambda *a: [dict(m) for m in mined]), \
                mock.patch.object(research, "_score", lambda idea: None), \
                mock.patch.object(storage, "all_products", lambda: []):
            ideas = smart_niche.find_trending_niches(1)
        self.assertTrue(ideas)
        self.assertEqual({i["type"] for i in ideas}, {"tattoo"})
