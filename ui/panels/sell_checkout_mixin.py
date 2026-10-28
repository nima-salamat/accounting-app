"""Receipt handling, checkout flow and product creation actions."""
import os
from PySide2.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QMessageBox, QScrollArea, QSizePolicy, QTableWidget, QCompleter,
    QTableWidgetItem, QTabWidget, QHeaderView, QCheckBox, QSizeGrip, QLayout, QSplitter, QLineEdit, QFrame
)
from PySide2.QtGui import QPixmap, Qt, QRegion, QFont
from PySide2.QtCore import QTimer, QEasingCurve, QPropertyAnimation, QSize, QPoint, QRect, Property, Signal
from PySide2.QtCore import QParallelAnimationGroup, QStringListModel
from collections import defaultdict
from datetime import datetime, date
from db.models import Product, Receipt, ReceiptProduct, Category
from accounting_app.services.sales import record_sale
from ui.base_panel import RecordDialog, RecordAdder, QDialog, to_jalali
from functools import partial
from PySide2.QtCore import QVariantAnimation
import random
import hashlib

from ui.thread import TrackingQThread
QThread = TrackingQThread
from ui.panels.sell_widgets import (
    SplitterAnimation, FlowLayout, SmallFlatButton, PanelCartItemCard,
    ProductCard, CartItemCard, CategoryCard, SearchLineEdit, get_color_from_name,
)
from ui.panels.sell_workers import CategoryProductFetcher, ReceiptFetcher, CheckoutWorker

from ui.panels.sell_widgets import (
    SplitterAnimation, FlowLayout, SmallFlatButton, PanelCartItemCard,
    ProductCard, CartItemCard, CategoryCard, SearchLineEdit, get_color_from_name,
)
from ui.panels.sell_workers import CategoryProductFetcher, ReceiptFetcher, CheckoutWorker



