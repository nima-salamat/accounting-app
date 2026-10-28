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


class SellPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.cart = {}
        self.current_receipt = None
        self.edit_mode: bool = False


        
        self._build_ui()
        self.refresh_products()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        

        self.notification_label = QLabel('', alignment=Qt.AlignCenter)
        self.notification_label.setFixedHeight(25)
        self.notification_label.setStyleSheet("QLabel { background: transparent; font-weight: bold; color: #228B22; }")
        main_layout.addWidget(self.notification_label)

        self.nav_widget = QWidget()
        self.nav_widget.setObjectName("nav_widget")
        self.nav_layout = QHBoxLayout(self.nav_widget)
        self.nav_layout.setSpacing(5)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_products = QPushButton("محصولات")
        self.btn_cart = QPushButton("سبد خرید")
        self.btn_checkout = QPushButton("پرداخت")
        self.btn_receipts = QPushButton("رسیدها")
        self.btn_refresh = QPushButton("🔄 بروزرسانی")


        for btn in [self.btn_products, self.btn_cart, self.btn_checkout, self.btn_receipts, self.btn_refresh]:
            self.nav_layout.addWidget(btn)

        main_layout.addWidget(self.nav_widget)
        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages, 1)

        self._init_pages()
        self._setup_connections()

        self.btn_products.click()

    def set_active_nav_button(self, active_button: QPushButton):
        for btn in [self.btn_products, self.btn_cart, self.btn_checkout, self.btn_receipts, self.btn_refresh]:
            btn.setProperty("class", "")
            btn.setStyleSheet("") 
        active_button.setProperty("class", "active")
        active_button.setStyleSheet("background-color: #3F51B5; color: white; border-radius: 6px; padding: 4px 8px;")

    def _setup_connections(self):
        self.btn_products.clicked.connect(lambda: (self.pages.setCurrentWidget(self.page_products), self.set_active_nav_button(self.btn_products)))
        self.btn_cart.clicked.connect(lambda: (self.pages.setCurrentWidget(self.page_cart), self.set_active_nav_button(self.btn_cart)))
        self.btn_checkout.clicked.connect(lambda: (self.show_checkout_page(), self.set_active_nav_button(self.btn_checkout)))
        self.btn_receipts.clicked.connect(lambda: (self.show_receipts_page(), self.set_active_nav_button(self.btn_receipts)))

        # self.btn_refresh.clicked.connect(self.refresh_products)
        self.btn_refresh.clicked.connect(self.refresh_all)

        self.btn_open_cart.clicked.connect(self.open_cart_panel)
        self.btn_close_cart.clicked.connect(self.close_cart_panel)
    def refresh_all(self):
        self.refresh_products()
        self.refresh_cart_panel()
        self.refresh_cart()
        self.refresh_receipts()
        self.refresh_checkout()
        
    def _init_pages(self):
        self.page_products = QSplitter(Qt.Horizontal)
        self.left_widget = QWidget()
        left_layout = QVBoxLayout(self.left_widget)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(10, 10, 10, 10)

        top_layout = QHBoxLayout()
        self.cb_disable_anim = QCheckBox("غیرفعال‌سازی انیمیشن‌ها")
        self.cb_disable_anim.setChecked(self._parent._parent._parent.DISABLE_ANIMATIONS)
        self.cb_disable_anim.stateChanged.connect(self.toggle_animations)
        self.cb_show_images = QCheckBox("نمایش عکس محصولات")
        self.cb_show_images.setChecked(self._parent._parent._parent.SHOW_PRODUCT_IMAGES)
        self.cb_show_images.stateChanged.connect(self.toggle_show_images)
        self.btn_add_custom = QPushButton("افزودن محصول سفارشی")
        self.btn_add_custom.setProperty("class", "flat")
        
        self.btn_add_custom.clicked.connect(self._on_add)
        self.btn_open_cart = QPushButton("🛒 پنل سبد خرید")
        self.btn_open_cart.setProperty("class", "flat")

        top_layout.addWidget(self.cb_disable_anim)
        top_layout.addWidget(self.cb_show_images)
        top_layout.addWidget(self.btn_add_custom)
        top_layout.addWidget(self.btn_open_cart)
        left_layout.addLayout(top_layout)

        self.tab_widget = QTabWidget()
        left_layout.addWidget(self.tab_widget)

        self.page_products.addWidget(self.left_widget)

        self.cart_panel = QWidget()
        self.cart_panel_layout = QVBoxLayout(self.cart_panel)
        self.cart_panel_layout.setContentsMargins(10, 10, 10, 10)
        self.cart_panel_layout.setSpacing(10)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("سبد خرید"))
        self.btn_close_cart = QPushButton("✖️ بستن")
        self.btn_close_cart.setProperty("class", "flat")
        
        header_layout.addWidget(self.btn_close_cart)
        self.cart_panel_layout.addLayout(header_layout)

        cart_scroll = QScrollArea()
        cart_scroll.setWidgetResizable(True)
        cart_container = QWidget()
        self.cart_panel_items_layout = QVBoxLayout(cart_container)
        self.cart_panel_items_layout.setAlignment(Qt.AlignTop)
        cart_scroll.setWidget(cart_container)
        self.cart_panel_layout.addWidget(cart_scroll)

        self.layout_panel_checkout = QHBoxLayout()
        self.cart_panel_layout.addLayout(self.layout_panel_checkout)
        self.btn_confirm = QPushButton("✓ تکمیل خرید")
        self.btn_confirm.setProperty("class", "flat")
        self.layout_panel_checkout.addWidget(self.btn_confirm, alignment=Qt.AlignCenter)
        self.btn_confirm.clicked.connect(self.checkout_payed)

        self.cart_panel_total_label = QLabel("قیمت کل: 0 تومان")
        self.cart_panel_total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.layout_panel_checkout.addWidget(self.cart_panel_total_label)

        size_grip = QSizeGrip(self.cart_panel)
        self.cart_panel_layout.addWidget(size_grip, alignment=Qt.AlignBottom | Qt.AlignRight)

        self.page_products.addWidget(self.cart_panel)
        self.page_products.setStretchFactor(0, 3)
        self.page_products.setStretchFactor(1, 1)
        self.page_products.setSizes([800, 0])

        self.page_cart = QWidget()
        cart_layout = QVBoxLayout(self.page_cart)
        self.edit_mode_label = QLabel("", alignment=Qt.AlignCenter)
        self.edit_mode_label.setStyleSheet("font-weight: bold; color: red;")
        cart_layout.addWidget(self.edit_mode_label)
        cart_layout.addWidget(QLabel("سبد خرید شما:"))

        cart_scroll = QScrollArea()
        cart_scroll.setWidgetResizable(True)
        cart_container = QWidget()
        self.cart_layout = QVBoxLayout(cart_container)
        self.cart_layout.setAlignment(Qt.AlignTop)
        cart_scroll.setWidget(cart_container)
        cart_layout.addWidget(cart_scroll)

        self.total_label = QLabel("قیمت کل: 0 تومان")
        self.total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        cart_layout.addWidget(self.total_label)

        self.page_checkout = QWidget()
        checkout_layout = QVBoxLayout(self.page_checkout)
        checkout_layout.addWidget(QLabel("ثبت نهایی خرید شما"))
        self.checkout_table = QTableWidget(0, 5)
        self.checkout_table.setHorizontalHeaderLabels(["نام محصول", "تعداد", "قیمت واحد", "قیمت کل", "حذف"])
        self.checkout_table.setWordWrap(True)
        self.checkout_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.checkout_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        checkout_layout.addWidget(self.checkout_table)

        self.total_label_checkout = QLabel("جمعاً: 0 تومان")
        self.total_label_checkout.setStyleSheet("font-size: 16px; font-weight: bold;")
        checkout_layout.addWidget(self.total_label_checkout)

        self.payed_checkbox = QCheckBox("پرداخت شده")
        checkout_layout.addWidget(self.payed_checkbox)

        self.btn_confirm = QPushButton("✓ تکمیل خرید")
        self.btn_confirm.setProperty("class", "flat")
        checkout_layout.addWidget(self.btn_confirm, alignment=Qt.AlignCenter)
        self.btn_confirm.clicked.connect(self.checkout)

        self.page_receipts = QWidget()
        receipts_layout = QVBoxLayout(self.page_receipts)
        self.receipts_table = QTableWidget(0, 7)
        self.receipts_table.setHorizontalHeaderLabels(["ID","آیدی در روز", "قیمت کل", "زمان تراکنش","وضعیت پرداخت", "بارگذاری", "حذف"])
        self.receipts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.receipts_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        receipts_layout.addWidget(self.receipts_table)

        self.pages.addWidget(self.page_products)
        self.pages.addWidget(self.page_cart)
        self.pages.addWidget(self.page_checkout)
        self.pages.addWidget(self.page_receipts)

    def open_cart_panel(self):
        left, right = self.page_products.sizes()
        if right == 0:
            total = left + right
            cart_width = 350
            self.page_products.setSizes([total - cart_width, cart_width])
            self.refresh_cart_panel()

    def close_cart_panel(self):
        left, right = self.page_products.sizes()
        if right > 0:
            total = left + right
            self.page_products.setSizes([total, 0])

    def _on_add_to_cart(self):
        model = Product
        _all_fields = model._meta.fields
        _create = ["name", "buy_price", "sell_price"]
        _labels = {"name": "نام محصول", "buy_price": "قیمت خرید", "sell_price": "قیمت فروش"}
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
        product = Product(**data)
        self.add_to_cart(product, 1)
        self.show_notification(f"{product.name} به سبد اضافه شد")

    def refresh_cart_panel(self):
        while self.cart_panel_items_layout.count():
            item = self.cart_panel_items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = 0
        for product, qty in self.cart.values():
            card = PanelCartItemCard(
                product=product,
                qty=qty,
                change_qty_callback=self.update_cart_qty,
                remove_callback=self.remove_from_cart,
                parent=self
            )
            self.cart_panel_items_layout.addWidget(card)
            total += product.sell_price * qty

        self.cart_panel_total_label.setText(f"قیمت کل: {total:,} تومان")
        container = self.cart_panel_items_layout.parentWidget()
        container.adjustSize()

    def refresh_products(self):
        self.fetcher = CategoryProductFetcher()
        self.fetcher.data_fetched.connect(self.on_data_fetched)
        self.fetcher.start()

    def toggle_animations(self, state: int):
        self._parent._parent._parent.DISABLE_ANIMATIONS = bool(state)
        self.show_notification("انیمیشن‌ها " + ("غیرفعال شدند" if self._parent._parent._parent.DISABLE_ANIMATIONS else "فعال شدند"))
        self._parent._parent._parent.save_keys()

    def toggle_show_images(self, state: int):
        self._parent._parent._parent.SHOW_PRODUCT_IMAGES = bool(state)
        self.show_notification("نمایش عکس‌ها " + ("فعال شد" if self._parent._parent._parent.SHOW_PRODUCT_IMAGES else "غیرفعال شد"))
        self.refresh_products()
        self.refresh_cart()
        self.refresh_cart_panel()
        self._parent._parent._parent.save_keys()
        

    def on_tab_changed(self, index: int):
        current_widget = self.tab_widget.widget(index)
        if current_widget:
            scroll_area = current_widget.findChild(QScrollArea)
            if scroll_area:
                container = scroll_area.widget()
                if container:
                    flow_layout = container.layout()
                    if flow_layout:
                        width = scroll_area.viewport().width() - 2 * flow_layout._margin
                        height = flow_layout.heightForWidth(width)
                        container.setMinimumSize(QSize(width, height))
                        container.adjustSize()
                        scroll_area.updateGeometry()

    def on_data_fetched(self, products: list, categories: list):
 
        self.categories = categories or []

        if hasattr(self, 'tab_widget'):
            self.tab_widget.deleteLater()

        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        if not products:
            label = QLabel("محصولی موجود نیست")
            self.tab_widget.addTab(label, "محصولات")
        else:
            categories_tab = QWidget()
            categories_layout = QVBoxLayout(categories_tab)
            scroll_categories = QScrollArea()
            scroll_categories.setWidgetResizable(True)
            container_categories = QWidget()
            flow_categories = FlowLayout(container_categories)

            if any(p.category is None for p in products):
                card = CategoryCard(None, self.select_category, self._parent)
                flow_categories.addWidget(card)

            for category in categories:
                card = CategoryCard(category, self.select_category, self._parent)
                flow_categories.addWidget(card)

            scroll_categories.setWidget(container_categories)
            categories_layout.addWidget(scroll_categories)
            self.tab_widget.addTab(categories_tab, "دسته‌بندی‌ها")

            all_products_tab = QWidget()
            all_products_layout = QVBoxLayout(all_products_tab)
            # create search widget that will live inside the "All Products" tab
            self.all_products_search = SearchLineEdit(self)
            # connect search signal to filter function
            self.all_products_search.searchTriggered.connect(self.filter_all_products)
            all_products_layout.addWidget(self.all_products_search)

            scroll_all_products = QScrollArea()
            scroll_all_products.setWidgetResizable(True)
            container_all_products = QWidget()
            flow_all_products = FlowLayout(container_all_products)

            # keep references so we can filter later
            self._all_products_flow = flow_all_products
            self._all_products_container = container_all_products
            self._all_products_scroll = scroll_all_products
            self._all_products_widgets = []  # store (product, card) pairs
            self._all_products_list = products  # list of Product models

            # populate flow with all products initially
            for product in products:
                card = ProductCard(product, self.add_to_cart, self._parent)
                flow_all_products.addWidget(card)
                self._all_products_widgets.append((product, card))

            # provide products list to search widget for suggestions
            self.all_products_search.set_products(self._all_products_list)

            scroll_all_products.setWidget(container_all_products)
            all_products_layout.addWidget(scroll_all_products)
            self.tab_widget.addTab(all_products_tab, "همه محصولات")

            for category in categories:
                cat_tab = QWidget()
                cat_layout = QVBoxLayout(cat_tab)
                scroll_cat = QScrollArea()
                scroll_cat.setWidgetResizable(True)
                container_cat = QWidget()
                flow_cat = FlowLayout(container_cat)
                cat_products = [p for p in products if p.category == category]
                for product in cat_products:
                    card = ProductCard(product, self.add_to_cart, self._parent)
                    flow_cat.addWidget(card)
                scroll_cat.setWidget(container_cat)
                cat_layout.addWidget(scroll_cat)
                self.tab_widget.addTab(cat_tab, category.name)

            if any(p.category is None for p in products):
                uncat_tab = QWidget()
                uncat_layout = QVBoxLayout(uncat_tab)
                scroll_uncat = QScrollArea()
                scroll_uncat.setWidgetResizable(True)
                container_uncat = QWidget()
                flow_uncat = FlowLayout(container_uncat)
                uncat_products = [p for p in products if p.category is None]
                for product in uncat_products:
                    card = ProductCard(product, self.add_to_cart, self._parent)
                    flow_uncat.addWidget(card)
                scroll_uncat.setWidget(container_uncat)
                uncat_layout.addWidget(scroll_uncat)
                self.tab_widget.addTab(uncat_tab, "بدون دسته‌بندی")

        left_layout = self.left_widget.layout()
        left_layout.addWidget(self.tab_widget)
        self.show_notification("محصولات و دسته‌بندی‌ها با موفقیت به‌روزرسانی شدند")
    def filter_all_products(self, query: str):
        """
        Filter product cards shown in the 'All Products' flow by query.
        Uses case-insensitive substring match. Shows/hides existing cards
        (does NOT remove/recreate layout items).
        """
        q = (query or "").strip().lower()

        widgets = getattr(self, "_all_products_widgets", None)
        if not widgets:
            return

        for product, card in widgets:
            # if empty query -> show all
            if not q:
                card.setVisible(True)
            else:
                card.setVisible(q in (product.name or "").lower())

        # adjust geometry so scroll area updates
        container = getattr(self, "_all_products_container", None)
        if container:
            container.adjustSize()
        scroll = getattr(self, "_all_products_scroll", None)
        if scroll:
            scroll.updateGeometry()

    def select_category(self, category: Category):
        tab_text = "بدون دسته‌بندی" if category is None else category.name
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == tab_text:
                self.tab_widget.setCurrentIndex(i)
                break

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
