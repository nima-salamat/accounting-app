"""Regression tests for strict client/server process separation."""
import os
import subprocess
import unittest
from unittest.mock import patch

import main


class DesktopEntryPointTests(unittest.TestCase):
    def test_default_launch_never_starts_server_process(self):
        with patch.dict(os.environ, {"ACCOUNTING_APP_API_URL": ""}, clear=False):
            with patch("subprocess.Popen") as spawn_process:
                with patch("client.desktop.main", return_value=0) as desktop_main:
                    self.assertEqual(main.run([]), 0)
        spawn_process.assert_not_called()
        desktop_main.assert_called_once()

    def test_custom_api_url_is_passed_without_spawning_server(self):
        with patch.dict(os.environ, {"ACCOUNTING_APP_API_URL": ""}, clear=False):
            with patch("subprocess.Popen") as spawn_process:
                with patch("client.desktop.main", return_value=0) as desktop_main:
                    self.assertEqual(main.run(["--api-url", "https://accounting.example.test"]), 0)
                    self.assertEqual(os.environ["ACCOUNTING_APP_API_URL"], "https://accounting.example.test")
        spawn_process.assert_not_called()
        desktop_main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
