"""Security-oriented unit tests for printable invoices."""
import unittest

from client.ui.invoice_render import DEFAULT_TEMPLATE, render_invoice_html


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
        self.assertIn("font-size:14px", html)
        self.assertIn("font-size:28px", html)
        self.assertIn("line-height:2.0", html)

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
        self.assertIn("200.00", html)
        self.assertIn("175.00", html)
        self.assertIn("375.00", html)
        self.assertIn("width: 74mm", html)


if __name__ == "__main__":
    unittest.main()
