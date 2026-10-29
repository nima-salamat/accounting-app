"""Security-oriented unit tests for printable invoices."""
import unittest

from client.ui.invoice_render import (
    DEFAULT_TEMPLATE, default_elements_for_paper, page_dimensions,
    prepare_invoice_pages, render_invoice_html,
)
from accounting_app.services.invoice_numbering import format_invoice_number, validate_invoice_number_format


class InvoiceRenderTests(unittest.TestCase):
    def test_invoice_number_formats_support_date_daily_counter_and_minimum_padding(self):
        receipt = {
            "created_at": "2026-10-30T16:45:00",
            "day_receipt_id": 1,
            "invoice_sequence": 100001,
        }
        self.assertEqual(format_invoice_number(receipt, "{DATE}-{NUM}", 5), "2026-10-30-00001")
        self.assertEqual(format_invoice_number(receipt, "{YYYY}-{MM}-{D}-NUM-{NUM}", 5), "2026-10-3-NUM-00001")
        self.assertEqual(format_invoice_number(receipt, "{SEQ}", 5), "100001")
        self.assertEqual(
            format_invoice_number(dict(receipt, day_receipt_id=100001), "{DATE}-{NUM}", 5),
            "2026-10-30-100001",
        )

    def test_invoice_number_format_requires_a_unique_counter_pattern(self):
        self.assertEqual(validate_invoice_number_format("INV-{SEQ}"), "INV-{SEQ}")
        with self.assertRaises(ValueError):
            validate_invoice_number_format("INV-{DD}")
        with self.assertRaises(ValueError):
            validate_invoice_number_format("{DATE}-{UNKNOWN}")

    def test_stored_invoice_number_is_immutable_when_template_format_changes(self):
        receipt = {
            "id": "old-receipt", "day_receipt_id": 1,
            "invoice_number": "INV-2026-10-30-00001",
            "created_at": "2026-10-30T12:00:00", "items": [],
        }
        html = render_invoice_html(
            receipt, dict(DEFAULT_TEMPLATE, invoice_number_format="{SEQ}", invoice_number_padding=2)
        )
        self.assertIn("INV-۲۰۲۶-۱۰-۳۰-۰۰۰۰۱", html)
        self.assertNotIn("شماره فاکتور: ۰۱", html)

    def test_invoice_escapes_untrusted_template_and_product_text(self):
        html = render_invoice_html(
            {
                "id": "receipt-1",
                "day_receipt_id": 12,
                "total_price": 150,
                "items": [{
                    "product_name": "<script>alert(1)</script>",
                    "quantity": 1,
                    "sell_price": 150,
                }],
            },
            dict(DEFAULT_TEMPLATE, company_name="<b>Shop</b>", footer="<img src=x onerror=alert(1)>"),
        )
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>Shop</b>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;b&gt;Shop&lt;/b&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

    def test_custom_persian_font_and_typography_are_applied(self):
        html = render_invoice_html(
            {"id": "receipt-font", "total_price": 100, "items": []},
            dict(DEFAULT_TEMPLATE, font_family="Noto Naskh Arabic", font_size=14,
                 header_font_size=28, line_height=2.0, text_direction="rtl"),
        )
        self.assertIn('dir="rtl"', html)
        self.assertIn('font-family:"Noto Naskh Arabic"', html)
        self.assertIn("font-size:14pt", html)
        self.assertIn("font-size:28pt", html)
        self.assertIn("line-height:2.0", html)

    def test_standard_invoice_splits_items_across_real_pages_without_dropping_rows(self):
        items = [
            {"product_name": "کالای {}".format(index), "quantity": 1, "sell_price": 100}
            for index in range(100)
        ]
        pages = prepare_invoice_pages(
            {"id": "multi", "total_price": 10000, "items": items},
            DEFAULT_TEMPLATE,
        )
        self.assertGreater(len(pages), 1)
        self.assertEqual(sum(len(receipt["items"]) for receipt, _template in pages), len(items))
        self.assertFalse(pages[0][0]["_is_final_page"])
        self.assertTrue(pages[-1][0]["_is_final_page"])
        self.assertEqual(pages[1][0]["_row_start"], len(pages[0][0]["items"]))

    def test_thermal_roll_expands_for_all_items_in_one_continuous_output(self):
        template = dict(
            DEFAULT_TEMPLATE,
            paper_size="receipt80",
            orientation="portrait",
            margin_mm=4,
            elements=default_elements_for_paper("receipt80", "portrait", 4),
        )
        items = [
            {"product_name": "کالای {}".format(index), "quantity": 1, "sell_price": 100}
            for index in range(60)
        ]
        pages = prepare_invoice_pages(
            {"id": "roll", "total_price": 6000, "items": items},
            template,
        )
        self.assertEqual(len(pages), 1)
        _receipt, prepared = pages[0]
        width, height = page_dimensions(prepared)
        self.assertEqual(width, 80.0)
        self.assertGreater(height, 220.0)
        table = next(element for element in prepared["elements"] if element["type"] == "items_table")
        self.assertGreater(table["h_mm"], 137.0)

    def test_thermal_roll_keeps_long_tables_above_the_sheet_geometry_limit(self):
        template = dict(
            DEFAULT_TEMPLATE,
            paper_size="receipt80",
            orientation="portrait",
            margin_mm=4,
            elements=default_elements_for_paper("receipt80", "portrait", 4),
        )
        items = [
            {"product_name": "کالای {}".format(index), "quantity": 1, "sell_price": 100}
            for index in range(500)
        ]
        receipt = {"id": "long-roll", "total_price": 50000, "items": items}
        pages = prepare_invoice_pages(receipt, template)
        self.assertEqual(len(pages), 1)
        prepared_receipt, prepared_template = pages[0]
        _width, height = page_dimensions(prepared_template)
        table = next(element for element in prepared_template["elements"] if element["type"] == "items_table")
        self.assertGreater(table["h_mm"], 2000.0)
        self.assertGreater(height, table["y_mm"] + table["h_mm"])

        html = render_invoice_html(prepared_receipt, prepared_template)
        self.assertEqual(html.count("<tr>"), 501)  # Header plus all 500 products.
        self.assertIn("کالای 499", html)

    def test_text_elements_can_render_page_number_and_page_count(self):
        counter = {
            "id": "page-counter", "type": "text", "label": "شماره صفحه",
            "x_mm": 10, "y_mm": 270, "w_mm": 80, "h_mm": 8,
            "font_size": 8, "align": "center", "bold": False,
            "visible": True, "text": "صفحه {{page_number}} از {{page_count}}",
        }
        template = dict(DEFAULT_TEMPLATE, elements=list(DEFAULT_TEMPLATE["elements"]) + [counter])
        items = [
            {"product_name": "کالای {}".format(index), "quantity": 1, "sell_price": 10}
            for index in range(100)
        ]
        pages = prepare_invoice_pages({"id": "page-counter", "items": items}, template)
        self.assertGreater(len(pages), 1)
        digit_map = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        count_text = str(len(pages)).translate(digit_map)
        for page_index, (receipt, page_template) in enumerate(pages, start=1):
            html = render_invoice_html(receipt, page_template)
            expected = "صفحه {} از {}".format(str(page_index).translate(digit_map), count_text)
            self.assertIn(expected, html)

    def test_untrusted_font_family_cannot_inject_css(self):
        html = render_invoice_html(
            {"id": "receipt-font-safe", "total_price": 0, "items": []},
            dict(DEFAULT_TEMPLATE, font_family='"; } body { color:red; /*'),
        )
        self.assertNotIn('font-family:""; } body', html)
        self.assertIn('font-family:"Vazirmatn"', html)

    def test_invoice_contains_line_totals_and_supported_layout(self):
        html = render_invoice_html(
            {
                "id": "receipt-2",
                "day_receipt_id": 13,
                "total_price": 375,
                "items": [
                    {"product_name": "قلم", "quantity": 2, "sell_price": 100},
                    {"product_name": "دفتر", "quantity": 1, "sell_price": 175},
                ],
            },
            dict(DEFAULT_TEMPLATE, paper_size="receipt"),
        )
        self.assertIn("قلم", html)
        self.assertIn("دفتر", html)
        self.assertIn("۲۰۰", html)
        self.assertIn("۱۷۵", html)
        self.assertIn("۳۷۵", html)
        self.assertIn("width: 74mm", html)


if __name__ == "__main__":
    unittest.main()
