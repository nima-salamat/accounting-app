"""Regression tests for the redesigned API-backed point-of-sale workspace."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication, QLabel

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

    def get_product(self, product_id):
        for product in self.products:
            if str(product["id"]) == str(product_id):
                return dict(product)
        error = RuntimeError("product not found")
        error.status_code = 404
        raise error

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

    def change_theme(self, mode):
        self.mode = mode


class SalesPageLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        settings = QSettings("AccountingApp", "DesktopClient")
        settings.setValue("sales/show_product_images", True)
        settings.setValue("sales/product_layout_mode", "grid")
        settings.setValue("sales/product_card_density", "comfortable")
        settings.setValue("sales/product_columns", 0)
        settings.sync()
        self.window = _WindowStub()
        self.page = SalesPage(self.window)
        self.page.show()
        self.app.processEvents()

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

    def test_cart_quantity_updates_the_line_subtotal(self):
        self.page.refresh_products()
        self.page.add_to_cart(self.page.products[0])
        self.app.processEvents()
        self.page._cart_plus_buttons["product-1"].click()
        self.page._cart_plus_buttons["product-1"].click()
        self.assertEqual(self.page._cart_quantity_labels["product-1"].text(), "3")
        self.assertEqual(self.page._cart_line_total_labels["product-1"].text(), "3.00")
        self.assertEqual(self.page.total_label.text(), "جمع تخمینی: 3.00")

    def test_search_suggestions_are_similar_results_and_load_more_is_paginated(self):
        self.page.search.setText("item")
        self.page._request_search_suggestions("item", 1)
        self.assertEqual(self.page.search_suggestion_list.count(), 8)
        self.assertTrue(self.page.search_more_button.isVisible())
        self.assertIn("101 نتیجه", self.page.search_suggestion_status.text())

        self.page._load_more_search_suggestions()
        self.assertEqual(self.page.search_suggestion_list.count(), 16)
        self.assertEqual(self.page._suggestion_page, 2)

        self.page.search_suggestion_list.item(0).setSelected(True)
        self.page._add_suggestion_to_cart(self.page.search_suggestion_list.item(0))
        self.assertEqual(self.page.collect_items()[0]["product_id"], "product-1")

    def test_existing_invoice_loads_into_edit_mode_and_exposes_payment_status(self):
        receipt = {
            "id": "receipt-123",
            "day_receipt_id": 17,
            "payed": False,
            "payment_method": "unpaid",
            "seat_number": None,
            "items": [{
                "product_id": "product-1",
                "product_name": "item-1",
                "sell_price": 1,
                "quantity": 2,
            }],
        }
        product = self.window.api.get_product("product-1")
        self.assertTrue(self.page._load_invoice_into_editor({
            "receipt": receipt,
            "products": {"product-1": product},
        }))

        self.assertEqual(self.page._editing_receipt_id, "receipt-123")
        self.assertEqual(self.page.collect_items(), [
            {"product_id": "product-1", "quantity": 2},
        ])
        self.assertEqual(self.page.submit_button.text(), "ذخیرهٔ تغییرات فاکتور")
        self.assertTrue(self.page.cancel_edit_button.isVisible())
        self.assertFalse(self.page.paid.isChecked())
        self.page.paid.setChecked(True)
        card_index = self.page.payment_method_combo.findData("card")
        self.page.payment_method_combo.setCurrentIndex(card_index)
        self.assertTrue(self.page.payment_method_combo.isEnabled())
        self.assertEqual(self.page.payment_method_combo.currentData(), "card")

    def test_product_cards_use_a_compact_width_and_shorter_image_area(self):
        self.page.refresh_products()
        card = self.page.product_grid.itemAt(0).widget()
        self.assertLessEqual(card.maximumWidth(), 218)
        self.assertLess(card.minimumWidth(), 140)
        image = card.findChild(QLabel, "SalesProductImage")
        self.assertLessEqual(image.maximumHeight(), 74)

    def test_sales_page_does_not_duplicate_global_theme_control(self):
        self.assertTrue(self.page.theme_button.isHidden())

    def test_image_visibility_is_user_configurable_from_display_settings(self):
        self.assertTrue(self.page._show_product_images)
        self.assertTrue(self.page.product_display_settings_button.isVisible())
        self.page._apply_product_display_settings("grid", False, "comfortable", 0)
        self.assertFalse(self.page._show_product_images)
        self.assertFalse(self.page._local_settings.value(
            "sales/show_product_images", True, type=bool
        ))

    def test_legacy_reflow_keeps_table_mode_selected(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings("table", True, "compact", 0)
        self.page._reflow_product_grid()
        self.assertIs(self.page.catalog_results_stack.currentWidget(), self.page.product_table)
        self.assertEqual(self.page._rendered_columns, 0)

    def test_grid_column_setting_never_overflows_the_available_catalog_width(self):
        self.page.refresh_products()
        width = max(260, self.page.catalog_scroll.viewport().width())
        self.page._apply_product_display_settings("grid", True, "compact", 6)
        available = max(1, min(6, width // 132))
        self.assertLessEqual(self.page._rendered_columns, available)

    def test_catalog_supports_horizontal_list_and_table_layouts(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings("horizontal", True, "compact", 0)
        self.assertEqual(self.page._product_layout_mode, "horizontal")
        self.assertIs(self.page.catalog_results_stack.currentWidget(), self.page.catalog_scroll)
        self.assertEqual(self.page.product_grid.count(), len(self.page.products))

        self.page._apply_product_display_settings("table", True, "compact", 0)
        self.assertIs(self.page.catalog_results_stack.currentWidget(), self.page.product_table)
        self.assertEqual(self.page.product_table.rowCount(), len(self.page.products))
        self.assertIn("product-1", self.page._product_add_buttons)
        self.page.product_table.cellWidget(0, 5).click()
        self.assertEqual(self.page.collect_items()[0]["product_id"], "product-1")

    def test_committed_search_shows_results_in_catalog_and_closes_suggestions(self):
        self.page.search.setText("item-10")
        self.page._request_search_suggestions("item-10", 1)
        self.assertTrue(self.page.search_suggestions_frame.isVisible())
        self.page.search_button.click()
        self.assertFalse(self.page.search_suggestions_frame.isVisible())
        self.assertEqual(self.page.total_products, 3)
        self.assertEqual(
            [product["name"] for product in self.page.products],
            ["item-10", "item-100", "item-101"],
        )
        # A delayed asynchronous suggestion response must not reopen the overlay
        # after the user has committed the search and loaded the catalog results.
        self.page._show_search_suggestions(
            self.window.api.list_products_page(q="item-10", page=1, page_size=8),
            "item-10",
            1,
        )
        self.assertFalse(self.page.search_suggestions_frame.isVisible())

    def test_search_suggestions_overlay_the_catalog_instead_of_reflowing_it(self):
        self.page.search.setText("item")
        self.page._request_search_suggestions("item", 1)
        self.app.processEvents()
        self.assertIs(self.page.search_suggestions_frame.parentWidget(), self.page.catalog_panel)
        self.assertEqual(self.page.catalog_panel.layout().indexOf(self.page.search_suggestions_frame), -1)
        self.assertTrue(self.page.search_suggestions_frame.isVisible())
        self.assertGreater(self.page.search_suggestions_frame.height(), 0)

    def test_new_sale_label_is_not_duplicated_in_the_pos_toolbar(self):
        self.assertFalse(hasattr(self.page, "invoice_mode_label"))


if __name__ == "__main__":
    unittest.main()