class SellCheckoutMixin:
    def show_receipts_page(self):
        self.refresh_receipts()
        self.pages.setCurrentWidget(self.page_receipts)

    def refresh_receipts(self):
        self.receipt_fetcher = ReceiptFetcher()
        self.receipt_fetcher.receipts_fetched.connect(self.on_receipts_fetched)
        self.receipt_fetcher.start()

    def on_receipts_fetched(self, receipts: list):
        self.receipts_table.setRowCount(0)
        for row, receipt in enumerate(receipts):
            self.receipts_table.insertRow(row)
            self.receipts_table.setItem(row, 0, QTableWidgetItem(str(receipt.id)))
            self.receipts_table.setItem(row, 1, QTableWidgetItem(str(receipt.day_receipt_id)))
            
            self.receipts_table.setItem(row, 2, QTableWidgetItem(f"{receipt.total_price:,}"))
            self.receipts_table.setItem(row, 3, QTableWidgetItem(str(to_jalali(receipt.created_at))))

            payed_status = "✓" if receipt.payed else "✗"
            self.receipts_table.setItem(row, 4, QTableWidgetItem(payed_status))
            btn_load = QPushButton("بارگذاری")
            btn_load.setProperty("class", "flat")
            btn_load.clicked.connect(partial(self.load_receipt, receipt))
            self.receipts_table.setCellWidget(row, 5, btn_load)

            btn_delete = QPushButton("حذف")
            btn_delete.setProperty("class", "flat")
            btn_delete.clicked.connect(partial(self.delete_receipt, receipt))
            self.receipts_table.setCellWidget(row, 6, btn_delete)

    def load_receipt(self, receipt):
        self.current_receipt = receipt
        self.edit_mode = True
        self.cart.clear()
        rps = ReceiptProduct.select().where(ReceiptProduct.receipt == receipt)
        for rp in rps:
            self.cart[rp.product.id] = (rp.product, rp.quantity)
        self.refresh_cart()
        self.refresh_cart_panel()
        self.edit_mode_label.setText("در حال ویرایش رسید")
        self.payed_checkbox.setChecked(receipt.payed)
        self.pages.setCurrentWidget(self.page_checkout)
        self.refresh_checkout()
        

    def add_to_cart(self, product: Product, qty: int):
        self.cart[product.id] = (product, self.cart.get(product.id, (None, 0))[1] + qty)
        self.refresh_cart()
        self.refresh_cart_panel()
        self.show_notification(f"{product.name} به سبد اضافه شد")
        

    def refresh_cart(self):
        while self.cart_layout.count():
            item = self.cart_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        total = 0
        cart_items = QWidget()
        cart_items_layout = QVBoxLayout(cart_items)
        cart_items_layout.setAlignment(Qt.AlignTop)
        cart_items_layout.setSpacing(10)
        for product, qty in self.cart.values():
            card = CartItemCard(product, qty, self.update_cart_qty, self.remove_from_cart, parent=self._parent)
            cart_items_layout.addWidget(card)
            total += product.sell_price * qty
        self.cart_layout.addWidget(cart_items)
        self.total_label.setText(f"جمعاً: {total:,} تومان")

    def update_cart_qty(self, product_id: int, new_qty: int):
        product, _ = self.cart[product_id]
        self.cart[product_id] = (product, new_qty)
        self.refresh_cart()
        self.refresh_cart_panel()
        if self.pages.currentWidget() == self.page_checkout:
            self.refresh_checkout()

    def remove_from_cart(self, product_id: int):
        if QMessageBox.question(self, "حذف", "آیا می‌خواهید این مورد را از سبد حذف کنید؟") == QMessageBox.Yes:
            if product_id in self.cart:
                name = self.cart[product_id][0].name
                del self.cart[product_id]
                self.refresh_cart()
                self.refresh_cart_panel()
                if self.pages.currentWidget() == self.page_checkout:
                    self.refresh_checkout()
                self.show_notification(f"{name} از سبد حذف شد")

    def show_checkout_page(self):
        self.refresh_checkout()
        self.pages.setCurrentWidget(self.page_checkout)

    def refresh_checkout(self):
        self.checkout_table.setRowCount(0)
        if not self.cart:
            self.total_label_checkout.setText("سبد خرید شما خالی است!")
            return
        total = 0
        for row, (product, qty) in enumerate(self.cart.values()):
            self.checkout_table.insertRow(row)
            self.checkout_table.setItem(row, 0, QTableWidgetItem(product.name))
            self.checkout_table.setItem(row, 1, QTableWidgetItem(str(qty)))
            self.checkout_table.setItem(row, 2, QTableWidgetItem(f"{product.sell_price:,}"))
            self.checkout_table.setItem(row, 3, QTableWidgetItem(f"{product.sell_price * qty:,}"))
            remove_btn = QPushButton("حذف")
            remove_btn.setProperty("class", "flat")
            remove_btn.clicked.connect(lambda pid=product.id: self.remove_from_cart(pid))
            self.checkout_table.setCellWidget(row, 4, remove_btn)
            total += product.sell_price * qty
        self.total_label_checkout.setText(f"جمعاً: {total:,} تومان")

    def checkout(self):
        if not self.cart:
            QMessageBox.warning(self, "اخطار", "سبد خرید شما خالی است!")
            return
        user = self._parent._parent._parent.AUTH_MANAGER.user
        payed = self.payed_checkbox.isChecked()
        receipt_to_delete = self.current_receipt if self.edit_mode else None
        self.checkout_worker = CheckoutWorker(self.cart, user, payed, edit_mode=self.edit_mode, receipt_to_delete=receipt_to_delete)
        self.checkout_worker.finished.connect(self.on_checkout_finished)
        self.checkout_worker.start()
    
    
    def checkout_payed(self):
        if not self.cart:
            QMessageBox.warning(self, "اخطار", "سبد خرید شما خالی است!")
            return
        user = self._parent._parent._parent.AUTH_MANAGER.user
        payed = True
        receipt_to_delete = self.current_receipt if self.edit_mode else None
        self.checkout_worker = CheckoutWorker(self.cart, user, payed, edit_mode=self.edit_mode, receipt_to_delete=receipt_to_delete)
        self.checkout_worker.finished.connect(self.on_checkout_finished)
        self.checkout_worker.start()

    def on_checkout_finished(self, success: bool, message: str):
        if success:
            QMessageBox.information(self, "موفقیت", message)
            self.cart.clear()
            self.refresh_cart()
            self.refresh_cart_panel()
            self.edit_mode = False
            self.edit_mode_label.setText("")
            self.current_receipt = None
            self.payed_checkbox.setChecked(False)
            self.pages.setCurrentWidget(self.page_products)
        else:
            QMessageBox.critical(self, "خطا", f"ثبت فروش با خطا مواجه شد:\n{message}")

    def delete_receipt(self, receipt):
        if QMessageBox.question(self, "حذف", "آیا می‌خواهید این را حذف کنید؟") == QMessageBox.Yes:
            
            receipt.delete_instance(recursive=True)
            self.show_notification("رسید با موفقیت حذف شد")
            self.refresh_receipts()

    def show_notification(self, message: str, duration: int = 2000):
        self.notification_label.setText(message)
        QTimer.singleShot(duration, lambda: self.notification_label.setText(""))

    def _on_add(self):
        model = Product
        _all_fields = model._meta.fields
        _create = ["name", "buy_price", "sell_price", "category"]
        _labels = {"name": "نام محصول", "buy_price": "قیمت خرید", "sell_price": "قیمت فروش", "category":"دسته بندی"}
        _image_fields = []
        dlg = RecordDialog(
            fields={n: _all_fields[n] for n in _create},
            model=model,
            image_fields=_image_fields,
            labels=_labels,
            parent=self
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.data.copy()
        data["custom_product"] = True
        self.adder = RecordAdder(model, data, _image_fields)
        self.thread = QThread(self)
        self.adder.moveToThread(self.thread)

        self.thread.started.connect(self.adder.add_record)
        self.adder.added.connect(self._on_record_added)
        self.adder.error.connect(self._on_record_error)

        self.adder.added.connect(self.thread.quit)
        self.adder.error.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def _on_record_added(self, product):
        self.add_to_cart(product, 1)
        self.show_notification(f"{product.name} به سبد اضافه شد")

    def _on_record_error(self, error):
        QMessageBox.critical(self, "خطا", f"خطا در افزودن محصول:\n{error}")
