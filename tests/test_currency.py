"""Regression coverage for shared Rial/Toman display and form conversion."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from decimal import Decimal

from PySide6.QtWidgets import QApplication, QLabel, QLineEdit
from pydantic import ValidationError

from client.ui.currency import (
    format_currency, format_display_amount, set_currency_unit,
    to_base_amount, to_display_amount,
)
from client.ui.forms import RecordDialog
from client.ui.invoice_render import DEFAULT_TEMPLATE, render_invoice_html
from server.app.schemas import AppearanceSettingsUpdate


class CurrencyDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.original_unit = "toman"
        set_currency_unit(self.original_unit)

    def tearDown(self):
        set_currency_unit(self.original_unit)
        self.app.processEvents()

    def test_toman_and_rial_display_formatting(self):
        self.assertEqual(format_currency(125000), "125,000 تومان")
        set_currency_unit("rial")
        self.assertEqual(format_currency(125000), "1,250,000 ریال")
        self.assertEqual(format_currency(125000, include_unit=False), "1,250,000")
        self.assertEqual(format_display_amount(125000), "125,000 ریال")

    def test_invoice_receipt_uses_the_selected_unit_in_table_headers_and_prices(self):
        set_currency_unit("rial")
        receipt = {
            "id": "currency-receipt",
            "total_price": 200,
            "items": [
                {"product_name": "قلم", "quantity": 2, "sell_price": 100},
            ],
        }
        html = render_invoice_html(receipt, DEFAULT_TEMPLATE)
        self.assertIn("قیمت واحد (ریال)", html)
        self.assertIn("جمع (ریال)", html)
        self.assertIn("۱,۰۰۰", html)
        self.assertIn("۲,۰۰۰ ریال", html)

    def test_conversion_preserves_the_internal_toman_amount(self):
        set_currency_unit("rial")
        displayed = to_display_amount(Decimal("125000"))
        self.assertEqual(displayed, Decimal("1250000"))
        self.assertEqual(to_base_amount(displayed), Decimal("125000"))
        self.assertEqual(format_currency(to_base_amount(displayed)), "1,250,000 ریال")

    def test_currency_aware_record_form_displays_selected_unit_and_saves_base_amount(self):
        set_currency_unit("rial")
        dialog = RecordDialog(
            "محصول",
            [{
                "key": "sell_price", "label": "قیمت فروش",
                "kind": "number", "required": True, "currency": True,
            }],
            record={"sell_price": 125000},
        )
        control = dialog.inputs["sell_price"]
        self.assertIsInstance(control, QLineEdit)
        self.assertEqual(control.text(), "1250000")
        self.assertTrue(any("ریال" in label.text() for label in dialog.findChildren(QLabel)))
        control.setText("1750000")
        value = Decimal(dialog.values()["sell_price"])
        self.assertEqual(value, Decimal("175000"))
        dialog.close()

    def test_server_shared_settings_accept_only_supported_currency_units(self):
        values = AppearanceSettingsUpdate()
        self.assertEqual(values.currency_unit, "toman")
        self.assertEqual(AppearanceSettingsUpdate(currency_unit="rial").currency_unit, "rial")
        with self.assertRaises(ValidationError):
            AppearanceSettingsUpdate(currency_unit="dinar")


if __name__ == "__main__":
    unittest.main()
