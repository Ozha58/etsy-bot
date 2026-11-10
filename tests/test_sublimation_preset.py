"""Vintage Christmas shirt bundle preset, without spending image quota (image AI, text AI and Etsy are fakes).

Run from the repo root:  python -m unittest tests.test_sublimation_preset -v
"""
import io
import os
import unittest
import zipfile
from unittest import mock

from PIL import Image, ImageDraw

from bot import images, llm, presets, research, smart_niche, storage
from bot.products import sublimation

PRESET = "vintagexmas"


def fake_image(prompt, width, height):
    fake_image.prompts.append(prompt)
    im = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(im).ellipse((width * 0.2, height * 0.2, width * 0.8, height * 0.8), fill=(180, 40, 50))
    return im


def fake_llm(prompt, system="", temperature=0.8):
    fake_llm.prompts.append(prompt)
    return {"intro": "Retro Christmas Sublimation PNG Bundle for shirt makers.\n\nPress it on tees and mugs.",
            "styles": ["Retro", "Vintage"], "price_usd": 99, "cover_scene": "a cozy craft table at Christmas"}


class VintageBundleTest(unittest.TestCase):
    def setUp(self):
        fake_image.prompts, fake_llm.prompts = [], []
        for p in [mock.patch.object(images, "try_generate", fake_image),
                  mock.patch.object(images, "generate", side_effect=AssertionError("real image call")),
                  mock.patch.object(llm, "ask_json", fake_llm),
                  mock.patch.object(research, "_score", lambda idea: None),
                  mock.patch.object(storage, "all_products", lambda: [])]:
            p.start()
            self.addCleanup(p.stop)

    def test_preset_is_valid_and_original(self):
        preset = presets.load("sublimation", PRESET)
        self.assertEqual(presets.problems(preset, "sublimation"), [])
        self.assertEqual(len(preset["designs"]), 12)
        phrases = [d["phrase"] for d in preset["designs"]]
        self.assertEqual(len(set(phrases)), 12)
        for ph in phrases:
            self.assertRegex(ph, sublimation.TEXT_OK)
        # original characters only: no film, show or character names anywhere in the file
        text = " ".join([preset["title"], *preset["tags"], *phrases, *(d["prompt"] for d in preset["designs"])]).lower()
        for word in ("grinch", "home alone", "elf movie", "buddy", "frosty", "rudolph", "griswold", "kevin", "peanuts",
                     "charlie brown", "disney", "red nose", "red-nosed"):
            self.assertNotIn(word, text)
        # a count outside the allowed range is refused, other product types keep their fixed number
        self.assertTrue(presets.problems(dict(preset, count=40), "sublimation"))
        self.assertEqual(presets._count({"count": 12}, "custom")[1], presets._list_field("custom")[1])

    def test_uret_builds_twelve_retro_designs(self):
        with mock.patch.dict(os.environ, {"ONLY_TYPE": "sublimation", "ONLY_SUBJECT": PRESET}):
            ideas = smart_niche.find_trending_niches(1)
            self.assertEqual([(i["type"], i["preset"]) for i in ideas], [("sublimation", PRESET)])
            spec = research.product_spec(ideas[0])
        self.assertEqual((spec["count"], spec["look"], len(spec["designs"])), (12, "retro", 12))
        self.assertEqual(research.title_problems(spec["title"]), [])
        built = sublimation.build(spec, "test-vintage")
        self.assertEqual(built["count"], 12)
        self.assertEqual(len(fake_image.prompts), 12)
        self.assertIn("flat 2D vector", fake_image.prompts[0])
        self.assertIn("dense maximalist composition", fake_image.prompts[0])
        self.assertNotIn("realistic illustration", fake_image.prompts[0])  # the preset's own style, not the shop style
        names = []
        for _, data in built["delivery"]:
            names += zipfile.ZipFile(io.BytesIO(data)).namelist()
        self.assertEqual(len([n for n in names if n.startswith("Designs-3600px/")]), 12)
        self.assertEqual(len([n for n in names if n.startswith("Mug-Wrap-11oz/")]), 12)

    def test_retro_design_is_transparent_and_worn(self):
        art = Image.new("RGBA", (1800, 1800), (0, 0, 0, 0))
        ImageDraw.Draw(art).ellipse((100, 100, 1700, 1700), fill=(196, 40, 44, 255))
        clean = Image.new("RGBA", (sublimation.SIZE, sublimation.SIZE), (0, 0, 0, 0))
        ImageDraw.Draw(clean).rectangle((400, 400, 3200, 3200), fill=(196, 40, 44, 255))
        worn = sublimation.distress(clean, seed=3)
        ink = lambda im: sum(im.getchannel("A").resize((300, 300)).histogram()[128:])
        self.assertLess(ink(worn), ink(clean))            # some ink is knocked out...
        self.assertGreater(ink(worn), ink(clean) * 0.85)  # ...but the design stays readable
        self.assertEqual(worn.tobytes(), sublimation.distress(clean, seed=3).tobytes())  # same file for the same product
        for k in range(3):
            d = sublimation.retro_design(art, "Too Cool For Yule", k, ["#C4282C", "#1C6E56", "#FAF0DC"], 5)
            self.assertEqual((d.size, d.mode), ((sublimation.SIZE, sublimation.SIZE), "RGBA"))
            self.assertEqual(d.getpixel((5, 5))[3], 0)  # transparent corners


if __name__ == "__main__":
    unittest.main()
