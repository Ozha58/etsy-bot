"""Made-to-order listings: Telegram says exactly what to type into Etsy's personalization box."""
import unittest

from bot import poller


def product(personal=True):
    listing = {"is_personalizable": True, "personalization_is_required": True, "personalization_char_count_max": 40,
               "personalization_instructions": "Type the child's name exactly as it should appear, max 40 characters."}
    return {"title": "Custom Name Coloring Pages, Personalized PDF, Kids Party", "build": {"listing": listing if personal else {}}}


class GuideTest(unittest.TestCase):
    def test_off_box_gives_copy_ready_texts(self):
        g = poller.personalization_guide(product(), {"personalization_on": False, "url": "https://www.etsy.com/listing/1"})
        self.assertIn("elle açman", g)
        self.assertIn("<code>Type the child&#x27;s name exactly as it should appear, max 40 characters.</code>", g)
        self.assertIn("<code>40</code>", g)
        self.assertIn("required", g)
        self.assertIn("https://www.etsy.com/listing/1", g)

    def test_on_box_is_a_short_confirmation_and_normal_products_get_nothing(self):
        g = poller.personalization_guide(product(), {"personalization_on": True})
        self.assertIn("açık", g)
        self.assertNotIn("elle aç", g)
        self.assertEqual(poller.personalization_guide(product(False), {"personalization_on": False}), "")


if __name__ == "__main__":
    unittest.main()


class LimitTest(unittest.TestCase):
    def test_every_instruction_fits_etsys_120_characters(self):
        import glob
        import json
        from bot import etsy, presets
        for f in glob.glob("presets/custom/*.json"):
            p = json.load(open(f))
            for v in [p] + list(p.get("themes") or []):
                t = v.get("personalization_instructions")
                if t:
                    self.assertLessEqual(len(t), 120, f)
        long = ("Type the child's name exactly as it should appear on the pages (e.g. Olivia), max 40 characters. "
                "Your 6 coloring pages are sent within 24 hours.")
        short = etsy.short_instructions(long)  # products made before the rule carry the long text
        self.assertLessEqual(len(short), 120)
        self.assertTrue(short.startswith("Type the child's name"))
        self.assertTrue(short.endswith("."))
        self.assertEqual(etsy.short_instructions("Name - Birth month (e.g. Emma - July)."), "Name - Birth month (e.g. Emma - July).")
        g = poller.personalization_guide({"title": "T, B, C", "build": {"listing": {
            "is_personalizable": True, "personalization_instructions": long}}}, {"personalization_on": False, "url": "u"})
        self.assertIn("Etsy sınırı 120", g)
        bad = dict(presets.load("custom", "boyama"), personalization_instructions="x" * 121)
        self.assertTrue(any("120" in pr for pr in presets.problems(bad, "custom")))
