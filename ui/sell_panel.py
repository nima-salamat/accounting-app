
import os
from PySide2.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QMessageBox, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QTabWidget, QHeaderView, QCheckBox, QSizeGrip, QLayout, QSplitter
)
from PySide2.QtGui import QPixmap, Qt, QRegion, QFont
from PySide2.QtCore import QTimer, QEasingCurve, QPropertyAnimation, QSize, QPoint, QRect, Property, Signal
from PySide2.QtCore import QParallelAnimationGroup
from collections import defaultdict
from datetime import datetime, date
from db.models import Product, Receipt, ReceiptProduct, Category
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


# ثابت در طول اجرا
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
        self.add_callback(self.product, qty)
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

        # تصویر محصول یا جایگزینش
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

        # اطلاعات محصول
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_layout.setAlignment(Qt.AlignVCenter)

        name_label = QLabel(self.product.name)
        name_label.setObjectName("item_title")
        info_layout.addWidget(name_label)

        price_label = QLabel(f"{self.product.sell_price:,} تومان")
        info_layout.addWidget(price_label)

        # کنترل تعداد
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

        # دکمه حذف
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


class CategoryProductFetcher(QThread):
    data_fetched = Signal(list, list)

    def run(self):
        products = list(Product.select().where(Product.custom_product==False).prefetch(Category))
        categories = list(Category.select())
        self.data_fetched.emit(products, categories)

class ReceiptFetcher(QThread):
    receipts_fetched = Signal(list)

    def run(self):
        receipts = list(Receipt.select().order_by(Receipt.created_at.desc()).limit(25))
        self.receipts_fetched.emit(receipts)

class CheckoutWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, cart, user, payed: bool, edit_mode: bool = False, receipt_to_delete=None):
        super().__init__()
        self.cart = cart
        self.user = user
        self.payed = payed
        self.edit_mode = edit_mode
        self.receipt_to_delete = receipt_to_delete

    def run(self):
        try:
            if not self.cart:
                self.finished.emit(False, "سبد خرید خالی است.")
                return

            total = sum(p.sell_price * q for p, q in self.cart.values())

            today = date.today()

            # اگر در حالت ویرایش هستیم، شماره قبلی رو نگه می‌داریم
            if self.edit_mode and self.receipt_to_delete:
                old_day_receipt_id = self.receipt_to_delete.day_receipt_id
            else:
                try: 
                    last_receipt = Receipt.select().order_by(Receipt.created_at.desc()).first()              
                    if last_receipt.created_at.date() == date.today():
                        
                        old_day_receipt_id = last_receipt.day_receipt_id +1
                    else: 
                        old_day_receipt_id = 1 
                        
                except:
                    old_day_receipt_id = 1 

            # ساخت رسید جدید
            receipt = Receipt.create(
                user=self.user,
                payed=self.payed,
                total_price=total,
                day_receipt_id=old_day_receipt_id,
            )

            for product, qty in self.cart.values():
                ReceiptProduct.create(
                    receipt=receipt,
                    product=product,
                    sell_price=product.sell_price,
                    buy_price=product.buy_price,
                    quantity=qty
                )

            if self.edit_mode and self.receipt_to_delete:
                self.receipt_to_delete.delete_instance(recursive=True)

            self.finished.emit(True, "فروش شما با موفقیت ثبت شد")

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.finished.emit(False, "خطایی در ثبت فروش رخ داد.")
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
            btn.setStyleSheet("")  # پاک کردن استایل قبلی
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
            scroll_all_products = QScrollArea()
            scroll_all_products.setWidgetResizable(True)
            container_all_products = QWidget()
            flow_all_products = FlowLayout(container_all_products)

            for product in products:
                card = ProductCard(product, self.add_to_cart, self._parent)
                flow_all_products.addWidget(card)

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
