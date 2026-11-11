"""Quality gate: repairs (tags, first sentence, dark cover, 10 photos) and the 100 point checklist."""
import io
import unittest

from PIL import Image, ImageDraw

from bot import config, quality, research, shopfix, social, watermark
from bot.imgutil import jpeg_bytes

TITLE = "Honey Bee Coloring Pages, Printable PDF Coloring Book, Spring Garden Kids Activity"


def photo(color, k=0, size=(2000, 2000)):
    im = Image.new("RGB", size, color)
    ImageDraw.Draw(im).ellipse((200 + 150 * k, 300, 900 + 150 * k, 1000 + 60 * k), fill=(200 - 15 * k, 90 + 10 * k, 60))
    return jpeg_bytes(im, 88, dpi=72)


def product(**kw):
    desc = ("✨ Honey Bee Coloring Pages for calm spring afternoons. " + "Detailed garden scenes to color. " * 30 +
            "\n\n🎁 WHAT'S INCLUDED\n• 20 PDF pages, US Letter and A4, 300 DPI\n\n💡 HOW TO USE\n• Print at home\n\n"
            "📌 PLEASE NOTE\n• This is a digital download. No physical item will be shipped.\n"
            "• Your files are available right after purchase under Purchases & Reviews.\n"
            "• Artwork created with the help of AI tools.\n• Personal use only.")
    p = {"title": TITLE, "description": desc, "type": "coloring", "price_usd": 2.99, "spec": {"styles": ["Vintage"]},
         "tags": ["bee coloring pages", "printable coloring", "spring activity", "kids coloring book", "garden printable",
                  "honey bee art", "insect coloring", "adult coloring pdf", "teacher resource", "rainy day craft",
                  "bee lover gift", "nature line art", "homeschool page"],
         "files": [{"name": "bee-coloring.zip", "size": 9 * 1048576}]}
    p.update(kw)
    return p


