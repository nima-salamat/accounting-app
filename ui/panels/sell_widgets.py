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
