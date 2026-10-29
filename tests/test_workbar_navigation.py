"""UI regressions for the empty landing page and inline second-row navigation."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel

from client.ui.auth_page import AuthPage
from client.ui.main_window import AccountingMainWindow


class WorkbarNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.auth_connect_patcher = patch.object(AuthPage, "connect_server", autospec=True)
        self.auth_connect_patcher.start()
        self.window = AccountingMainWindow()
        self.window.current_user = {"username": "navigation-test", "is_admin": True}
        # Treat all entries as permitted so the test measures navigation layout, not RBAC.
        for button, _admin_only in self.window._nav.values():
            button.setVisible(True)

    def tearDown(self):
        self.window.close()
        self.auth_connect_patcher.stop()
        self.app.processEvents()

    def test_default_home_is_blank_and_has_no_submenu_or_user_status_row(self):
        self.window.navigate("home")
        self.assertIs(self.window.page_stack.currentWidget(), self.window._pages["home"])
        self.assertEqual(self.window.breadcrumb.text(), "")
        self.assertEqual(self.window.page_subtitle.text(), "")
        self.assertTrue(self.window.status_bar_frame.isHidden())
        self.assertTrue(self.window.workbar_submenu_frame.isHidden())
        self.assertEqual(self.window._pages["home"].findChildren(QLabel), [])

    def test_category_entries_render_in_second_row_and_can_be_collapsed(self):
        self.window._toggle_workbar_group("accounting")
        self.assertFalse(self.window.workbar_submenu_frame.isHidden())
        self.assertEqual(
            set(self.window._nav_actions),
            {"purchases", "checks_in", "checks_out", "journals", "fiscal_years", "accounting_reports", "audit"},
        )
        self.assertEqual(self.window.workbar_submenu_layout.count(), 8)  # seven buttons + stretch
        self.window._toggle_workbar_group("accounting")
        self.assertTrue(self.window.workbar_submenu_frame.isHidden())
        self.assertEqual(self.window._nav_actions, {})

    def test_switching_category_replaces_the_second_row(self):
        self.window._toggle_workbar_group("sales")
        self.assertEqual(set(self.window._nav_actions), {"sales", "receipts", "returns"})
        self.window._toggle_workbar_group("templates")
        self.assertEqual(set(self.window._nav_actions), {"invoices", "invoice_numbering", "settings"})
        self.assertEqual(self.window.workbar_submenu_layout.count(), 3)  # two buttons + stretch


if __name__ == "__main__":
    unittest.main()
