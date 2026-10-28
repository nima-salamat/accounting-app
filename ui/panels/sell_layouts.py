"""Reusable layouts and lightweight controls for the point-of-sale screen."""
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

class SplitterAnimation(QVariantAnimation):
    def __init__(self, splitter, start_sizes, end_sizes, parent=None):
        super().__init__(parent)
        self.splitter = splitter
        self.setStartValue(start_sizes)
        self.setEndValue(end_sizes)

    def updateCurrentValue(self, value):
        if isinstance(value, list):
            self.splitter.setSizes(value)

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 10, h_spacing: int = 10, v_spacing: int = 10):
        super().__init__(parent)
        self._items = []
        self._margin = margin
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        if parent:
            self.setParent(parent)
            parent.setLayout(self)

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < self.count() else None

    def takeAt(self, index: int):
        if 0 <= index < self.count():
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.doLayout(QRect(0, 0, width, 0), testOnly=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self.doLayout(rect)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        if not self._items:
            return QSize(0, 0)
        max_width = max(item.sizeHint().width() for item in self._items)
        max_height = max(item.sizeHint().height() for item in self._items)
        l = self._margin
        size = QSize(max_width + 2 * l, max_height + 2 * l)
        return size

    def doLayout(self, rect: QRect, testOnly: bool = False) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)

        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        max_x = effective_rect.right()
        spacing = self._h_spacing

        for item in self._items:
            widget = item.widget()
            if not widget or not widget.isVisible():
                continue
            item_size = item.sizeHint()
            next_x = x + item_size.width()
            if next_x > max_x + 1 and x > effective_rect.x():
                x = effective_rect.x()
                y += line_height + self._v_spacing
                next_x = x + item_size.width()
                line_height = 0
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item_size))
            x = next_x + spacing
            line_height = max(line_height, item_size.height())
        return y + line_height - rect.y()

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations()

class SmallFlatButton(QPushButton):
    def __init__(self, text: str, parent=None, icon_path: str = None):
        super().__init__(text, parent)
        self.setProperty("class", "flat")
        self.setFixedSize(28, 28)
        if icon_path and os.path.isfile(icon_path):
            pix = QPixmap(icon_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setIcon(pix)
        self.setStyleSheet("background: transparent; border: none; font-size: 18px; border: 0.5px solid #3F51B5;margin:0.5px;")
