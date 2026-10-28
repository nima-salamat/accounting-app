import tempfile
import unittest
from pathlib import Path

from accounting_app.services.settings_store import load_settings, save_settings


class SettingsStoreTests(unittest.TestCase):
    def test_settings_round_trip_and_atomic_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "keys.json"
            settings = {"mode": "dark", "screen_saver_mode": "clock", "caption": "فارسی"}
            save_settings(path, settings)
            self.assertEqual(load_settings(path), settings)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_missing_or_corrupt_settings_return_empty_dictionary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "keys.json"
            self.assertEqual(load_settings(path), {})
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(load_settings(path), {})


if __name__ == "__main__":
    unittest.main()
