"""Regression tests for paginated POS catalog and persistent cart state."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from PySide6.QtWidgets import QApplication

from client.ui.sales_page import SalesPage


class _PagedApi:
    def __init__(self):
        self.products = [
            {"id": "product-{}".format(index), "name": "item-{}".format(index), "sell_price": index}
            for index in range(1, 102)
        ]

    def list_products_page(self, q=None, page=1, page_size=50):
        matches = [
            product for product in self.products
            if not q or q.casefold() in product["name"].casefold()
        ]
        start = (page - 1) * page_size
        return {
            "items": matches[start:start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(matches),
        }


class _WindowStub:
    def __init__(self):
        self.api = _PagedApi()
        self.errors = []
        self.status = ""

    def run_api(self, operation, callback, failure=None, busy=None):
        try:
            result = operation()
        except Exception as exc:
            if failure:
                failure(exc)
            else:
                self.errors.append(str(exc))
        else:
            callback(result)

    def show_error(self, error):
        self.errors.append(str(error))

    def set_status(self, message):
        self.status = message


class SalesPagePaginationTests(unittest.TestCase):
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

    def test_catalog_pages_include_products_past_the_old_200_item_limit(self):
        self.page.refresh_products()
        self.assertEqual(self.page.table.rowCount(), 50)
        self.assertTrue(self.page.next_page_button.isEnabled())

        self.page.next_page_button.click()
        self.assertEqual(self.page.product_page, 2)
        self.assertEqual(self.page.table.rowCount(), 50)
        self.assertIn("صفحه 2 از 3", self.page.product_page_label.text())

        self.page.next_page_button.click()
        self.assertEqual(self.page.product_page, 3)
        self.assertEqual(self.page.table.rowCount(), 1)
        self.assertEqual(self.page.table.item(0, 1).text(), "item-101")
        self.assertFalse(self.page.next_page_button.isEnabled())

    def test_cart_items_survive_paging_and_are_included_in_checkout_payload(self):
        self.page.refresh_products()
        self.page.table.cellWidget(0, 3).setValue(2)
        self.page.next_page_button.click()
        self.page.table.cellWidget(0, 3).setValue(3)

        self.assertEqual(
            self.page.collect_items(),
            [
                {"product_id": "product-1", "quantity": 2},
                {"product_id": "product-51", "quantity": 3},
            ],
        )
        self.assertEqual(self.page.total_label.text(), "جمع تخمینی: 155.00")

    def test_changing_search_resets_the_catalog_to_first_page(self):
        self.page.refresh_products()
        self.page.next_page_button.click()
        self.page.search.setText("item-10")
        self.page.refresh_products()

        self.assertEqual(self.page.product_page, 1)
        self.assertEqual(self.page.table.rowCount(), 3)
        self.assertEqual(self.page.table.item(0, 1).text(), "item-10")
        self.assertEqual(self.page.table.item(2, 1).text(), "item-101")


if __name__ == "__main__":
    unittest.main()
