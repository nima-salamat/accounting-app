from PySide2.QtWidgets import (
    QWidget, QLabel, QPushButton, QMenuBar, QMenu, QVBoxLayout,
    QSizePolicy, QDockWidget, QMainWindow, QHBoxLayout,QApplication,
    QStackedWidget, QAction, QShortcut
)
from PySide2.QtGui import  Qt, QKeySequence, QPainter, QPolygonF, QPixmap, QDrag
from PySide2.QtCore import QPointF, QByteArray
from PySide2.QtCore import QMimeData

from ui.user_panel import UserManagement, UserPanel
from ui.category_panel import CategoryManagement
from ui.product_panel import ProductManagement
from ui.receipt_panel import ReceiptManagement
from ui.receipt_product_panel import ReceiptProductManagement
from ui.report_panel import ProductSalesChartPanel
from ui.home_panel import Home
from ui.sell_panel import SellPanel
from ui.warehouse_panel import WarehouseManagement
from ui.styles.dashboard_styles import dark_qss, light_qss
from ui.menu_bar import MenuBar
from ui.float_bar import DockWidget
from ui.checks import CheckInPanel, CheckOutPanel
from functools import partial



class BaseWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Central widget
        self.main_widget = QWidget()
        self.main_widget.setObjectName("main_widget")
        self.setCentralWidget(self.main_widget)

        # Layout
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setAlignment(Qt.AlignTop | Qt.AlignCenter)

        self.init()
        

    def add_layout(self, layout):
        self.main_layout.addLayout(layout)

    def add_widget(self, widget):
        self.main_layout.addWidget(widget)


class MainPanel(BaseWindow):
    def init(self):

        self.apply_theme(self._parent.mode)

        self.dock_widget = DockWidget("نوار دسترسی", self)
        self.dock_widget.add_buttons_from_indices(self._parent.button_indices)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)

        self.menu_bar = MenuBar(self)
        self.add_widget(self.menu_bar)

        self.manager_panel = ManagerPanel(self)
        self.add_widget(self.manager_panel)
        

    def apply_theme(self, mode: str):

        base_qss = dark_qss if mode == "dark" else light_qss
        bg_url = "assets/cool-purple-background-design.jpg"
        combined = f"{base_qss}\n" \
                   f"#main_widget {{\n" \
                   f"  background-image: url({bg_url});\n" \
                   f"  background-repeat: no-repeat;\n" \
                   f"  background-position: center center;\n" \
                   f"  background-size: cover;\n" \
                   f"}}"
        self.setStyleSheet(combined)
        

    def update_theme(self, mode: str):
        self._parent.mode = mode
        self.apply_theme(mode)


class ToggleButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_open = True
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(10)
        self.setMinimumHeight(150)
        self.setFocusPolicy(Qt.NoFocus)
        self.setObjectName("ToggleButton")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = self.palette().color(self.foregroundRole())
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        w, h = self.width(), self.height()
        cy = h / 2
        m, s = 5, 10
        tri = QPolygonF()
        if self._is_open:
            tri.append(QPointF(w - m, cy - s))
            tri.append(QPointF(w - m, cy + s))
            tri.append(QPointF(w - m - s, cy))
        else:
            tri.append(QPointF(m, cy - s))
            tri.append(QPointF(m, cy + s))
            tri.append(QPointF(m + s, cy))
        painter.drawPolygon(tri)

    def set_open(self, state: bool):
        self._is_open = state
        self.update()

    def toggle(self):
        self.set_open(not self._is_open)

class DraggableButton(QPushButton):
    def __init__(self, text, index, parent=None):
        super().__init__(text, parent)
        self.index = index
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos and (event.pos() - self._drag_start_pos).manhattanLength() > QApplication.startDragDistance():
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData('application/x-panel-index', QByteArray.number(self.index))
            drag.setMimeData(mime)
            pix = QPixmap(self.size())
            self.render(pix)
            drag.setPixmap(pix)
            drag.exec_(Qt.MoveAction)
            self._drag_start_pos = None  # Prevent multiple drags
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)



class ManagerPanel(QWidget):
    def __init__(self, parent=None):
        self.selected_button = None
        
        super().__init__(parent)
        self._parent = parent
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Side panel buttons container
        self.button_container = QWidget()
        self.button_container.setObjectName("button_container")
        btn_layout = QVBoxLayout(self.button_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)
        self.button_container.setFixedWidth(150)
        self.layout.addWidget(self.button_container)

        # Toggle button
        self.toggle_btn = ToggleButton(self)
        self.toggle_btn.clicked.connect(self.toggle_panel)
        self.layout.addWidget(self.toggle_btn)

        # Wrapper for stacked pages
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(30, 15, 30, 15)
        wrapper_layout.setSpacing(0)
        self.page_stack = QStackedWidget()
        self.page_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        wrapper_layout.addWidget(self.page_stack)
        self.layout.addWidget(wrapper)

        # پنل‌ها و نام‌ها
        self.panel_classes = [
            Home, UserPanel, UserManagement, ProductManagement,
            CategoryManagement, ReceiptManagement, ReceiptProductManagement,
            WarehouseManagement ,SellPanel, ProductSalesChartPanel, CheckInPanel, CheckOutPanel
        ]
        names = ["خانه", "کاربر", "کاربران", "محصولات", "دسته بندی ها",
                 "رسید ها", "آیتم رسید","خرید ها", "فروش", "گزارش", "طلبکاری", "بدهکاری"]
        self.pages = [None] * len(self.panel_classes)
        self.buttons = []
        # ساخت دکمه‌های درگ‌ابل
        for idx, name in enumerate(names):
            btn = DraggableButton(name, idx, self)
            btn.clicked.connect(partial(self.show_page, idx))
            self.buttons.append(btn)
            btn_layout.addWidget(btn)

        # ESC برای بازگشت به خانه
        QShortcut(QKeySequence("Esc"), self).activated.connect(lambda: self.show_page(0))

        self.show_page(0)
        self.panel_open = True

    def show_page(self, idx: int):
        if not idx in self._parent._parent.visible_buttons:
            return

        # تغییر ظاهر دکمه قبلی
        if self.selected_button:
            self.selected_button.setProperty("active", False)
            self.selected_button.style().unpolish(self.selected_button)
            self.selected_button.style().polish(self.selected_button)

        # تغییر ظاهر دکمه جدید
        btn = self.buttons[idx]
        btn.setProperty("active", True)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        self.selected_button = btn

        if self.pages[idx] is None:
            panel = self.panel_classes[idx](self)
            panel.setProperty("class", "my_panel")
            panel.style().unpolish(panel)
            panel.style().polish(panel)
            panel.update()
            self.pages[idx] = panel
            self.page_stack.addWidget(panel)
        self.page_stack.setCurrentWidget(self.pages[idx])


    def toggle_panel(self):
        self.panel_open = not self.panel_open
        self.button_container.setVisible(self.panel_open)
        self.toggle_btn.set_open(self.panel_open)

    def set_visible_buttons(self, indexes: list[int]):
        layout = self.button_container.layout()

        # همه دکمه‌ها را مخفی و از layout حذف کن
        for btn in self.buttons:
            layout.removeWidget(btn)
            btn.hide()

        # فقط دکمه‌های مورد نظر را به ترتیب مشخص شده اضافه و نمایش بده
        for idx in indexes:
            if 0 <= idx < len(self.buttons):
                btn = self.buttons[idx]
                layout.addWidget(btn)
                btn.show()
