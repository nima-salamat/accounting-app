"""Compact cart row cards and their quantity controls."""
"""Product, category and cart cards used by point-of-sale pages."""
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
from ui.panels.sell_layouts import SmallFlatButton


class PanelCartItemCard(QWidget):
    def __init__(self, product: Product, qty: int, change_qty_callback, remove_callback, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.product = product
        self.qty = qty
        self.change_qty_callback = change_qty_callback
        self.remove_callback = remove_callback
        self._build_ui()

    def _build_ui(self):
        self.setFixedHeight(100)
        # Background color
        try:
            bg_color = get_color_from_name(self.product.name)
        except NameError:
            bg_color = "#3E3E3E"
        self.setStyleSheet(f"""
            background: {bg_color};
            border-radius: 8px;
            padding: 4px;
            QLabel {{ color: white;}}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # Top section: image + name or only name depending on SHOW_PRODUCT_IMAGES
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        if self._parent._parent._parent._parent.SHOW_PRODUCT_IMAGES:
            if self.product.image_path and os.path.isfile(self.product.image_path):
                img_label = QLabel()
                img_label.setFixedSize(48, 48)
                pix = QPixmap(self.product.image_path).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                img_label.setPixmap(pix)
                top_layout.addWidget(img_label)
        # Name label
        name_label = QLabel(self.product.name)
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        top_layout.addWidget(name_label, 1)
        main_layout.addLayout(top_layout)

        # Bottom section: controls
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

       
       
        dec_btn = SmallFlatButton("➖", self)
        inc_btn = SmallFlatButton("➕", self)
        del_btn = SmallFlatButton("✖️", self)

        dec_btn.clicked.connect(lambda: self._change_qty(-1))
        bottom_layout.addWidget(dec_btn)

        # Quantity display
        self.qty_label = QLabel(str(self.qty), alignment=Qt.AlignCenter)
        self.qty_label.setFixedSize(32, 28)
        self.qty_label.setStyleSheet("color: white; font-size: 14px;")
        bottom_layout.addWidget(self.qty_label)

        inc_btn.clicked.connect(lambda: self._change_qty(+1))
        bottom_layout.addWidget(inc_btn)

        bottom_layout.addStretch(1)

        del_btn.clicked.connect(lambda: self.remove_callback(self.product.id))
        bottom_layout.addWidget(del_btn)

        main_layout.addLayout(bottom_layout)

    def _change_qty(self, delta: int):
        new_qty = self.qty + delta
        if new_qty < 1:
            self.remove_callback(self.product.id)
        else:
            self.qty = new_qty
            self.qty_label.setText(str(self.qty))
            self.change_qty_callback(self.product.id, self.qty)


class CartItemCard(QWidget):
    def __init__(self, product, qty, change_qty_callback, remove_callback, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.product = product
        self.qty = qty
        self.change_qty_callback = change_qty_callback
        self.remove_callback = remove_callback
        self.setObjectName("cartItemCard")
        self.setStyleSheet("""
            #cartItemCard {
                background: #f9f9f9;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px;
            }
            QLabel {
                font-size: 14px;
            }
            QLabel#item_title {
                font-weight: bold;
                font-size: 15px;
            }
            QLabel#no_image {
                background: #eee;
                border: 1px dashed #ccc;
                border-radius: 40px;
                font-size: 12px;
            }
            QPushButton.flat {
                background: transparent;
                border: none;
                font-size: 16px;
                color: #0078D7;
                border: 0.5px solid #3F51B5;

            }
            QPushButton.flat:hover {
                color: #005a9e;
            }
        """)
        self._build_ui()

    def _build_ui(self):
        self.setFixedHeight(100)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(14)

 
        img_label = QLabel(alignment=Qt.AlignCenter)
        img_label.setFixedSize(80, 80)
        if self._parent._parent._parent.SHOW_PRODUCT_IMAGES:
            if self.product.image_path and os.path.isfile(self.product.image_path):
                pix = QPixmap(self.product.image_path).scaled(
                    80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                img_label.setPixmap(pix)
            else:
                img_label.setObjectName("no_image")
                img_label.setText("📦\nبدون تصویر")
                img_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(img_label)

     
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_layout.setAlignment(Qt.AlignVCenter)

        name_label = QLabel(self.product.name)
        name_label.setObjectName("item_title")
        info_layout.addWidget(name_label)

        price_label = QLabel(f"{self.product.sell_price:,} تومان")
        info_layout.addWidget(price_label)


        qty_controls = QHBoxLayout()
        qty_controls.setSpacing(6)
        qty_controls.setAlignment(Qt.AlignLeft)

        btn_dec = QPushButton("➖")
        btn_dec.setObjectName("btn_decrease")
        btn_dec.setFixedSize(24, 24)
        btn_dec.setProperty("class", "flat")
        btn_dec.clicked.connect(lambda _: self.change_qty(-1))
        qty_controls.addWidget(btn_dec)

        self.qty_label = QLabel(str(self.qty), alignment=Qt.AlignCenter)
        self.qty_label.setFixedSize(30, 24)
        self.qty_label.setObjectName("qty_display")
        self.qty_label.setStyleSheet("background: #f0f0f0; border-radius: 4px; font-weight: bold;color:black;")
        qty_controls.addWidget(self.qty_label)

        btn_inc = QPushButton("➕")
        btn_inc.setObjectName("btn_increase")
        btn_inc.setFixedSize(24, 24)
        btn_inc.setProperty("class", "flat")
        btn_inc.clicked.connect(lambda _: self.change_qty(+1))
        qty_controls.addWidget(btn_inc)

        info_layout.addLayout(qty_controls)
        layout.addLayout(info_layout)


        remove_btn = QPushButton("❌")
        remove_btn.setObjectName("remove_btn")
        remove_btn.setFixedSize(30, 30)
        remove_btn.setProperty("class", "flat")
        remove_btn.clicked.connect(lambda _: self.remove_callback(self.product.id))
        layout.addWidget(remove_btn, alignment=Qt.AlignTop)

    def change_qty(self, delta):
        new_qty = self.qty + delta
        if new_qty < 1:
            self.remove_callback(self.product.id)
        elif new_qty <= 100:
            self.qty = new_qty
            self.qty_label.setText(str(self.qty))
            self.change_qty_callback(self.product.id, self.qty)
