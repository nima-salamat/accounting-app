"""Regression tests for the desktop entry point's server lifecycle."""
import os
import unittest
from unittest.mock import patch

import main


class DesktopEntryPointTests(unittest.TestCase):
    def test_default_launch_never_starts_a_local_server(self):
        with patch.dict(os.environ, {"ACCOUNTING_APP_API_URL": ""}, clear=False):
            with patch.object(main, "_start_local_server") as start_server:
                with patch("client.desktop.main", return_value=0) as desktop_main:
                    self.assertEqual(main.run([]), 0)
        start_server.assert_not_called()
        desktop_main.assert_called_once()

    def test_local_server_requires_explicit_opt_in(self):
        fake_process = object()
        with patch.dict(os.environ, {"ACCOUNTING_APP_API_URL": ""}, clear=False):
            with patch.object(main, "_start_local_server", return_value=(fake_process, "http://127.0.0.1:8123")) as start_server:
                with patch.object(main, "_stop_local_server") as stop_server:
                    with patch("client.desktop.main", return_value=0) as desktop_main:
                        self.assertEqual(main.run(["--with-local-server"]), 0)
        start_server.assert_called_once_with()
        stop_server.assert_called_once_with(fake_process)
        desktop_main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
