"""Regression tests for login keyboard flow and independent numbering settings."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from client.api_client import ApiError
from client.ui.auth_page import AuthPage
from client.ui.invoice_numbering_page import InvoiceNumberingPage
from client.ui.invoice_templates_page import InvoiceTemplatesPage
from client.ui.invoice_render import DEFAULT_TEMPLATE


class _WindowStub:
    def __init__(self):
        self.current_user = {"username": "test-admin", "is_admin": True}
        self.api = None
        self.invoice_templates_page = None
        self.status = ""
        self.errors = []

    def show_error(self, error):
        self.errors.append(str(error))

    def set_status(self, message):
        self.status = str(message)

    def run_api(self, operation, callback, failure=None, busy=None):
        try:
            result = operation()
        except Exception as error:
            if failure:
                failure(error)
            else:
                self.errors.append(str(error))
        else:
            callback(result)


class LoginKeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.connect_patch = patch.object(AuthPage, "connect_server", lambda _self: None)
        self.connect_patch.start()
        self.page = AuthPage()
        self.page.show()
        self.page.activateWindow()
        self.app.processEvents()

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.connect_patch.stop()
        self.app.processEvents()

    def _tab_from_to(self, first, second):
        first.setFocus()
        self.app.processEvents()
        QTest.keyClick(first, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), second)

    def test_tab_order_is_explicit_across_nested_password_row(self):
        for first, second in (
            (self.page.server_url, self.page.connect_button),
            (self.page.connect_button, self.page.username),
            (self.page.username, self.page.password),
            (self.page.password, self.page.password_visibility_button),
            (self.page.password_visibility_button, self.page.client_name),
            (self.page.client_name, self.page.remember_session_checkbox),
            (self.page.remember_session_checkbox, self.page.login_button),
        ):
            with self.subTest(first=first.objectName() or type(first).__name__):
                self._tab_from_to(first, second)

    def test_username_enter_moves_to_password_and_visibility_control_is_icon_only(self):
        self.page.username.setText("cashier")
        self.page.password.setText("Secret-1234")
        self.page.username.setFocus()
        QTest.keyClick(self.page.username, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), self.page.password)

        toggle = self.page.password_visibility_button
        self.assertEqual(toggle.text(), "")
        self.assertTrue(toggle.toolTip())
        self.assertTrue(toggle.accessibleName())
        toggle.setChecked(True)
        self.assertEqual(self.page.password.echoMode(), QLineEdit.EchoMode.Normal)
        self.assertEqual(self.page.password.text(), "Secret-1234")
        toggle.setChecked(False)
        self.assertEqual(self.page.password.echoMode(), QLineEdit.EchoMode.Password)

    def test_api_error_uses_parsed_detail_without_internal_request_path(self):
        error = ApiError(422, "نام کاربری: این فیلد الزامی است.", "POST", "/api/v1/auth/login")
        self.page._default_failure("test-ticket", error)
        self.assertEqual(self.page.message.text(), "نام کاربری: این فیلد الزامی است.")
        self.assertNotIn("/api/v1/auth/login", self.page.message.text())


class InvoiceNumberingPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = _WindowStub()
        self.designer = InvoiceTemplatesPage(self.window)
        self.window.invoice_templates_page = self.designer
        self.page = InvoiceNumberingPage(self.window)

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.designer.close()
        self.designer.deleteLater()
        self.app.processEvents()

    def test_numbering_has_its_own_page_and_is_not_shown_in_invoice_designer(self):
        self.assertIs(self.designer.invoice_number_card.parentWidget(), self.designer)
        self.assertEqual(
            self.designer.invoice_number_card.objectName(),
            "InvoiceNumberingCompatibilityCard",
        )
        self.assertEqual(
            self.designer.layout().indexOf(self.designer.invoice_number_card), -1
        )
        self.assertEqual(self.page.invoice_number_style.currentData(), "date_daily")
        self.assertEqual(self.page.title_label.text(), "شماره‌گذاری فاکتور")

    def test_friendly_builder_generates_format_and_preview(self):
        self.page.invoice_number_style.setCurrentIndex(
            self.page.invoice_number_style.findData("prefix_date_daily")
        )
        self.page.invoice_number_prefix.setText("NUM")
        self.page.invoice_number_padding.setValue(5)
        self.assertEqual(
            self.page._build_invoice_number_format(),
            "NUM-{YYYY}-{MM}-{DD}-{NUM}",
        )
        self.assertIn("NUM-۲۰۲۶-۱۰-۲۹-۰۱۰۰۱", self.page.invoice_number_example.text())

    def test_unknown_saved_pattern_is_preserved_in_advanced_mode(self):
        self.page._load_template({
            **DEFAULT_TEMPLATE,
            "invoice_number_format": "2026-{MM}-{D}-NUM-{NUM}",
            "invoice_number_padding": 4,
        })
        self.assertEqual(self.page.invoice_number_style.currentData(), "custom")
        self.assertEqual(
            self.page.invoice_number_custom_format.text(), "2026-{MM}-{D}-NUM-{NUM}"
        )
