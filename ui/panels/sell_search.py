"""Product search field and completion widget for point-of-sale pages."""
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

COLORS = [
    "#D84315",  # Deep Orange
    "#1565C0",  # Indigo Blue
    "#C2185B",  # Raspberry
    "#7B1FA2",  # Purple
    "#512DA8",  # Deep Purple
    "#9E9D24",  # Olive
    "#8D6E63",  # Brown
    "#5E35B1",  # Muted Violet
    "#2E7D32",  # Dark Green
]



def get_color_from_name(name: str) -> str:
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return COLORS[h % len(COLORS)]

class SearchLineEdit(QWidget):
    """
    Search widget placed inside the "All Products" tab.
    - shows suggestions via QCompleter (product names)
    - on Enter or search button, emits search and triggers filtering of the 'All Products' flow
    """
    searchTriggered = Signal(str)

    def __init__(self, sellpanel):
        super().__init__(sellpanel)
        self.sellpanel = sellpanel
        self.line = QLineEdit(self)
        self.line.setPlaceholderText("نام محصول (کامل یا قسمتی) را تایپ کنید و Enter بزنید...")
        self.search_btn = QPushButton("🔍", self)
        self.search_btn.setFixedHeight(self.line.sizeHint().height())
        self.search_btn.setProperty("class", "flat")

        # completer for suggestions (shows product names)
        self.string_model = QStringListModel(self)
        self.completer = QCompleter(self.string_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.line.setCompleter(self.completer)

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(self.line)
        h.addWidget(self.search_btn)
        self.setLayout(h)

        # signals
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.line.returnPressed.connect(self._on_search_clicked)
        self.line.textEdited.connect(self._on_text_edited)

        # internal list of products (Product models)
        self._products = []

    def set_products(self, products: list):
        """Provide list of Product models for suggestions."""
        self._products = products or []
        # initialize completer list with all names
        names = [p.name for p in self._products]
        self.string_model.setStringList(names)

    def _on_text_edited(self, text: str):
        s = text.strip()
        if not s:
            names = [p.name for p in self._products]
        else:
            names = [p.name for p in self._products if s.lower() in (p.name or "").lower()]

        if names != self.string_model.stringList():
            self.string_model.setStringList(names)
            # ensure completer uses the fresh model
            try:
                self.completer.setModel(self.string_model)
            except Exception:
                pass

        # try to show popup (only if there are suggestions)
        if names:
            try:
                self.completer.complete()
            except Exception:
                pass


    def _on_search_clicked(self):
        text = self.line.text().strip()
        # emit the search text; SellPanel will handle filtering
        self.searchTriggered.emit(text)
