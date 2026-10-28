import unittest
from pathlib import Path

from accounting_app.config import get_data_dir, get_database_path, get_keys_path


class ConfigPathTests(unittest.TestCase):
    def test_windows_uses_local_app_data(self):
        path = get_data_dir(
            {"LOCALAPPDATA": "C:/Users/demo/AppData/Local"},
            is_windows=True,
            home="C:/Users/demo",
        )
        self.assertEqual(path, Path("C:/Users/demo/AppData/Local") / "accounting_app")

    def test_xdg_path_is_respected(self):
        path = get_data_dir({"XDG_DATA_HOME": "/tmp/demo-data"}, is_windows=False, home="/home/demo")
        self.assertEqual(path, Path("/tmp/demo-data") / "accounting_app")

    def test_home_fallback_is_portable(self):
        path = get_data_dir({}, is_windows=False, home="/home/demo")
        self.assertEqual(path, Path("/home/demo/.local/share/accounting_app"))

    def test_explicit_path_overrides(self):
        env = {
            "ACCOUNTING_APP_DATA_DIR": "/tmp/custom-data",
            "ACCOUNTING_APP_DB_PATH": "/tmp/custom-data/custom.sqlite3",
        }
        self.assertEqual(get_data_dir(env), Path("/tmp/custom-data"))
        self.assertEqual(get_database_path(env), Path("/tmp/custom-data/custom.sqlite3"))
        self.assertEqual(get_keys_path(env), Path("/tmp/custom-data/keys.json"))


if __name__ == "__main__":
    unittest.main()
