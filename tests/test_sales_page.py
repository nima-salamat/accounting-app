"""Regression tests for the redesigned API-backed point-of-sale workspace."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from client.ui.sales_page import SalesPage


class _PagedApi:
    def __init__(self):
        self.products = [
            {
                "id": "product-{}".format(index),
                "name": "item-{}".format(index),
                "sell_price": index,
                "category_id": "cat-a" if index % 2 else "cat-b",
                "track_stock": True,
                "stock_quantity": 20,
                "image_path": None,
            }
            for index in range(1, 102)
        ]
        self.list_calls = []

    def list_products_page(self, q=None, category_id=None, page=1, page_size=24):
        self.list_calls.append((q, category_id, page, page_size))
        matches = [
            product for product in self.products
            if (not q or q.casefold() in product["name"].casefold())
            and (not category_id or product["category_id"] == category_id)
        ]
        start = (page - 1) * page_size
        return {
            "items": matches[start:start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(matches),
        }

    def list_categories_page(self, page=1, page_size=200):
        return {
            "items": [
                {"id": "cat-a", "name": "Category A"},
                {"id": "cat-b", "name": "Category B"},
            ],
            "page": page,
            "page_size": page_size,
            "total": 2,
        }

    def get_product_image_bytes(self, product_id):
        return None


class _WindowStub:
    def __init__(self):
        self.api = _PagedApi()
        self.errors = []
        self.status = ""
        self.mode = "light"
        self.company_profile = {}

    def run_api(self, operation, callback, failure=None, busy=None):
        if busy is not None:
            busy.setEnabled(False)
        try:
            result = operation()
        except Exception as exc:
            if failure:
                failure(exc)
            else:
                self.errors.append(str(exc))
        else:
            callback(result)
        finally:
            if busy is not None:
                busy.setEnabled(True)

    def show_error(self, error):
        self.errors.append(str(error))

    def set_status(self, message):
        self.status = message


class SalesPageLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = _WindowStub()
        self.page = SalesPage(self.window)

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()

    def test_workspace_places_catalog_and_cart_in_a_resizable_rtl_splitter(self):
        self.assertIs(self.page.splitter.widget(0), self.page.catalog_panel)
        self.assertIs(self.page.splitter.widget(1), self.page.cart_panel)
        self.assertEqual(self.page.splitter.layoutDirection(), Qt.LayoutDirection.RightToLeft)
        self.assertTrue(self.page.catalog_panel.minimumWidth() > 0)
        self.assertTrue(self.page.cart_panel.minimumWidth() > 0)

    def test_catalog_pages_include_products_past_the_old_limit(self):
        self.page.refresh_products()
        self.assertEqual(len(self.page.products), 24)
        self.assertEqual(self.page.total_products, 101)
        self.assertEqual(self.page.product_page, 1)
        self.assertTrue(self.page.next_page_button.isEnabled())

        self.page.next_page_button.click()
        self.assertEqual(self.page.product_page, 2)
        self.assertEqual(len(self.page.products), 24)
        self.assertIn("صفحه 2 از 5", self.page.product_page_label.text())

        for _ in range(3):
            self.page.next_page_button.click()
        self.assertEqual(self.page.product_page, 5)
        self.assertEqual(len(self.page.products), 5)
        self.assertEqual(self.page.products[-1]["name"], "item-101")
        self.assertFalse(self.page.next_page_button.isEnabled())

    def test_cart_survives_pagination_and_checkout_payload_uses_selected_items(self):
        self.page.refresh_products()
        self.page.add_to_cart(self.page.products[0])
        self.page.add_to_cart(self.page.products[0])
        self.page.next_page_button.click()
        self.page.add_to_cart(self.page.products[0])
        self.page.add_to_cart(self.page.products[0])
        self.page.add_to_cart(self.page.products[0])

        self.assertEqual(
            self.page.collect_items(),
            [
                {"product_id": "product-1", "quantity": 2},
                {"product_id": "product-25", "quantity": 3},
            ],
        )
        self.assertEqual(self.page.total_label.text(), "جمع تخمینی: 77.00")
        self.assertEqual(self.page.cart_status_label.text(), "2 نوع · 5 عدد")

    def test_search_resets_to_first_page_and_filters_the_server_catalog(self):
        self.page.refresh_products()
        self.page.next_page_button.click()
        self.page.search.setText("item-10")
        self.page.refresh_products()

        self.assertEqual(self.page.product_page, 1)
        self.assertEqual(self.page.total_products, 3)
        self.assertEqual(
            [product["name"] for product in self.page.products],
            ["item-10", "item-100", "item-101"],
        )

    def test_category_filter_is_sent_to_api(self):
        self.page.refresh_products()
        category_index = self.page.category_combo.findData("cat-a")
        self.assertGreaterEqual(category_index, 0)
        self.page.category_combo.setCurrentIndex(category_index)

        self.assertTrue(self.window.api.list_calls)
        self.assertEqual(self.window.api.list_calls[-1][1], "cat-a")
        self.assertTrue(all(product["category_id"] == "cat-a" for product in self.page.products))

    def test_cart_can_be_collapsed_and_restored_without_losing_quantities(self):
        self.page.refresh_products()
        self.page.add_to_cart(self.page.products[0])

        self.page._set_cart_panel_visible(False)
        self.assertFalse(self.page.cart_panel.isVisible())
        self.assertTrue(self.page.show_cart_button.isVisible())
        self.assertEqual(self.page.collect_items()[0]["quantity"], 1)

        self.page._set_cart_panel_visible(True)
        self.assertTrue(self.page.cart_panel.isVisible())
        self.assertFalse(self.page.show_cart_button.isVisible())
        self.assertEqual(self.page.collect_items()[0]["quantity"], 1)

    def test_image_visibility_is_user_configurable(self):
        self.assertTrue(self.page.show_images_checkbox.isChecked())
        self.page.show_images_checkbox.setChecked(False)
        self.assertFalse(self.page._show_product_images)
        self.assertFalse(self.page._local_settings.value(
            "sales/show_product_images", True, type=bool
        ))


if __name__ == "__main__":
    unittest.main()
