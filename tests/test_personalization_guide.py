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
