"""Regression tests for the redesigned API-backed point-of-sale workspace."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
import tempfile
from unittest.mock import patch
from PySide6.QtCore import Qt, QSettings, QEvent, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSizePolicy, QWidget

from client.ui.invoice_dialog import InvoicePreviewWidget
from client.ui.invoice_render import DEFAULT_TEMPLATE
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
        self.recent_calls = []

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

    def list_recent_receipts_page(self, q=None, page=1, page_size=50):
        self.recent_calls.append((q, page, page_size))
        return {"items": [], "page": page, "page_size": page_size, "total": 0}

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
        self.standalone_pos = False
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
        settings.setValue("sales/show_product_stock", True)
        settings.setValue("sales/show_product_add_button", True)
        settings.setValue("sales/product_stock_display_style", "text")
        settings.setValue("sales/zoom_product_images", True)
        settings.setValue("sales/use_category_tabs", False)
        settings.setValue("sales/cart_collapsed", False)
        settings.setValue("sales/history_preview_collapsed", True)
        settings.remove("sales/history_splitter_sizes")
        settings.remove("sales/product_table_column_widths")
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
        self.assertTrue(self.page.cart_panel.isVisible())
        self.assertTrue(self.page._cart_collapsed)
        self.assertTrue(self.page.cart_scroll.isHidden())
        self.assertEqual(self.page.cart_panel_toggle.text(), "›")
        self.assertEqual(self.page.collect_items()[0]["quantity"], 1)

        self.page._set_cart_panel_visible(True)
        self.assertFalse(self.page._cart_collapsed)
        self.assertFalse(self.page.cart_scroll.isHidden())
        self.assertEqual(self.page.cart_panel_toggle.text(), "‹")
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
        self.assertLessEqual(card.maximumWidth(), 320)
        self.assertLess(card.minimumWidth(), 140)
        image = card.findChild(QLabel, "SalesProductImage")
        self.assertEqual(image.width(), image.height())

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
        self.page._apply_product_display_settings("grid", True, "compact", 6)
        self.app.processEvents()
        self.assertEqual(self.page._rendered_columns, 6)
        widths = [
            self.page.product_grid.itemAt(index).widget().width()
            for index in range(min(6, self.page.product_grid.count()))
        ]
        self.assertEqual(len(widths), 6)
        self.assertLessEqual(max(widths) - min(widths), 4)

    def test_cart_toggle_is_in_the_catalog_header_not_inside_the_cart(self):
        self.assertGreaterEqual(self.page.catalog_title_row.indexOf(self.page.cart_panel_toggle), 0)
        self.assertEqual(self.page.cart_header_layout.indexOf(self.page.cart_panel_toggle), -1)

    def test_cancel_loaded_invoice_button_is_in_the_footer_next_to_total(self):
        self.assertGreaterEqual(self.page.footer_layout.indexOf(self.page.total_label), 0)
        self.assertGreaterEqual(self.page.footer_layout.indexOf(self.page.cancel_edit_button), 0)
        self.assertEqual(
            self.page.footer_layout.indexOf(self.page.cancel_edit_button),
            self.page.footer_layout.indexOf(self.page.total_label) - 1,
        )
        self.assertEqual(self.page.cancel_edit_button.text(), "لغو بارگذاری")

    def test_stock_circle_style_and_list_preview_are_rendered(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings(
            "grid", True, "comfortable", 0, stock_display_style="circle"
        )
        card = self.page.product_grid.itemAt(0).widget()
        circle = card.findChild(QLabel, "SalesProductStockCircle")
        self.assertIsNotNone(circle)
        self.assertEqual((circle.width(), circle.height()), (32, 32))
        self.assertFalse(card.findChildren(QLabel, "SalesProductStock"))

        preview = self.page._build_product_card(
            self.page.products[0], preview=True, layout_mode="list",
            show_images=True, show_stock=True, show_add_button=True,
            stock_display_style="text",
        )
        self.assertEqual(
            preview.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding
        )
        self.assertTrue(preview.findChildren(QPushButton, "SalesProductAddButton"))

    def test_recent_invoice_title_and_reload_button_are_inside_the_list_panel(self):
        list_panel = self.page.history_splitter.widget(0)
        self.assertIs(self.page.history_title.parentWidget(), list_panel)
        self.assertIs(self.page.history_refresh_button.parentWidget(), list_panel)
        self.assertEqual(self.page.history_tabs.parentWidget(), list_panel)

    def test_catalog_supports_horizontal_list_and_table_layouts(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings("horizontal", True, "compact", 0)
        self.assertEqual(self.page._product_layout_mode, "horizontal")
        self.assertIs(self.page.catalog_results_stack.currentWidget(), self.page.catalog_scroll)
        self.assertEqual(self.page.product_grid.count(), len(self.page.products))
        card = self.page.product_grid.itemAt(0).widget()
        price = card.findChild(QLabel, "SalesProductPrice")
        stock = card.findChild(QLabel, "SalesProductStock")
        add = next(button for button in card.findChildren(QPushButton)
                   if button.objectName() == "SalesProductAddButton")
        self.assertIs(price.parentWidget(), stock.parentWidget())
        self.assertIs(price.parentWidget().parentWidget(), add.parentWidget())

        self.page._apply_product_display_settings(
            "horizontal", True, "compact", 0, show_stock=True, show_add_button=False
        )
        no_add_card = self.page.product_grid.itemAt(0).widget()
        self.assertFalse(no_add_card.findChildren(QPushButton, "SalesProductAddButton"))
        self.assertTrue(
            no_add_card.findChild(QWidget, "SalesProductDetails").property("stackStockBelowPrice")
        )

        self.page._apply_product_display_settings("table", True, "compact", 0)
        self.assertIs(self.page.catalog_results_stack.currentWidget(), self.page.product_table)
        self.assertEqual(self.page.product_table.rowCount(), len(self.page.products))
        self.assertEqual(self.page.product_table.columnCount(), 5)
        self.assertEqual(self.page._product_add_buttons, {})
        self.assertFalse(self.page.product_table.findChildren(QPushButton, "SalesProductAddButton"))
        self.page.product_table.doubleClicked.emit(self.page.product_table.model().index(0, 1))
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

    def test_inline_invoice_preview_has_mouse_zoom_and_page_fit_controls(self):
        preview = InvoicePreviewWidget()
        preview.resize(700, 520)
        preview.show()
        self.app.processEvents()
        receipt = {
            "id": "receipt-preview",
            "day_receipt_id": 101,
            "total_price": 150,
            "payed": True,
            "items": [{
                "product_id": "product-1",
                "product_name": "item-1",
                "sell_price": 150,
                "quantity": 1,
            }],
        }
        preview.set_invoice(receipt, DEFAULT_TEMPLATE)
        self.app.processEvents()
        self.assertTrue(preview.preview.dragMode() == preview.preview.DragMode.ScrollHandDrag)
        self.assertIsNotNone(preview._page_item)
        self.assertIn("A4", preview.page_info.text())
        bounds = preview._page_item.boundingRect()
        viewport = preview.preview.viewport().size()
        expected_fit = min(
            max(1, viewport.width() - 8) / bounds.width(),
            max(1, viewport.height() - 8) / bounds.height(),
        )
        self.assertAlmostEqual(preview.preview.transform().m11(), expected_fit, places=3)
        scale_before = preview.preview.transform().m11()
        preview._zoom(1.2)
        self.assertGreater(preview.preview.transform().m11(), scale_before)
        preview.fit_width()
        preview.close()

    def test_recent_invoices_are_a_mode_with_inline_preview(self):
        self.page.refresh_products()
        self.assertIs(self.page.workspace_stack.currentWidget(), self.page.sales_workspace)
        self.page.set_workspace_mode("history")
        self.assertIs(self.page.workspace_stack.currentWidget(), self.page.history_workspace)
        self.assertIsNotNone(self.page.history_invoice_preview)
        self.assertIs(
            self.page.history_invoice_preview.parentWidget(),
            self.page.history_splitter.widget(1),
        )
        self.assertEqual(self.page._history_current_page, 1)
        self.page.set_workspace_mode("sales")
        self.assertIs(self.page.workspace_stack.currentWidget(), self.page.sales_workspace)

    def test_new_sale_label_is_not_duplicated_in_the_pos_toolbar(self):
        self.assertFalse(hasattr(self.page, "invoice_mode_label"))


    def test_stock_and_add_button_visibility_settings_apply_to_cards(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings(
            "grid", True, "comfortable", 0,
            show_stock=False, show_add_button=False,
        )
        card = self.page.product_grid.itemAt(0).widget()
        self.assertFalse(card.findChildren(QLabel, "SalesProductStock"))
        self.assertFalse(card.findChildren(QPushButton, "SalesProductAddButton"))

        title = card.findChild(QLabel, "SalesProductTitle")
        event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(2.0, 2.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.assertTrue(self.page.eventFilter(title, event))
        self.assertEqual(self.page.collect_items()[0]["product_id"], "product-1")

    def test_table_selection_can_be_cleared_and_action_is_disabled_without_selection(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings("table", True, "comfortable", 0)
        self.assertTrue(self.page.product_deselect_button.isVisible())
        self.assertFalse(self.page.product_deselect_button.isEnabled())

        self.page.product_table.setCurrentCell(0, 1)
        self.page.product_table.selectRow(0)
        self.assertTrue(self.page.product_deselect_button.isEnabled())
        self.page.product_deselect_button.click()
        self.assertEqual(self.page.product_table.selectionModel().selectedRows(), [])
        self.assertFalse(self.page.product_deselect_button.isEnabled())

    def test_table_column_widths_are_saved_and_restored(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings("table", True, "comfortable", 0)
        self.page.product_table.setColumnWidth(1, 333)
        self.page._save_product_table_column_widths()
        self.assertIn("333", self.page._local_settings.value(
            "sales/product_table_column_widths"
        ))

        another_page = SalesPage(self.window)
        try:
            self.assertEqual(another_page.product_table.columnWidth(1), 333)
        finally:
            another_page.close()
            another_page.deleteLater()
            self.app.processEvents()

    def test_standalone_pos_exposes_theme_icon_but_desktop_client_does_not(self):
        self.assertTrue(self.page.theme_button.isHidden())
        standalone = _WindowStub()
        standalone.standalone_pos = True
        standalone_page = SalesPage(standalone)
        try:
            self.assertFalse(standalone_page.theme_button.isHidden())
            self.assertTrue(standalone_page.theme_button.toolTip())
        finally:
            standalone_page.close()
            standalone_page.deleteLater()
            self.app.processEvents()



    def test_category_tabs_setting_filters_by_tab_but_searches_all_categories(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings(
            "grid", True, "comfortable", 0, use_category_tabs=True
        )
        self.app.processEvents()
        self.assertTrue(self.page.category_tabs.isVisible())
        self.assertTrue(self.page.category_combo.isHidden())
        self.assertEqual(self.page.category_tabs.tabText(0), "همهٔ دسته‌ها")
        self.assertEqual(self.page.category_tabs.count(), 3)

        self.page.category_tabs.setCurrentIndex(1)
        self.assertTrue(all(item["category_id"] == "cat-a" for item in self.page.products))
        self.assertEqual(self.window.api.list_calls[-1][1], "cat-a")

        self.page.search.setText("item-10")
        self.page.search_button.click()
        self.assertEqual(self.window.api.list_calls[-1][0], "item-10")
        self.assertIsNone(self.window.api.list_calls[-1][1])
        self.assertEqual(self.page.category_tabs.currentIndex(), 0)
        self.assertEqual(len(self.page.products), 3)
        self.assertEqual({item["category_id"] for item in self.page.products}, {"cat-a", "cat-b"})
        self.assertTrue(self.page._local_settings.value("sales/use_category_tabs", False, type=bool))

    def test_cart_collapse_is_functional_and_persisted_for_next_open(self):
        self.assertFalse(self.page._cart_collapsed)
        self.page._set_cart_panel_visible(False)
        self.app.processEvents()
        self.assertTrue(self.page._cart_collapsed)
        self.assertTrue(self.page._local_settings.value("sales/cart_collapsed", False, type=bool))
        collapsed_sizes = self.page.splitter.sizes()
        self.assertLessEqual(collapsed_sizes[1], 180)

        reopened = SalesPage(self.window)
        reopened.show()
        self.app.processEvents()
        try:
            self.assertTrue(reopened._cart_collapsed)
            self.assertTrue(reopened.cart_scroll.isHidden())
            reopened.cart_panel_toggle.click()
            self.app.processEvents()
            self.assertFalse(reopened._cart_collapsed)
            self.assertFalse(reopened.cart_scroll.isHidden())
            self.assertFalse(reopened._local_settings.value("sales/cart_collapsed", True, type=bool))
        finally:
            reopened.close()
            reopened.deleteLater()
            self.app.processEvents()

    def test_invoice_preview_is_closed_by_default_and_can_reopen(self):
        self.page.set_workspace_mode("history")
        self.app.processEvents()
        preview_panel = self.page.history_splitter.widget(1)
        self.assertTrue(preview_panel.isHidden())
        self.assertTrue(self.page.history_preview_reopen_button.isVisible())
        self.assertTrue(self.page._local_settings.value(
            "sales/history_preview_collapsed", False, type=bool
        ))

        self.page._set_history_preview_visible(True)
        self.app.processEvents()
        self.assertFalse(preview_panel.isHidden())
        self.assertEqual(self.page.history_preview_reopen_button.toolTip(), "بستن پیش‌نمایش فاکتور")
        self.page._set_history_preview_visible(False)
        self.app.processEvents()
        self.assertTrue(preview_panel.isHidden())
        self.assertEqual(self.page.history_preview_reopen_button.toolTip(), "بازکردن پیش‌نمایش فاکتور")
        self.assertTrue(self.page._local_settings.value(
            "sales/history_preview_collapsed", False, type=bool
        ))

    def test_invoice_deselect_clears_selection_and_preview(self):
        self.page.set_workspace_mode("history")
        record = {
            "id": "full-invoice-uuid-1234",
            "day_receipt_id": 33,
            "payed": True,
            "created_at": "2026-10-30T12:00:00",
            "seat_number": None,
            "total_price": 50,
            "payment_method": "cash",
        }
        self.page._populate_recent_receipts({"items": [record], "total": 1, "page": 1})
        table = self.page._history_tables["all"]
        table.setCurrentCell(0, 1)
        table.selectRow(0)
        self.app.processEvents()
        self.assertTrue(self.page.history_deselect_button.isEnabled())
        self.page.history_deselect_button.click()
        self.assertEqual(table.currentRow(), -1)
        self.assertFalse(self.page.history_deselect_button.isEnabled())
        self.assertIsNone(self.page.history_invoice_preview._page_item)
        self.assertIsNone(self.page._history_invoice_payload)

    def test_invoice_number_chip_copies_id_and_shows_full_id_on_hover(self):
        receipt_id = "3da9f062-6f0b-4f0f-9417-abcd7890abcd"
        receipt = {
            "id": receipt_id, "day_receipt_id": 44, "total_price": 50, "payed": True,
            "items": [{"product_id": "product-1", "product_name": "item-1", "sell_price": 50, "quantity": 1}],
        }
        self.page._set_history_invoice_preview({"receipt": receipt, "template": DEFAULT_TEMPLATE})
        self.assertFalse(self.page.history_splitter.widget(1).isHidden())
        self.assertTrue(self.page.history_preview_close_button.isVisible())
        self.assertEqual(self.page.history_preview_status.text(), "شماره: 44")
        self.assertIn(receipt_id, self.page.history_preview_status.toolTip())
        self.page.history_preview_status.click()
        self.assertEqual(QApplication.clipboard().text(), receipt_id)

    def test_inline_preview_exports_png_and_jpg(self):
        receipt = {
            "id": "receipt-export", "day_receipt_id": 9, "total_price": 25, "payed": True,
            "items": [{"product_id": "product-1", "product_name": "item-1", "sell_price": 25, "quantity": 1}],
        }
        preview = InvoicePreviewWidget()
        preview.resize(700, 520)
        preview.set_invoice(receipt, DEFAULT_TEMPLATE)
        try:
            for extension, image_filter in (
                ("png", "PNG image (*.png)"),
                ("jpg", "JPEG image (*.jpg *.jpeg)"),
            ):
                with self.subTest(extension=extension), tempfile.TemporaryDirectory() as tmp:
                    path = os.path.join(tmp, "invoice." + extension)
                    with patch("client.ui.invoice_dialog.QFileDialog.getSaveFileName", return_value=(path, image_filter)):
                        with patch("client.ui.invoice_dialog.QMessageBox.information"):
                            self.assertTrue(preview.export_invoice(extension))
                    self.assertTrue(os.path.exists(path))
                    self.assertGreater(os.path.getsize(path), 100)
        finally:
            preview.close()



    def test_recent_invoice_search_passes_query_to_server_and_resets_page(self):
        self.page.set_workspace_mode("history")
        self.page.history_search_input.setText("invoice-17")
        self.page.history_search_button.click()
        q, page, page_size = self.window.api.recent_calls[-1]
        self.assertEqual(q, "invoice-17")
        self.assertEqual(page, 1)
        self.assertEqual(page_size, self.page._history_page_size)
        self.assertEqual(self.page._history_search_query, "invoice-17")

    def test_list_layout_has_a_visible_add_button_and_zoom_can_be_disabled(self):
        self.page.refresh_products()
        self.page._apply_product_display_settings("list", True, "comfortable", 0)
        self.app.processEvents()
        card = self.page.product_grid.itemAt(0).widget()
        add_button = card.findChild(QPushButton, "SalesProductAddButton")
        self.assertIsNotNone(add_button)
        self.assertTrue(add_button.isVisible())
        self.assertGreater(add_button.width(), 0)

        self.page._apply_product_display_settings(
            "grid", True, "comfortable", 0, zoom_images=False
        )
        self.assertFalse(self.page._zoom_product_images)
        self.assertFalse(self.page._local_settings.value(
            "sales/zoom_product_images", True, type=bool
        ))

if __name__ == "__main__":
    unittest.main()
