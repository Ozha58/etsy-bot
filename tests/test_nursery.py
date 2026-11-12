"""Personalized nursery wall art (custom, look "nursery"): original characters, name poster per order, room photos."""
import io
import json
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from bot import images, presets, quality, generator, photo_ratio, research
from bot.products import custom, custom_nursery

# names and words of existing films, shows and brands must never appear in this product
FORBIDDEN = ("paw patrol", "patrol", "chase", "marshall", "skye", "rubble", "rocky", "zuma", "everest", "ryder",
             "disney", "bluey", "pixar", "nickelodeon", "peppa", "mickey", "police", "firefighter", "badge")


def fake(prompts):
    def gen(prompt, w, h):
        prompts.append(prompt)
        if "interior photograph" in prompt:
            im = Image.new("RGB", (w, h), (232, 226, 216))
            ImageDraw.Draw(im).rectangle((0, int(h * .75), w, h), fill=(196, 170, 138))
            return im
        im = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(im)
        k = len(prompts)
        d.ellipse((240, 220, 780, 800), fill=(200 - 12 * k, 150, 60 + 20 * k))
        d.ellipse((380, 380, 470, 470), fill=(30, 30, 30))
        d.ellipse((560, 380, 650, 470), fill=(30, 30, 30))
        return im
    return gen


class NurseryTest(unittest.TestCase):
    def test_presets_are_valid_and_original(self):
        p = presets.load("custom", "nursery")
        themes = presets.variants(p)
        self.assertEqual([v["theme"] for v in themes], ["puppy", "safari", "woodland"])
        text = json.dumps(json.loads(Path("presets/custom/nursery.json").read_text()), ensure_ascii=False).lower()
        text += custom_nursery.ART_SUFFIX.lower() + " ".join(r[0] for r in custom_nursery.ROOMS).lower()
        for w in FORBIDDEN:
            if w == "badge":  # only allowed as "no badges" in the prompt suffix
                self.assertNotIn(w, json.dumps(themes).lower())
                continue
            self.assertNotIn(w, text, w)
        for v in themes:
            self.assertEqual(presets.problems(v, "custom"), [])
            self.assertEqual(len(v["designs"]), 6)

    def test_build_delivers_portraits_and_room_photos(self):
        prompts = []
        with mock.patch.object(images, "try_generate", fake(prompts)), \
                mock.patch.object(research, "_ask_intro", lambda *a, **k: "", create=True):
            spec = presets.spec({"type": "custom", "preset": "nursery", "theme": "puppy"})
            built = custom.build(spec, "test-nursery-art")
        self.assertEqual(len(prompts), 10)  # 6 portraits + 4 rooms
        self.assertTrue(5.99 <= spec["price_usd"] <= 8.99, spec["price_usd"])  # a poster set, not a $3 clip art
        self.assertEqual(sum("interior photograph" in p for p in prompts), 4)
        self.assertTrue(all("no badges" in p for p in prompts if "interior" not in p))
        # delivery: every portrait in the three print ratios, inside Etsy's limits
        self.assertLessEqual(len(built["delivery"]), 5)
        names = []
        for _, data in built["delivery"]:
            self.assertLessEqual(len(data), 20 * 1048576)
            names += zipfile.ZipFile(io.BytesIO(data)).namelist()
        jpgs = [n for n in names if n.endswith(".jpg")]
        self.assertEqual(len(jpgs), 18)
        z = zipfile.ZipFile(io.BytesIO(built["delivery"][0][1]))
        first = next(n for n in z.namelist() if n.endswith("3x4.jpg"))
        self.assertEqual(Image.open(io.BytesIO(z.read(first))).size, (3600, 4800))
        # photos: square, the cover is a room with three frames on the wall
        mock_ = photo_ratio.same_ratio(built["mockups"])
        self.assertEqual(len(mock_), 9)
        for _, b in mock_:
            self.assertEqual(Image.open(io.BytesIO(b)).size, (2000, 2000))
        cover = Image.open(io.BytesIO(mock_[0][1])).convert("RGB")
        row = [cover.getpixel((x, 560)) for x in range(0, 2000, 4)]
        paper = [sum(abs(a - b) for a, b in zip(px, custom_nursery.PAPER)) < 40 for px in row]
        runs = sum(1 for i in range(1, len(paper)) if paper[i] and not paper[i - 1])
        self.assertGreaterEqual(runs, 3)  # three posters hang side by side
        self.assertTrue(built["listing"]["is_personalizable"])
        # the whole product passes the quality gate without "instant download" cards (made to order)
        files = [{"name": n, "size": len(b)} for n, b in built["delivery"]]
        mock_ = quality.top_up_photos(quality.repair_cover(mock_), files, spec["title"], "custom")
        self.assertFalse(any("download-steps" in n or "files-included" in n for n, _ in mock_))
        p = {"title": spec["title"], "description": generator.compose_description(spec, built), "type": "custom",
             "tags": quality.fill_tags(spec["tags"], spec["title"]), "price_usd": spec["price_usd"], "spec": spec,
             "files": files}
        q = quality.score(p, mock_)
        self.assertGreaterEqual(q["total"], quality.TARGET, q)

    def test_order_gets_the_name_poster_in_three_colours_and_ratios(self):
        p = {"id": "20261112-09", "spec": {"look": "nursery"}, "custom_count": 6}
        files = custom.render(p, "Ethan")
        self.assertEqual(len(files), 9)
        self.assertEqual({n.split("-name-poster-")[1].split("-")[0] for n, _ in files}, {"blue", "pink", "sage"})
        sizes = {Image.open(io.BytesIO(b)).size for _, b in files}
        self.assertEqual(sizes, {(3600, 4800), (3600, 4500), (3508, 4961)})
        self.assertTrue(all(n.startswith("ethan-") for n, _ in files))
        blue = Image.open(io.BytesIO(files[0][1])).convert("RGB")
        self.assertEqual(blue.getpixel((30, 30))[:2], custom_nursery.PAPER[:2])  # clean paper at the edge
        dark = sum(1 for x in range(300, 3300, 20) for y in range(1900, 2700, 20) if sum(blue.getpixel((x, y))) < 150)
        self.assertGreater(dark, 150)  # the name in black across the middle
        # another name gives another poster; a name that cannot fit is refused with a clear message
        other = custom.render(p, "Mia")
        self.assertNotEqual(files[0][1], other[0][1])
        with self.assertRaises(ValueError):
            custom.render(p, "Maximilian Alexander")


if __name__ == "__main__":
    unittest.main()
