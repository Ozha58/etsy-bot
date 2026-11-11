"""Preset test without spending image quota: image generation, the text AI and Etsy are replaced by fakes.

Run from the repo root:  python -m unittest tests.test_custom_preset -v
"""
import io
import os
import unittest
from unittest import mock

from PIL import Image, ImageChops, ImageDraw

from bot import assets, images, llm, presets, research, smart_niche, storage
from bot.products import custom

PRESET = "xmaskids"


def fake_image(prompt, width, height):
    """Stands in for Cloudflare FLUX: a coloured shape on a white background, no network, no quota."""
    fake_image.prompts.append(prompt)
    im = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(im).ellipse((width * 0.2, height * 0.2, width * 0.8, height * 0.8), fill=(180, 40, 50))
    return im


def fake_llm(prompt, system="", temperature=0.8):
    fake_llm.prompts.append(prompt)
    return {"intro": "Custom Kids Name Christmas PNG for the little ones.\n\nMade to order for shirts and mugs.",
            "styles": ["Whimsical", "Watercolor"], "price_usd": 99, "cover_scene": "a cozy living room at Christmas"}


class PresetTest(unittest.TestCase):
    def setUp(self):
        fake_image.prompts, fake_llm.prompts = [], []
        patches = [mock.patch.object(images, "try_generate", fake_image),
                   mock.patch.object(images, "generate", side_effect=AssertionError("real image call")),
                   mock.patch.object(llm, "ask_json", fake_llm),
                   mock.patch.object(research, "_score", lambda idea: None),
                   mock.patch.object(storage, "all_products", lambda: self.products)]
        self.products = []  # what the shop already made (decides the next theme)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _env(self, subject):
        return mock.patch.dict(os.environ, {"ONLY_TYPE": "custom", "ONLY_SUBJECT": subject})

    def test_preset_file_is_valid(self):
        preset = presets.load("custom", PRESET)
        self.assertEqual(presets.problems(preset, "custom"), [])
        self.assertLessEqual(len(preset["title"]), 140)
        self.assertEqual(len(preset["tags"]), 13)
        self.assertTrue(all(len(t) <= 20 for t in preset["tags"]))
        self.assertEqual(len(preset["designs"]), custom.COUNT)

    def test_uret_custom_preset_builds_six_named_designs(self):
        preset = presets.load("custom", PRESET)
        with self._env(PRESET):
            ideas = smart_niche.find_trending_niches(1)
        self.assertEqual([(i["type"], i["preset"]) for i in ideas], [("custom", PRESET)])
        spec = research.product_spec(ideas[0])

        # designs, taglines, title and tags come from the preset; the AI only wrote the description
        self.assertEqual(spec["title"], preset["title"])
        self.assertLessEqual(len(spec["title"]), 140)
        self.assertEqual(spec["tags"], preset["tags"])
        self.assertEqual([d["tagline"] for d in spec["designs"]], [d["tagline"] for d in preset["designs"]])
        self.assertEqual(len(fake_llm.prompts), 1)
        self.assertIn("Write the description", fake_llm.prompts[0])
        self.assertTrue(spec["intro"].startswith("Custom Kids Name Christmas PNG"))
        lo, hi = 2.99, 3.99  # settings.json custom range, must not be exceeded even when the AI says 99
        self.assertTrue(lo <= spec["price_usd"] <= hi, spec["price_usd"])

        built = custom.build(spec, research.slugify(spec["title"]))
        self.assertEqual(len(fake_image.prompts), custom.COUNT)
        for d, prompt in zip(preset["designs"], fake_image.prompts):
            self.assertIn(d["prompt"], prompt)
        self.assertEqual(sorted(built["extra_assets"]), [f"custom__art-{k}.png" for k in range(1, custom.COUNT + 1)])
        self.assertEqual(built["product_extra"], {"custom_count": custom.COUNT})
        self.assertEqual(built["listing"]["personalization_instructions"], preset["personalization_instructions"])
        self.assertEqual(built["listing"]["personalization_char_count_max"], 40)

        # an order arrives: the buyer's name is written into all 6 stored drawings
        product = {"id": "test-01", "spec": spec, "custom_count": built["product_extra"]["custom_count"]}
        with mock.patch.object(assets, "download", lambda pid, name: built["extra_assets"][name]):
            files = custom.render(product, "Emma Rose")
        designs = [(n, b) for n, b in files if "mug-wrap" not in n]
        self.assertEqual([n for n, _ in designs], [f"emma-rose-design-{k}.png" for k in range(1, custom.COUNT + 1)])
        self.assertEqual(len(files), custom.COUNT * 2)
        # festive look: 7 square listing photos, and the preset's own art style instead of the realistic shop style
        self.assertEqual(spec["look"], "festive")
        self.assertEqual(len(built["mockups"]), 7)
        for name, data in built["mockups"]:
            self.assertEqual(Image.open(io.BytesIO(data)).size, (2000, 2000), name)
        self.assertNotIn("realistic", fake_image.prompts[0])
        long_name = custom._design(spec, Image.new("RGBA", (2400, 3000), (180, 40, 50, 255)), "The Johnson-Williams Family", 0)
        self.assertEqual(long_name.size, (custom.SIZE, custom.SIZE))
        for k, (name, data) in enumerate(designs):
            im = Image.open(io.BytesIO(data))
            self.assertEqual((im.size, im.mode), ((custom.SIZE, custom.SIZE), "RGBA"), name)
            # name + drawing + tagline is clearly more ink than the drawing with an empty name line
            art = Image.open(io.BytesIO(built["extra_assets"][f"custom__art-{k + 1}.png"])).convert("RGBA")
            tag, ink, layout = custom._style(spec, k)
            self.assertEqual(tag, preset["designs"][k]["tagline"])
            bare = custom.compose(art, ".", "", ink, layout)
            painted = lambda x: sum(x.getchannel("A").resize((90, 90)).histogram()[41:])
            self.assertGreater(painted(im), painted(bare) * 1.1, name)

    def test_every_theme_is_valid_and_different(self):
        vs = presets.variants(presets.load("custom", PRESET))
        self.assertGreaterEqual(len(vs), 6)
        for v in vs:
            self.assertEqual(presets.problems(v, "custom"), [], v["theme"])
            self.assertLessEqual(len(v["title"]), 140)
        for field in ("title", "search_query"):
            self.assertEqual(len({v[field] for v in vs}), len(vs), field)
        prompts = [d["prompt"] for v in vs for d in v["designs"]]
        self.assertEqual(len(set(prompts)), len(prompts))
        # every theme has its own look: colours of the names, cover backdrop and cover line all differ
        from bot.products import custom_festive as F
        skins = [F.skin(v["theme"]) for v in vs]
        for v in vs:
            self.assertIn(v["theme"], F.SKINS, v["theme"])
        for key in ("sub",):
            self.assertEqual(len({s[key] for s in skins}), len(vs), key)
        self.assertEqual(len({s["backdrops"][0] for s in skins}), len(vs), "cover backdrop")
        self.assertEqual(len({tuple(r[0] for r in s["schemes"]) for s in skins}), len(vs), "name colours")
        # products made before skins (no "skin" in their spec) keep the classic look they were listed with
        self.assertIs(F.skin(None), F.SKINS["classic"])
        self.assertEqual(F.SKINS["classic"]["schemes"], F.SCHEMES)

    def test_each_run_takes_a_theme_not_made_yet(self):
        order = [v["theme"] for v in presets.variants(presets.load("custom", PRESET))]
        made = []
        for i in range(len(order) + 1):
            with self._env(PRESET):
                idea = smart_niche.find_trending_niches(1)[0]
            made.append(idea["theme"])
            spec = research.product_spec(idea)
            self.assertEqual((spec["preset"], spec["theme"]), (PRESET, idea["theme"]))
            self.products.append({"spec": spec, "status": "pending", "created_at": i})
        self.assertEqual(made[:len(order)], order)  # all themes once, in file order
        self.assertEqual(made[-1], order[0])        # then the one made longest ago
        self.products[0]["status"] = "rejected"     # a rejected product does not use up its theme
        self.products = self.products[:3]
        with self._env(PRESET):
            self.assertEqual(smart_niche.find_trending_niches(1)[0]["theme"], order[0])

    def test_theme_can_be_asked_for_by_name(self):
        with self._env(PRESET + " dino"):
            idea = smart_niche.find_trending_niches(1)[0]
        spec = research.product_spec(idea)
        self.assertEqual(spec["theme"], "dino")
        self.assertIn("Dinosaur", spec["title"])
        self.assertIn("dinosaur", spec["designs"][0]["prompt"])
        with self._env(PRESET + " nosuchtheme"), self.assertRaises(RuntimeError):
            smart_niche.find_trending_niches(1)

    def test_name_coloring_pages(self):
        from bot.products import custom_coloring
        preset = presets.load("custom", "boyama")
        themes = [v["theme"] for v in presets.variants(preset)]
        self.assertEqual(themes, ["name", "birthday", "babyshower", "christmas"])
        for v in presets.variants(preset):
            self.assertEqual(presets.problems(v, "custom"), [], v["theme"])
        with self._env("boyama birthday"):
            idea = smart_niche.find_trending_niches(1)[0]
        spec = research.product_spec(idea)
        self.assertEqual((spec["look"], spec["theme"], spec["art"], spec["above"]), ("coloring", "birthday", False, "Happy Birthday"))
        self.assertLessEqual(len(spec["title"]), 140)
        built = custom.build(spec, research.slugify(spec["title"]))
        self.assertEqual(fake_image.prompts, [])  # lettering only: no drawing is generated, no image quota is used
        self.assertEqual(built["extra_assets"], {})
        self.assertEqual(built["product_extra"], {"custom_count": custom.COUNT})
        self.assertTrue(built["listing"]["personalization_is_required"])
        self.assertEqual(len(built["mockups"]), 6)
        for name, data in built["mockups"]:
            self.assertEqual(Image.open(io.BytesIO(data)).size, (2000, 2000), name)
        self.assertNotIn("mug", " ".join(built["included"]).lower())

        # an order: two PDFs with 6 pages each, nothing has to be downloaded
        product = {"id": "test-02", "spec": spec, "custom_count": custom.COUNT}
        with mock.patch.object(assets, "download", side_effect=AssertionError("no drawing to download")):
            files = custom.render(product, "Emma Rose")
        self.assertEqual([n for n, _ in files], ["emma-rose-coloring-pages-US-Letter.pdf", "emma-rose-coloring-pages-A4.pdf"])
        for name, data in files:
            self.assertTrue(data.startswith(b"%PDF"), name)
            self.assertEqual(data.count(b"/Type /Page\n") + data.count(b"/Type /Page "), custom.COUNT, name)

        pages = [custom_coloring.page(None, "Emma", spec, k) for k in range(custom.COUNT)]
        for k, pg in enumerate(pages):
            self.assertEqual(pg.size, custom_coloring.LETTER)
            self.assertEqual(sum(pg.histogram()[1:255]), 0, k)  # pure black and white, prints crisp
            black = pg.histogram()[0] / (pg.width * pg.height)
            self.assertTrue(0.02 < black < 0.30, (k, black))    # outlines only: nearly everything is left to colour
            other = custom_coloring.page(None, "Noah", spec, k)
            self.assertIsNotNone(ImageChops.difference(pg, other).getbbox(), k)  # the name really is on the page
        self.assertEqual(len({pg.tobytes() for pg in pages}), custom.COUNT)      # six different layouts
        for long in ("Alexander-Christopher Montgomery", "Al", "The Johnson-Williams Family"):
            for k in range(custom.COUNT):
                self.assertEqual(custom_coloring.page(None, long, spec, k, custom_coloring.A4).size, custom_coloring.A4)

    def test_product_without_look_keeps_plain_design(self):
        art = Image.new("RGBA", (900, 900), (180, 40, 50, 255))
        spec = {"designs": [{"tagline": "Teach Love Inspire"}] * custom.COUNT, "palette": ["#B3262E"]}
        tag, ink, layout = custom._style(spec, 0)
        old = custom.compose(art, "Mrs. Johnson", tag, ink, layout)
        self.assertEqual(custom._design({"spec": spec}, art, "Mrs. Johnson", 0).tobytes(), old.tobytes())

    def test_subject_without_preset_keeps_old_behaviour(self):
        with self._env("teacher"):
            self.assertIsNone(presets.for_request())
        self.assertIsNone(presets.load("custom", "../../settings"))
        idea = {"type": "custom", "niche": "custom teacher name png", "search_query": "custom teacher png"}
        with self.assertRaises(RuntimeError):  # the fake answer is not a full plan: proves the normal AI path ran
            research.product_spec(idea)
        self.assertEqual(len(fake_llm.prompts), 3)
        self.assertIn("Create a complete Etsy digital product listing plan", fake_llm.prompts[0])


if __name__ == "__main__":
    unittest.main()
