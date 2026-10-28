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

from ui.panels.sell_catalog_mixin import SellCatalogMixin
from ui.panels.sell_checkout_mixin import SellCheckoutMixin


class SellPanel(SellCatalogMixin, SellCheckoutMixin, QWidget):
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
