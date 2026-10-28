"""Visual product card with stock-independent cart interactions."""
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
from ui.panels.sell_card_style import get_color_from_name


class ProductCard(QWidget):
    def __init__(self, product: Product, add_callback, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.product = product
        self.add_callback = add_callback
        self.qty: int = 1
        self._card_size = QSize(180, 260)
        self.setAttribute(Qt.WA_Hover, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._build_ui()
        self._setup_hover_effect()

    def _build_ui(self):
        if self._parent._parent._parent.SHOW_PRODUCT_IMAGES:
            self._card_size = QSize(180, 260)
        else:
            self._card_size = QSize(180, 140) 

 
        self.setFixedSize(self._card_size)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        

        if self._parent._parent._parent.SHOW_PRODUCT_IMAGES:
            # Image view
            img_label = QLabel(alignment=Qt.AlignCenter)
            img_label.setFixedSize(150, 150)
            img_label.setObjectName("imageContainerbes")
            if self.product.image_path and os.path.isfile(self.product.image_path):
                pix = QPixmap(self.product.image_path).scaled(
                    150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                img_label.setPixmap(pix)
            else:
                img_label.setText("No Image")
                img_label.setStyleSheet("color: gray; border: 1px solid #ccc; border-radius: 4px;")
            layout.addWidget(img_label)

            # Price and quantity controls
            name_label = QLabel(f"{self.product.name} ")
            name_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(name_label)
            # Price and quantity controls
            price_label = QLabel(f"{self.product.sell_price:,} تومان")
            price_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(price_label)

            qty_layout = QHBoxLayout()
            qty_layout.setSpacing(14)
            qty_layout.setAlignment(Qt.AlignCenter)
            for label, slot in [("➖", self.decrease_qty), ("➕", self.increase_qty)]:
                btn = QPushButton(label)
                btn.setProperty("class", "flat")
                btn.setFixedSize(30, 30)
                btn.clicked.connect(slot)
                qty_layout.addWidget(btn)
            self.qty_label = QLabel(str(self.qty), alignment=Qt.AlignCenter)
            self.qty_label.setFixedSize(30, 30)
            qty_layout.insertWidget(1, self.qty_label)
            layout.addLayout(qty_layout)

            add_btn = QPushButton("افزودن")
            add_btn.setProperty("class", "flat")
            add_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            add_btn.clicked.connect(self.add_to_cart)
            layout.addWidget(add_btn)
        else:
            # No image: use a single clickable info label with background color
            color = get_color_from_name(self.product.name)
            self.setStyleSheet(f"""
                QLabel {{
                    background: {color};
                    border-radius: 8px;
                }}
            """)
            info_label = QLabel(f"{self.product.name}\n\n\n\n{self.product.sell_price:,} تومان")
            info_label.setWordWrap(True)
            info_label.setAlignment(Qt.AlignCenter)
            info_label.setStyleSheet(
                "border: 2px solid white;"
                "border-radius: 6px;"
                "padding: 6px;"
            )
            info_label.setCursor(Qt.PointingHandCursor)
            info_label.mousePressEvent = lambda event: self.add_to_cart()
            font = QFont("Tahoma")
            font.setPointSize(24)  # Set font size to 18pt
            info_label.setFont(font)
            layout.addWidget(info_label)

    def _setup_hover_effect(self):
        if getattr(self._parent._parent._parent, 'DISABLE_ANIMATIONS', False):
            return
        self._hover_anim = QPropertyAnimation(self, b"cardSize")
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._shadow_anim = QPropertyAnimation(self, b"windowOpacity")
        self._shadow_anim.setDuration(180)
        self._shadow_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._group = QParallelAnimationGroup()
        self._group.addAnimation(self._hover_anim)
        self._group.addAnimation(self._shadow_anim)

    def enterEvent(self, event):
        if getattr(self._parent._parent._parent, 'DISABLE_ANIMATIONS', False):
            return
        if self._parent._parent._parent.SHOW_PRODUCT_IMAGES:
            self._card_size = QSize(200, 280)
        else:
            self._card_size = QSize(200, 160) 
        self._group.stop()
        self._hover_anim.setStartValue(self.size())
        self._hover_anim.setEndValue(self._card_size)
        self._shadow_anim.setStartValue(0.9)
        self._shadow_anim.setEndValue(1.0)
        self._group.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if getattr(self._parent._parent._parent, 'DISABLE_ANIMATIONS', False):
            return
        if self._parent._parent._parent.SHOW_PRODUCT_IMAGES:
            self._card_size = QSize(180, 260)
        else:
            self._card_size = QSize(180, 140) 

 
        self._group.stop()
        self._hover_anim.setStartValue(self.size())
        self._hover_anim.setEndValue(self._card_size)
        self._shadow_anim.setStartValue(1.0)
        self._shadow_anim.setEndValue(0.9)
        self._group.start()
        
       
        super().leaveEvent(event)

    def get_card_size(self) -> QSize:
        return self.size()

    def set_card_size(self, size: QSize):
        self.setFixedSize(size)

    cardSize = Property(QSize, get_card_size, set_card_size)

    def increase_qty(self):
        if self.qty < 100:
            self.qty += 1
            self.qty_label.setText(str(self.qty))

    def decrease_qty(self):
        if self.qty > 1:
            self.qty -= 1
            self.qty_label.setText(str(self.qty))

    def add_to_cart(self):
        qty = self.qty if self._parent._parent._parent.SHOW_PRODUCT_IMAGES else 1
        # call provided callback
        try:
            self.add_callback(self.product, qty)
        except Exception:
            # fallback if callback expects different signature
            try:
                self.add_callback(self.product)
            except Exception:
                pass
        if self._parent._parent._parent.SHOW_PRODUCT_IMAGES:
            self.qty = 1
            self.qty_label.setText(str(self.qty))
