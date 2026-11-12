"""Buttons of a product made while the listener was already running must work (was: "Ürün bulunamadı")."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bot import config, storage


class FetchNewProductTest(unittest.TestCase):
    def test_missing_product_is_taken_from_github(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "STATE_KEY", "test-key"), \
                mock.patch.object(storage, "PRODUCTS_DIR", Path(d) / "state" / "products"), \
                mock.patch.object(config, "ROOT", Path(d)):
            storage.PRODUCTS_DIR.mkdir(parents=True)
            calls = []

            def fake_run(cmd, **kw):  # "git checkout origin/main -- file" writes the file the daily run pushed
                calls.append(cmd[:2])
                if cmd[1] == "checkout":
                    (Path(d) / cmd[-1]).write_bytes(storage.encrypt_bytes(b'{"id": "20261112-04", "title": "X"}'))
            with mock.patch.object(storage.subprocess, "run", fake_run):
                p = storage.load_product("20261112-04")
                self.assertEqual(p["title"], "X")
                self.assertEqual(calls, [["git", "fetch"], ["git", "checkout"]])
                calls.clear()
                self.assertIsNone(storage.load_product("../../etc"))  # never a path from outside
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
