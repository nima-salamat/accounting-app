"""Category tile for product browsing."""
"""Product, category and cart cards used by point-of-sale pages."""
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
from ui.panels.sell_card_style import get_color_from_name


class CategoryCard(QWidget):
    def __init__(self, category: Category, select_callback, parent=None):
        super().__init__(parent)
        self.category = category
        self.select_callback = select_callback
        self.setFixedSize(180, 100)

        # Set background color based on category ID
        color = get_color_from_name(self.category.name if self.category else "بدون دسته‌بندی")
        self.setStyleSheet(f"""
            QLabel {{
                background: {color};
                border-radius: 8px;
            }}
        """)

        # Single clickable label
        self.label = QLabel(self.category.name if self.category else "بدون دسته‌بندی", alignment=Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            "border: 2px solid white;"
            "border-radius: 6px;"
            "color: white;"
            "padding: 8px;"
        )
        self.label.setCursor(Qt.PointingHandCursor)
        # Forward click on label to callback
        self.label.mousePressEvent = lambda event: self.select_callback(self.category)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

    def sizeHint(self) -> QSize:
        return QSize(180, 100)
