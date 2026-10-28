"""Security-oriented unit tests for printable invoices."""
import unittest

from client.ui.invoice_render import (
    DEFAULT_TEMPLATE, default_elements_for_paper, page_dimensions,
    prepare_invoice_pages, render_invoice_html,
)


class InvoiceRenderTests(unittest.TestCase):
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
