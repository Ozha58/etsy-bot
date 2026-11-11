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
        shopfix._llm_fails[0] = 0
        with mock.patch.object(llm, "ask_json", side_effect=llm.LLMError("429 quota")) as ask:
            for _ in range(4):
                seo = shopfix.new_seo(li, "coloring")
        self.assertTrue(seo["no_llm"])
        self.assertEqual(ask.call_count, 2)  # after two failures the run stops asking (no minutes lost per listing)
        shopfix._llm_fails[0] = 0

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
        self.assertEqual(len(treated), 5)  # photos and descriptions of every listing are still repaired
        self.assertEqual(meta.get("shopfix_done"), {})  # nothing marked done: the next /tedavi retries them
        self.assertTrue(any("kota" in t for t in sent))

    def test_closeups_show_whole_designs_and_never_cut_text_cards(self):
        grid = Image.new("RGB", (2000, 2000), (244, 240, 234))  # four designs on a calm sheet
        d = ImageDraw.Draw(grid)
        for cx, cy in ((520, 520), (1480, 520), (520, 1480), (1480, 1480)):
            d.ellipse((cx - 300, cy - 300, cx + 300, cy + 300), fill=(190, 60, 50))
            d.rectangle((cx - 120, cy - 120, cx + 120, cy + 120), fill=(30, 110, 80))
        card = Image.new("RGB", (2000, 2000), (250, 246, 239))  # a text card: lines of dark text
        dc = ImageDraw.Draw(card)
        for y in range(300, 1700, 140):
            dc.rectangle((150, y, 1750, y + 60), fill=(20, 30, 70))
        ups = shopfix.closeups([card, grid], 3)
        self.assertEqual(len(ups), 1)  # nothing from the text card
        up = ups[0]
        self.assertEqual(up.size, (2000, 2000))
        edge = [up.getpixel((x, y)) for x in range(0, 2000, 50) for y in (8, 1991)] + \
               [up.getpixel((x, y)) for y in range(0, 2000, 50) for x in (8, 1991)]
        calm = sum(1 for p in edge if max(p) - min(p) < 50 and sum(p) > 600)
        self.assertGreater(calm / len(edge), 0.9)  # the design is not cut by the frame
        self.assertGreater(max(up.getpixel((1000, 1000))) - min(up.getpixel((1000, 1000))), 50)  # and fills the middle

        extra = [n for n, _ in shopfix.extra_photos(grid, [card, grid], [{"filename": "a.zip", "size": 5 << 20}], TITLE, 6)]
        self.assertEqual(extra, ["detail-1.jpg", "info-whats-included.jpg", "file-details.jpg", "good-to-know.jpg",
                                 "how-to-download.jpg"])  # artwork first, download help last
        two = [n for n, _ in shopfix.extra_photos(grid, [card, grid], [{"filename": "a.zip", "size": 5 << 20}], TITLE, 2)]
        self.assertEqual(two, ["detail-1.jpg", "info-whats-included.jpg"])

    def test_first_treatment_photos_are_found_for_replacement(self):
        def im(rank, label):
            return {"listing_image_id": rank, "rank": rank, "alt_text": f"Some Title, B, C - {label}"}
        v1 = [im(1, "cover preview"), im(2, "page preview"), im(3, "what is included"), im(4, "what is included"),
              im(5, "how to download"), im(6, "file formats and details"), im(7, "close-up detail"), im(8, "close-up detail")]
        self.assertEqual([i["rank"] for i in shopfix.old_extras(v1)], [4, 5, 6, 7, 8])
        own = [im(1, "cover preview"), im(2, "close-up detail"), im(3, "what is included")]
        self.assertEqual(shopfix.old_extras(own), [])  # a product's own detail photo stays
        v2 = [im(1, "cover preview"), im(2, "close-up detail"), im(3, "what is included"), im(4, "how to download")]
        self.assertEqual(shopfix.old_extras(v2), [])  # the new order is never touched again

    def test_second_run_does_not_add_the_extra_photos_again(self):
        from unittest import mock
        from bot import etsy
        imgs = [{"listing_image_id": k, "rank": k, "alt_text": f"Bee Pages, B, C - {lab}"} for k, lab in
                enumerate(["cover preview", "page preview", "close-up detail", "what is included", "how to download"], 1)]
        li = {"listing_id": 7, "title": "Bee Coloring Pages, Printable PDF Book, Kids Spring Activity",
              "tags": [], "description": ""}
        added = []
        with mock.patch.object(etsy, "listing_images", lambda lid: imgs), \
                mock.patch.object(etsy, "listing_files", lambda lid: [{"filename": "bee.zip", "size_bytes": 1 << 20}]), \
                mock.patch.object(etsy, "listing_video_count", lambda lid: 1), \
                mock.patch.object(etsy, "update_listing", lambda *a, **k: None, create=True), \
                mock.patch.object(etsy, "download_image", lambda im: photo((245, 240, 232), im["rank"])), \
                mock.patch.object(etsy, "add_image", lambda *a, **k: added.append(a)), \
                mock.patch.object(etsy, "delete_image", lambda *a, **k: self.fail("nothing to delete")), \
                mock.patch.object(shopfix, "new_seo", lambda *a, **k: {"title": li["title"], "tags": [], "styles": []}):
            notes = shopfix.treat_listing(li, None, dry_run=True)
        self.assertEqual(added, [])
        self.assertFalse(any("foto" in n and "+" in n for n in notes), notes)

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
