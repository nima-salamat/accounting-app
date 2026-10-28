"""Product browsing, categories, animated layout and cart panel behavior."""
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QMessageBox, QScrollArea, QSizePolicy, QTableWidget, QCompleter,
    QTableWidgetItem, QTabWidget, QHeaderView, QCheckBox, QSizeGrip, QLayout, QSplitter, QLineEdit, QFrame
)
from PySide6.QtGui import QPixmap, QRegion, QFont
from PySide6.QtCore import QTimer, QEasingCurve, QPropertyAnimation, QSize, QPoint, QRect, Property, Signal
from PySide6.QtCore import QParallelAnimationGroup, QStringListModel
from collections import defaultdict
from datetime import datetime, date
from db.models import Product, Receipt, ReceiptProduct, Category
from accounting_app.services.sales import record_sale
from ui.base_panel import RecordDialog, RecordAdder, QDialog, to_jalali
from functools import partial
from PySide6.QtCore import QVariantAnimation
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



class SellCatalogMixin:
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
        if dlg.exec() != QDialog.Accepted:
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
        self.fetcher.error.connect(self._on_product_fetch_error)
        self.fetcher.start()

    def _on_product_fetch_error(self, message):
        QMessageBox.warning(self, "خطا در دریافت محصولات", message)

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