class QualityTest(unittest.TestCase):
    def test_shop_name_is_foxlantern_everywhere(self):
        self.assertEqual(config.SHOP_NAME, "Foxlantern Studio")
        self.assertEqual(watermark.TEXT, "FOXLANTERN STUDIO")
        for text in (shopfix.ANNOUNCEMENT, shopfix.SALE_MESSAGE, shopfix.ABOUT_STORY):
            self.assertIn("Foxlantern Studio", text)
            self.assertNotIn("Sebasteia", text)
        self.assertEqual(social.HANDLE, "")  # no account name in post texts

    def test_shop_texts_with_the_old_name_are_rewritten(self):
        from unittest import mock
        from bot import etsy
        det = {"title": "Realistic Printables", "announcement": "Welcome to Sebasteia - printables",
               "sale_message": "Thanks from Sebasteia!", "digital_sale_message": "Thank you!", "policy_additional": "x"}
        sent = {}
        with mock.patch.object(etsy, "shop_details", lambda: det), \
                mock.patch.object(etsy, "update_shop", lambda **kw: sent.update(kw)):
            shopfix.treat_shop()
        self.assertEqual(set(sent), {"announcement", "sale_message"})
        self.assertIn("Foxlantern Studio", sent["announcement"])

    def test_tedavi_waits_when_gemini_quota_is_full(self):
        from unittest import mock
        from bot import etsy, llm, storage, telegram
        li = {"listing_id": 1, "title": "Bee Pages - Cute Bee Coloring", "tags": ["bee"], "description": "x"}
        with mock.patch.object(llm, "ask_json", side_effect=llm.LLMError("429 quota")) as ask:
            seo = shopfix.new_seo(li, "coloring")
        self.assertTrue(seo["no_llm"])
        self.assertEqual(ask.call_count, 1)  # no pointless retries when the quota is gone

        meta, treated, sent = {}, [], []
        listings = [dict(li, listing_id=k) for k in range(5)]
        with mock.patch.object(etsy, "shop_listings", lambda state: listings), \
                mock.patch.object(etsy, "shop_details", lambda: {}), \
                mock.patch.object(storage, "all_products", lambda: []), \
                mock.patch.object(storage, "load_meta", lambda: meta), \
                mock.patch.object(storage, "save_meta", lambda m: None), \
                mock.patch.object(telegram, "send", lambda *a, **k: sent.append(a[0])), \
                mock.patch.object(shopfix, "treat_listing", lambda l, p, d: treated.append(l) or [shopfix.NO_LLM]):
            shopfix.run(shop_part=False)
        self.assertEqual(len(treated), 2)  # stops after two listings instead of grinding through all of them
        self.assertEqual(meta.get("shopfix_done"), {})  # nothing marked done: the next /tedavi retries them
        self.assertTrue(any("kota" in t for t in sent))

    def test_first_sentence_gets_the_title_lead(self):
        out = quality.lead_intro("A calm set of garden scenes for spring.", TITLE)
        self.assertTrue(out.startswith("Honey Bee Coloring Pages"))
        same = "Honey Bee Coloring Pages bring the garden to your desk."
        self.assertEqual(quality.lead_intro(same, TITLE), same)

    def test_tags_are_topped_up_to_13_valid_ones(self):
        tags = quality.fill_tags(["bee coloring pages", "spring activity", "a tag that is far too long for etsy"], TITLE)
        self.assertEqual(len(tags), 13)
        self.assertEqual(len({t.lower() for t in tags}), 13)
        self.assertTrue(all(len(t) <= 20 for t in tags))
        self.assertGreaterEqual(sum(len(t.split()) >= 2 for t in tags), 10)
        self.assertEqual(research.tag_problems(tags)[:0], [])

    def test_dark_cover_is_brightened_and_bright_one_untouched(self):
        dark = [("00-cover.jpg", photo((40, 36, 44))), ("01.jpg", photo((240, 240, 240), 1))]
        fixed = quality.repair_cover(dark)
        self.assertGreater(quality.brightness(Image.open(io.BytesIO(fixed[0][1]))),
                           quality.brightness(Image.open(io.BytesIO(dark[0][1]))) + 10)
        self.assertEqual(fixed[1], dark[1])
        bright = [("00-cover.jpg", photo((245, 240, 232)))]
        self.assertEqual(quality.repair_cover(bright), bright)

    def test_photos_are_topped_up_to_ten_square_ones(self):
        mock = [(f"{k:02d}-p.jpg", photo((245 - 6 * k, 240, 232), k)) for k in range(6)]
        out = quality.top_up_photos(mock, [{"name": "bee-coloring.zip", "size": 9 * 1048576}], TITLE)
        self.assertEqual(len(out), 10)
        self.assertEqual(out[:6], mock)
        self.assertEqual(len({n for n, _ in out}), 10)
        for _, b in out:
            self.assertEqual(Image.open(io.BytesIO(b)).size, (2000, 2000))
        self.assertEqual(quality.top_up_photos(out, [], TITLE), out)

    def test_ready_product_scores_90_and_weak_one_is_explained(self):
        mock = [(f"{k:02d}-p.jpg", photo((245 - 6 * k, 240, 232), k)) for k in range(6)]
        mock = quality.top_up_photos(mock, [{"name": "bee-coloring.zip", "size": 9 * 1048576}], TITLE)
        good = quality.score(product(), mock)
        self.assertGreaterEqual(good["total"], quality.TARGET, good)
        self.assertEqual(sum(m for _, m in good["parts"].values()), 100)
        self.assertIn("✅", quality.caption_lines(good)[0])

        weak = quality.score(product(title="Cute Bee Coloring Pages - Beautiful Bee Pages", tags=["bee"],
                                     description="Nice pages."), mock[:4])
        self.assertLess(weak["total"], 60)
        text = "\n".join(quality.caption_lines(weak))
        self.assertIn("⚠️", text)
        self.assertIn("etiket 1/13", text)
        self.assertIn("görsel 4/10", text)


if __name__ == "__main__":
    unittest.main()
