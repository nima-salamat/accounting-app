"""WYSIWYG invoice designer with a physical page canvas, movable fields and grouped properties."""
from copy import deepcopy

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QBrush, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFormLayout, QFrame, QGraphicsItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from client.ui.invoice_render import (
    DEFAULT_TEMPLATE, ELEMENT_TYPES, default_elements_for_paper, draw_invoice_element,
    normalize_elements, page_dimensions, render_invoice_html,
)
from client.ui.permissions import can_access


SAMPLE_RECEIPT = {
    "id": "preview-invoice", "day_receipt_id": "۱۰۰۱",
    "created_at": "2026-10-29T12:00:00", "payed": True, "total_price": 1285000,
    "items": [
        {"product_name": "نمونه کالا", "quantity": 2, "sell_price": 450000},
        {"product_name": "کالای دوم", "quantity": 1, "sell_price": 385000},
        {"product_name": "لوازم جانبی", "quantity": 1, "sell_price": 85000},
    ],
    "seat_number": "۱۲",
}
ELEMENT_LABELS = {
    "company": "نام و مشخصات مجموعه",
    "invoice_number": "شماره فاکتور",
    "invoice_date": "تاریخ فاکتور",
    "payment_status": "وضعیت پرداخت",
    "seat_number": "شماره میز / صندلی",
    "items_table": "جدول کالاها",
    "totals": "مبلغ نهایی",
    "footer": "متن پایانی",
    "text": "متن آزاد",
}
PRESETS = [
    ("formal", "فاکتور فارسی · A4"),
    ("minimal", "فاکتور مینیمال · A4"),
    ("a5", "فاکتور فروشگاهی · A5"),
    ("thermal80", "رسید صندوق · رول ۸۰"),
    ("thermal58", "رسید جمع‌وجور · رول ۵۸"),
    ("cafe", "رسید کافه و شماره میز"),
    ("return", "رسید مرجوعی · A5"),
]

TEMPLATE_KINDS = [
    ("invoice", "فاکتور فروش"),
    ("pos_receipt", "رسید صندوق / POS"),
    ("kiosk_receipt", "رسید کیوسک"),
    ("return_slip", "رسید مرجوعی"),
    ("purchase_slip", "سند خرید"),
]


class _DesignerScene(QGraphicsScene):
    elementMoved = Signal(object)


class _PanZoomGraphicsView(QGraphicsView):
    """Canvas with wheel zoom and middle-button drag panning."""

    zoomChanged = Signal(float)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom = 1.0
        self._user_zoomed = False
        self._pan_position = None
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def fit_page(self, rect):
        self.resetTransform()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = 1.0
        self._user_zoomed = False
        self.zoomChanged.emit(self._zoom)

    def zoom_by(self, factor):
        new_zoom = max(0.2, min(5.0, self._zoom * float(factor)))
        if abs(new_zoom - self._zoom) < 0.0001:
            return
        ratio = new_zoom / self._zoom
        self.scale(ratio, ratio)
        self._zoom = new_zoom
        self._user_zoomed = True
        self.zoomChanged.emit(self._zoom)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            event.ignore()
            return
        self.zoom_by(1.15 ** (delta / 120.0))
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_position = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_position is not None:
            current = event.position().toPoint()
            delta = current - self._pan_position
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_position = current
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_position is not None:
            self._pan_position = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _DesignerElementItem(QGraphicsRectItem):
    def __init__(self, element, page, scene):
        super().__init__(QRectF(0, 0, float(element["w_mm"]), float(element["h_mm"])))
        self.element = element
        self.page = page
        self.setPos(float(element["x_mm"]), float(element["y_mm"]))
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def paint(self, painter, option, widget=None):
        self.element["x_mm"] = float(self.pos().x())
        self.element["y_mm"] = float(self.pos().y())
        self.element["w_mm"] = float(self.rect().width())
        self.element["h_mm"] = float(self.rect().height())
        draw_invoice_element(
            painter, self.rect(), self.element, SAMPLE_RECEIPT,
            self.page._values(), editor=True, selected=self.isSelected(),
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            bounds = self.scene().sceneRect()
            x = max(0.0, min(float(value.x()), max(0.0, bounds.width() - self.rect().width())))
            y = max(0.0, min(float(value.y()), max(0.0, bounds.height() - self.rect().height())))
            return QPointF(x, y)
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.scene().elementMoved.emit(self)
            self.update()
        return result

    def update_element(self, element):
        self.element = element
        self.setRect(QRectF(0, 0, float(element["w_mm"]), float(element["h_mm"])))
        self.setPos(float(element["x_mm"]), float(element["y_mm"]))
        self.update()


class InvoiceTemplatesPage(QFrame):
    """A single studio-like workspace; page shape and on-paper positions match the saved invoice."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self._loading = False
        self._template_kind = "invoice"
        self._elements = []
        self._items_by_id = {}
        self._selected_id = None
        self._last_page_size = page_dimensions(DEFAULT_TEMPLATE)
        self.accent_color_value = DEFAULT_TEMPLATE["accent_color"]
        self.frame_border_color_value = DEFAULT_TEMPLATE["frame_border_color"]
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("طراح بصری فاکتور")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "المان‌ها را روی خود برگه بکشید؛ مختصات بر حسب میلی‌متر ذخیره می‌شود. "
            "اندازهٔ کاغذ و جهت صفحه، قاب پیش‌نمایش و خروجی چاپ را تغییر می‌دهند."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box, 1)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.save_button = QPushButton("ذخیرهٔ قالب")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_template)
        heading.addWidget(self.refresh_button)
        heading.addWidget(self.save_button)
        root.addLayout(heading)

        toolbar = QFrame()
        toolbar.setObjectName("Card")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 7, 10, 7)
        toolbar_layout.setSpacing(4)
        toolbar_top = QHBoxLayout()
        toolbar_top.setSpacing(7)
        toolbar_bottom = QHBoxLayout()
        toolbar_bottom.setSpacing(7)
        self.document_kind = QComboBox()
        for key, label in TEMPLATE_KINDS:
            self.document_kind.addItem(label, key)
        self.preset = QComboBox()
        for key, label in PRESETS:
            self.preset.addItem(label, key)
        self.apply_preset_button = QPushButton("استفاده از قالب آماده")
        self.apply_preset_button.clicked.connect(self.apply_preset)
        self.paper_size = QComboBox()
        self.paper_size.addItem("A4 · ۲۱۰ × ۲۹۷", "A4")
        self.paper_size.addItem("A5 · ۱۴۸ × ۲۱۰", "A5")
        self.paper_size.addItem("A6 · ۱۰۵ × ۱۴۸", "A6")
        self.paper_size.addItem("رسید حرارتی · ۸۰mm", "receipt80")
        self.paper_size.addItem("رسید حرارتی · ۵۸mm", "receipt58")
        self.orientation = QComboBox()
        self.orientation.addItem("عمودی", "portrait")
        self.orientation.addItem("افقی", "landscape")
        self.margin_mm = QSpinBox()
        self.margin_mm.setRange(2, 30)
        self.margin_mm.setSuffix(" mm")
        self.show_border = QCheckBox("قاب چاپ")
        self.show_border.setChecked(True)
        self.accent_button = QPushButton("رنگ اصلی")
        self.accent_button.clicked.connect(lambda: self._pick_color("accent"))
        self.accent_swatch = QLabel()
        self.accent_swatch.setFixedWidth(24)
        self.accent_swatch.setMinimumHeight(22)
        self.border_button = QPushButton("رنگ قاب")
        self.border_button.clicked.connect(lambda: self._pick_color("border"))
        self.border_swatch = QLabel()
        self.border_swatch.setFixedWidth(24)
        self.border_swatch.setMinimumHeight(22)
        toolbar_top.addWidget(QLabel("نوع برگه"))
        toolbar_top.addWidget(self.document_kind, 1)
        toolbar_top.addWidget(QLabel("قالب آماده"))
        toolbar_top.addWidget(self.preset, 1)
        toolbar_top.addWidget(self.apply_preset_button)
        toolbar_top.addWidget(QLabel("کاغذ"))
        toolbar_top.addWidget(self.paper_size)
        toolbar_top.addWidget(self.orientation)
        toolbar_top.addWidget(QLabel("حاشیه"))
        toolbar_top.addWidget(self.margin_mm)
        toolbar_bottom.addWidget(self.show_border)
        toolbar_bottom.addWidget(self.accent_button)
        toolbar_bottom.addWidget(self.accent_swatch)
        toolbar_bottom.addWidget(self.border_button)
        toolbar_bottom.addWidget(self.border_swatch)
        toolbar_bottom.addStretch(1)
        toolbar_layout.addLayout(toolbar_top)
        toolbar_layout.addLayout(toolbar_bottom)
        root.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Right-hand properties inspector.
        properties_scroll = QScrollArea()
        properties_scroll.setWidgetResizable(True)
        properties_scroll.setMinimumWidth(245)
        properties = QWidget()
        properties.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        properties_layout = QVBoxLayout(properties)
        properties_layout.setContentsMargins(4, 4, 4, 4)
        properties_layout.setSpacing(10)

        element_card = QFrame()
        element_card.setObjectName("Card")
        element_layout = QVBoxLayout(element_card)
        element_layout.setContentsMargins(12, 12, 12, 12)
        element_layout.setSpacing(8)
        selected_heading = QLabel("تنظیمات المان انتخاب‌شده")
        selected_heading.setObjectName("PageTitle")
        element_layout.addWidget(selected_heading)
        self.selected_kind = QLabel("برای ویرایش، یک المان روی برگه انتخاب کنید.")
        self.selected_kind.setObjectName("PageSubtitle")
        self.selected_kind.setWordWrap(True)
        element_layout.addWidget(self.selected_kind)
        form = QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.element_label = QLineEdit()
        self.element_label.setPlaceholderText("برچسب یا متن المان")
        self.x_mm = self._spin(0, 600, " mm")
        self.y_mm = self._spin(0, 600, " mm")
        self.w_mm = self._spin(3, 600, " mm")
        self.h_mm = self._spin(3, 600, " mm")
        self.element_font_size = self._spin(6, 32, " pt")
        self.element_align = QComboBox()
        self.element_align.addItem("راست‌چین", "right")
        self.element_align.addItem("وسط‌چین", "center")
        self.element_align.addItem("چپ‌چین", "left")
        self.element_bold = QCheckBox("متن ضخیم")
        form.addRow("متن / برچسب", self.element_label)
        form.addRow("موقعیت افقی X", self.x_mm)
        form.addRow("موقعیت عمودی Y", self.y_mm)
        form.addRow("عرض", self.w_mm)
        form.addRow("ارتفاع", self.h_mm)
        form.addRow("اندازهٔ نوشته", self.element_font_size)
        form.addRow("تراز نوشته", self.element_align)
        form.addRow("", self.element_bold)
        element_layout.addLayout(form)
        self.duplicate_button = QPushButton("تکثیر المان")
        self.duplicate_button.clicked.connect(self.duplicate_element)
        self.delete_button = QPushButton("حذف المان انتخاب‌شده")
        self.delete_button.setObjectName("DangerButton")
        self.delete_button.clicked.connect(self.delete_element)
        element_layout.addWidget(self.duplicate_button)
        element_layout.addWidget(self.delete_button)
        properties_layout.addWidget(element_card)

        business_card = QFrame()
        business_card.setObjectName("Card")
        business_layout = QVBoxLayout(business_card)
        business_layout.setContentsMargins(12, 12, 12, 12)
        business_layout.setSpacing(8)
        business_title = QLabel("اطلاعات عمومی فاکتور")
        business_title.setObjectName("PageTitle")
        business_layout.addWidget(business_title)
        business_form = QFormLayout()
        business_form.setSpacing(8)
        self.company_name = QLineEdit()
        self.legal_id = QLineEdit()
        self.phone = QLineEdit()
        self.address = QTextEdit()
        self.address.setFixedHeight(58)
        self.footer = QTextEdit()
        self.footer.setFixedHeight(58)
        self.font_family = QComboBox()
        self.font_family.setEditable(True)
        self.font_family.addItems([
            "Vazirmatn", "Noto Sans Arabic", "Noto Naskh Arabic", "Tahoma",
            "Segoe UI", "Arial", "IRANSans", "B Nazanin",
        ])
        self.global_font_size = self._spin(8, 18, " pt")
        business_form.addRow("نام مجموعه", self.company_name)
        business_form.addRow("شناسه / مالیاتی", self.legal_id)
        business_form.addRow("تلفن", self.phone)
        business_form.addRow("نشانی", self.address)
        business_form.addRow("متن پایین فاکتور", self.footer)
        business_form.addRow("فونت", self.font_family)
        business_form.addRow("اندازهٔ پایه", self.global_font_size)
        business_layout.addLayout(business_form)
        properties_layout.addWidget(business_card)
        properties_layout.addStretch(1)
        properties_scroll.setWidget(properties)

        # Physical page in the center.
        canvas_card = QFrame()
        canvas_card.setObjectName("Card")
        canvas_layout = QVBoxLayout(canvas_card)
        canvas_layout.setContentsMargins(8, 8, 8, 8)
        canvas_layout.setSpacing(6)
        self.page_info = QLabel("A4 · عمودی · ۲۱۰ × ۲۹۷ میلی‌متر")
        self.page_info.setObjectName("StatusPill")
        self.page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        view_toolbar = QHBoxLayout()
        view_toolbar.setSpacing(5)
        view_toolbar.addWidget(self.page_info, 1)
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setToolTip("کوچک‌نمایی")
        self.zoom_out_button.setObjectName("CompactActionButton")
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setToolTip("بزرگ‌نمایی")
        self.zoom_in_button.setObjectName("CompactActionButton")
        self.zoom_label = QLabel("۱۰۰٪")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fit_button = QPushButton("برازش صفحه")
        self.fit_button.setToolTip("نمایش تمام برگه")
        self.fit_button.setObjectName("CompactActionButton")
        view_toolbar.addWidget(self.zoom_out_button)
        view_toolbar.addWidget(self.zoom_label)
        view_toolbar.addWidget(self.zoom_in_button)
        view_toolbar.addWidget(self.fit_button)
        canvas_layout.addLayout(view_toolbar)
        self.scene = _DesignerScene(self)
        self.scene.elementMoved.connect(self._element_moved)
        self.canvas = _PanZoomGraphicsView(self.scene)
        self.canvas.setObjectName("InvoiceDesignerCanvas")
        self.canvas.setBackgroundBrush(QBrush(QColor("#E9EDF4")))
        self.canvas.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.canvas.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setMinimumWidth(360)
        self.canvas.setMinimumHeight(400)
        self.scene.selectionChanged.connect(self._canvas_selection_changed)
        canvas_layout.addWidget(self.canvas, 1)
        self.canvas_help = QLabel(
            "برای زوم از چرخ موس، برای جابه‌جایی برگه دکمهٔ وسط موس را نگه دارید و بکشید؛ «برازش صفحه» نمای کامل را برمی‌گرداند."
        )
        self.canvas_help.setObjectName("PageSubtitle")
        self.canvas_help.setWordWrap(True)
        canvas_layout.addWidget(self.canvas_help)

        # Element palette and layer list on the left.
        palette_scroll = QScrollArea()
        palette_scroll.setWidgetResizable(True)
        palette_scroll.setMinimumWidth(210)
        palette = QWidget()
        palette.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        palette_layout = QVBoxLayout(palette)
        palette_layout.setContentsMargins(4, 4, 4, 4)
        palette_layout.setSpacing(10)
        add_card = QFrame()
        add_card.setObjectName("Card")
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(12, 12, 12, 12)
        add_layout.setSpacing(8)
        add_title = QLabel("افزودن المان")
        add_title.setObjectName("PageTitle")
        add_layout.addWidget(add_title)
        self.new_kind = QComboBox()
        for kind in ELEMENT_TYPES:
            self.new_kind.addItem(ELEMENT_LABELS[kind], kind)
        self.add_button = QPushButton("＋ افزودن به برگه")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.clicked.connect(self.add_element)
        add_layout.addWidget(self.new_kind)
        add_layout.addWidget(self.add_button)
        self.elements_list = QListWidget()
        self.elements_list.setMinimumHeight(180)
        self.elements_list.currentRowChanged.connect(self._list_selection_changed)
        add_layout.addWidget(QLabel("المان‌های برگه"))
        add_layout.addWidget(self.elements_list, 1)
        self.reset_layout_button = QPushButton("بازنشانی چیدمان قالب")
        self.reset_layout_button.clicked.connect(self.reset_layout)
        add_layout.addWidget(self.reset_layout_button)
        palette_layout.addWidget(add_card)
        palette_layout.addStretch(1)
        palette_scroll.setWidget(palette)

        splitter.addWidget(properties_scroll)
        splitter.addWidget(canvas_card)
        splitter.addWidget(palette_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([290, 660, 240])
        root.addWidget(splitter, 1)

        self.paper_size.currentIndexChanged.connect(self._page_dimensions_changed)
        self.orientation.currentIndexChanged.connect(self._page_dimensions_changed)
        self.margin_mm.valueChanged.connect(self._page_style_changed)
        self.show_border.toggled.connect(self._page_style_changed)
        self.element_label.textEdited.connect(self._selected_property_changed)
        for control in (self.x_mm, self.y_mm, self.w_mm, self.h_mm, self.element_font_size):
            control.valueChanged.connect(self._selected_property_changed)
        self.element_align.currentIndexChanged.connect(self._selected_property_changed)
        self.element_bold.toggled.connect(self._selected_property_changed)
        for control in (self.company_name, self.legal_id, self.phone):
            control.textChanged.connect(self._global_setting_changed)
        self.address.textChanged.connect(self._global_setting_changed)
        self.footer.textChanged.connect(self._global_setting_changed)
        self.font_family.currentTextChanged.connect(self._global_setting_changed)
        self.global_font_size.valueChanged.connect(self._global_setting_changed)
        self.document_kind.currentIndexChanged.connect(self._document_kind_changed)
        self.zoom_out_button.clicked.connect(lambda: self.canvas.zoom_by(1 / 1.2))
        self.zoom_in_button.clicked.connect(lambda: self.canvas.zoom_by(1.2))
        self.fit_button.clicked.connect(lambda: self._fit_page(force=True))
        self.canvas.zoomChanged.connect(self._zoom_label_changed)

        self._load_template(deepcopy(DEFAULT_TEMPLATE))
        self.set_permissions(window.current_user)

    @staticmethod
    def _spin(minimum, maximum, suffix):
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setSuffix(suffix)
        return control

    def set_permissions(self, user):
        self.save_button.setVisible(can_access(user, "invoices", "update"))
        self.refresh_button.setVisible(can_access(user, "invoices", "read"))
        self.apply_preset_button.setEnabled(can_access(user, "invoices", "update"))
        self.add_button.setEnabled(can_access(user, "invoices", "update"))
        self.delete_button.setEnabled(can_access(user, "invoices", "update"))
        self.duplicate_button.setEnabled(can_access(user, "invoices", "update"))

    def refresh(self):
        if self.window.api and can_access(self.window.current_user, "invoices", "read"):
            kind = self._template_kind
            self.window.run_api(
                lambda: self.window.api.get_invoice_template(kind=kind),
                self._load_template,
                failure=lambda error: self.window.show_error(error),
                busy=self.refresh_button,
            )

    def _current_page_settings(self):
        return {
            "paper_size": self.paper_size.currentData() or "A4",
            "orientation": self.orientation.currentData() or "portrait",
            "margin_mm": self.margin_mm.value(),
        }

    def _values(self):
        result = {
            "company_name": self.company_name.text().strip() or "نام کسب‌وکار",
            "legal_id": self.legal_id.text().strip(),
            "address": self.address.toPlainText().strip(),
            "phone": self.phone.text().strip(),
            "seat_number_label": "شماره میز / صندلی",
            "footer": self.footer.toPlainText().strip(),
            "paper_size": self.paper_size.currentData() or "A4",
            "orientation": self.orientation.currentData() or "portrait",
            "margin_mm": self.margin_mm.value(),
            "font_family": self.font_family.currentText().strip() or "Vazirmatn",
            "font_size": self.global_font_size.value(),
            "header_font_size": min(32, self.global_font_size.value() + 6),
            "line_height": 1.5,
            "text_direction": "rtl",
            "accent_color": self.accent_color_value,
            "show_border": self.show_border.isChecked(),
            "frame_border_color": self.frame_border_color_value,
            "layout_order": list(DEFAULT_TEMPLATE["layout_order"]),
            "block_settings": deepcopy(DEFAULT_TEMPLATE["block_settings"]),
            "table_alignment": deepcopy(DEFAULT_TEMPLATE["table_alignment"]),
            "elements": deepcopy(self._elements),
        }
        return result

    def _load_template(self, values):
        values = dict(DEFAULT_TEMPLATE, **(values or {}))
        self._loading = True
        for control, key, fallback in (
            (self.company_name, "company_name", "نام کسب‌وکار"),
            (self.legal_id, "legal_id", ""),
            (self.phone, "phone", ""),
        ):
            control.setText(str(values.get(key, fallback) or ""))
        self.address.setPlainText(str(values.get("address", "") or ""))
        self.footer.setPlainText(str(values.get("footer", "") or ""))
        self.paper_size.setCurrentIndex(max(0, self.paper_size.findData(values.get("paper_size", "A4"))))
        paper_value = values.get("paper_size", "A4")
        self.orientation.setCurrentIndex(max(0, self.orientation.findData(values.get("orientation", "portrait"))))
        is_thermal = paper_value in ("receipt", "receipt80", "receipt58")
        if is_thermal:
            self.orientation.blockSignals(True)
            self.orientation.setCurrentIndex(max(0, self.orientation.findData("portrait")))
            self.orientation.blockSignals(False)
        self.orientation.setEnabled(not is_thermal)
        self.margin_mm.setValue(int(values.get("margin_mm", 12)))
        self.show_border.setChecked(bool(values.get("show_border", True)))
        self.accent_color_value = str(values.get("accent_color", "#3157A4"))
        self.frame_border_color_value = str(values.get("frame_border_color", "#CBD5E1"))
        self.font_family.setCurrentText(str(values.get("font_family", "Vazirmatn")))
        self.global_font_size.setValue(int(values.get("font_size", 11)))
        self.accent_swatch.setStyleSheet(
            "background:{};border:1px solid #64748B;border-radius:4px;".format(self.accent_color_value)
        )
        self.border_swatch.setStyleSheet(
            "background:{};border:1px solid #64748B;border-radius:4px;".format(self.frame_border_color_value)
        )
        raw_elements = values.get("elements")
        self._elements = normalize_elements(raw_elements if raw_elements is not None else default_elements_for_paper(
            values.get("paper_size", "A4"), values.get("orientation", "portrait"), values.get("margin_mm", 12)
        ), values)
        self._loading = False
        self._last_page_size = page_dimensions(self._values())
        self._rebuild_canvas()
        self._refresh_element_list()
        self._load_selected_properties(None)
        self._update_page_info()
        self._update_canvas_appearance()

    def _rebuild_canvas(self):
        self.scene.clear()
        self._items_by_id.clear()
        self._paper_item = None
        self._safe_margin_item = None
        width, height = page_dimensions(self._values())
        self.scene.setSceneRect(QRectF(0, 0, width, height))
        page = QGraphicsRectItem(QRectF(0, 0, width, height))
        page.setBrush(QBrush(QColor("#FFFFFF")))
        page.setPen(QPen(QColor(self.frame_border_color_value), 0.6 if self.show_border.isChecked() else 0.25))
        page.setZValue(-100)
        page.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._paper_item = page
        self.scene.addItem(page)
        margin = float(self.margin_mm.value())
        safe = QGraphicsRectItem(QRectF(margin, margin, max(1, width - 2 * margin), max(1, height - 2 * margin)))
        safe.setPen(QPen(QColor("#CBD5E1"), 0.25, Qt.PenStyle.DashLine))
        safe.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        safe.setZValue(-90)
        safe.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._safe_margin_item = safe
        self.scene.addItem(safe)
        current_template = self._values()
        for element in self._elements:
            item = _DesignerElementItem(element, self, self.scene)
            item.setPos(float(element["x_mm"]), float(element["y_mm"]))
            self.scene.addItem(item)
            self._items_by_id[element["id"]] = item
        self.scene.update()
        self._update_page_info()
        self._fit_page(force=True)

    def _fit_page(self, force=False):
        if self.scene.sceneRect().isEmpty():
            return
        if force or not self.canvas._user_zoomed:
            self.canvas.fit_page(self.scene.sceneRect())

    def _zoom_label_changed(self, zoom):
        percent = int(round(float(zoom) * 100))
        self.zoom_label.setText("{}٪".format(str(percent).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))))

    def _document_kind_changed(self, *_args):
        kind = self.document_kind.currentData() or "invoice"
        if kind == self._template_kind:
            return
        self._template_kind = kind
        if self.window.api is None:
            self._load_template(self._local_default_for_kind(kind))
            return
        self.document_kind.setEnabled(False)
        self.window.run_api(
            lambda: self.window.api.get_invoice_template(kind=kind),
            lambda values, requested=kind: self._load_template(values) if requested == self._template_kind else None,
            failure=lambda error: self.window.show_error(error),
            busy=self.document_kind,
        )

    @staticmethod
    def _local_default_for_kind(kind):
        values = deepcopy(DEFAULT_TEMPLATE)
        paper = "A4"
        margin = 12
        if kind in ("pos_receipt", "kiosk_receipt"):
            paper, margin = "receipt80", 4
            values["accent_color"] = "#0F766E" if kind == "pos_receipt" else "#3157A4"
            values["font_size"] = 9
            values["footer"] = "از خرید شما سپاسگزاریم."
        elif kind == "return_slip":
            paper, margin = "A5", 8
            values["accent_color"] = "#B45309"
            values["footer"] = "کالای مرجوعی بررسی و ثبت شد."
        elif kind == "purchase_slip":
            paper, margin = "A4", 12
            values["accent_color"] = "#475569"
            values["footer"] = "سند خرید را بررسی و نگهداری کنید."
        values["paper_size"] = paper
        values["orientation"] = "portrait"
        values["margin_mm"] = margin
        values["elements"] = default_elements_for_paper(paper, "portrait", margin)
        if kind == "return_slip":
            for element in values["elements"]:
                if element["type"] == "invoice_number":
                    element["label"] = "شماره رسید مرجوعی"
                elif element["type"] == "invoice_date":
                    element["label"] = "تاریخ مرجوعی"
                elif element["type"] in ("seat_number", "payment_status"):
                    element["visible"] = False
        elif kind == "purchase_slip":
            for element in values["elements"]:
                if element["type"] == "invoice_number":
                    element["label"] = "شماره سند خرید"
                elif element["type"] == "seat_number":
                    element["label"] = "تأمین‌کننده"
                elif element["type"] == "payment_status":
                    element["label"] = "وضعیت تسویه"
        return values

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_page()

    def _update_canvas_appearance(self, *_args):
        self._update_page_info()
        if self._paper_item is not None:
            pen = QPen(QColor(self.frame_border_color_value), 0.65 if self.show_border.isChecked() else 0.25)
            self._paper_item.setPen(pen)
        if self._safe_margin_item is not None:
            width, height = page_dimensions(self._values())
            margin = float(self.margin_mm.value())
            self._safe_margin_item.setRect(QRectF(margin, margin, max(1, width - 2 * margin), max(1, height - 2 * margin)))
        self.scene.update()
        for item in self._items_by_id.values():
            item.page = self
            item.update()

    def _update_page_info(self):
        width, height = page_dimensions(self._values())
        if hasattr(self, "x_mm"):
            self.x_mm.setRange(0, max(0, int(width) - 3))
            self.y_mm.setRange(0, max(0, int(height) - 3))
            self.w_mm.setRange(3, max(3, int(width)))
            self.h_mm.setRange(3, max(3, int(height)))
        paper = self.paper_size.currentData() or "A4"
        orientation = self.orientation.currentData() or "portrait"
        is_thermal = paper in ("receipt80", "receipt58")
        orientation_text = "حرارتی (جهت ثابت)" if is_thermal else ("افقی" if orientation == "landscape" else "عمودی")
        paper_label = {"receipt80": "رسید حرارتی ۸۰mm", "receipt58": "رسید حرارتی ۵۸mm"}.get(paper, paper)
        self.page_info.setText("{} · {} · {:.0f} × {:.0f} میلی‌متر".format(
            paper_label, orientation_text, width, height
        ))

    def _page_style_changed(self, *_args):
        if self._loading:
            return
        self._update_canvas_appearance()

    def _page_dimensions_changed(self, *_args):
        if self._loading:
            return
        paper = self.paper_size.currentData() or "A4"
        is_thermal = paper in ("receipt", "receipt80", "receipt58")
        self.orientation.setEnabled(not is_thermal)
        if is_thermal and self.orientation.currentData() != "portrait":
            self.orientation.blockSignals(True)
            self.orientation.setCurrentIndex(max(0, self.orientation.findData("portrait")))
            self.orientation.blockSignals(False)
        old_width, old_height = self._last_page_size
        new_width, new_height = page_dimensions(self._values())
        scale_x = new_width / old_width if old_width else 1
        scale_y = new_height / old_height if old_height else 1
        self._loading = True
        for element in self._elements:
            element_w = max(3.0, min(new_width, float(element["w_mm"]) * scale_x))
            element_h = max(3.0, min(new_height, float(element["h_mm"]) * scale_y))
            element["w_mm"] = element_w
            element["h_mm"] = element_h
            element["x_mm"] = max(0.0, min(new_width - element_w, float(element["x_mm"]) * scale_x))
            element["y_mm"] = max(0.0, min(new_height - element_h, float(element["y_mm"]) * scale_y))
        self._loading = False
        self._last_page_size = (new_width, new_height)
        self._rebuild_canvas()
        self._refresh_element_list()
        self._load_selected_properties(self._selected_id)
        self._update_canvas_appearance()

    def _pick_color(self, target):
        current = self.accent_color_value if target == "accent" else self.frame_border_color_value
        chosen = QColorDialog.getColor(QColor(current), self, "انتخاب رنگ")
        if not chosen.isValid():
            return
        if target == "accent":
            self.accent_color_value = chosen.name().upper()
            self.accent_swatch.setStyleSheet("background:{};border:1px solid #64748B;border-radius:4px;".format(self.accent_color_value))
        else:
            self.frame_border_color_value = chosen.name().upper()
            self.border_swatch.setStyleSheet("background:{};border:1px solid #64748B;border-radius:4px;".format(self.frame_border_color_value))
        self._update_canvas_appearance()

    def _refresh_element_list(self):
        chosen = self._selected_id
        self.elements_list.blockSignals(True)
        self.elements_list.clear()
        for element in self._elements:
            item = QListWidgetItem("{}  ·  {}".format(
                ELEMENT_LABELS.get(element["type"], element["type"]),
                element.get("label") or element["id"],
            ))
            item.setData(Qt.ItemDataRole.UserRole, element["id"])
            self.elements_list.addItem(item)
            if element["id"] == chosen:
                self.elements_list.setCurrentItem(item)
        self.elements_list.blockSignals(False)

    def _element_by_id(self, element_id):
        return next((item for item in self._elements if item["id"] == element_id), None)

    def _list_selection_changed(self, row):
        if self._loading or row < 0:
            return
        list_item = self.elements_list.item(row)
        element_id = list_item.data(Qt.ItemDataRole.UserRole)
        item = self._items_by_id.get(element_id)
        if item is not None:
            self.scene.blockSignals(True)
            self.scene.clearSelection()
            item.setSelected(True)
            self.scene.blockSignals(False)
            self._canvas_selection_changed()
            self.canvas.centerOn(item)

    def _canvas_selection_changed(self):
        if self._loading:
            return
        selected = self.scene.selectedItems()
        item = selected[0] if selected else None
        element_id = item.element["id"] if isinstance(item, _DesignerElementItem) else None
        self._load_selected_properties(element_id)
        if element_id:
            self.elements_list.blockSignals(True)
            for row in range(self.elements_list.count()):
                if self.elements_list.item(row).data(Qt.ItemDataRole.UserRole) == element_id:
                    self.elements_list.setCurrentRow(row)
                    break
            self.elements_list.blockSignals(False)

    def _load_selected_properties(self, element_id):
        element = self._element_by_id(element_id) if element_id else None
        self._loading = True
        self._selected_id = element_id if element else None
        self.selected_kind.setText(
            ELEMENT_LABELS.get(element["type"], element["type"]) if element else
            "برای ویرایش، یک المان روی برگه انتخاب کنید."
        )
        controls = (
            self.element_label, self.x_mm, self.y_mm, self.w_mm, self.h_mm,
            self.element_font_size, self.element_align, self.element_bold,
            self.duplicate_button, self.delete_button,
        )
        for control in controls:
            control.setEnabled(bool(element))
        if element:
            width, height = page_dimensions(self._values())
            element_width = max(3.0, min(width, float(element["w_mm"])))
            element_height = max(3.0, min(height, float(element["h_mm"])))
            element["w_mm"] = element_width
            element["h_mm"] = element_height
            element["x_mm"] = max(0.0, min(width - element_width, float(element["x_mm"])))
            element["y_mm"] = max(0.0, min(height - element_height, float(element["y_mm"])))
            self.element_label.setText(element.get("text") if element["type"] == "text" else element.get("label", ""))
            self.w_mm.setRange(3, max(3, int(width)))
            self.h_mm.setRange(3, max(3, int(height)))
            self.w_mm.setValue(round(element["w_mm"]))
            self.h_mm.setValue(round(element["h_mm"]))
            self.x_mm.setRange(0, max(0, int(width - element["w_mm"])))
            self.y_mm.setRange(0, max(0, int(height - element["h_mm"])))
            self.x_mm.setValue(round(element["x_mm"]))
            self.y_mm.setValue(round(element["y_mm"]))
            self.element_font_size.setValue(int(element.get("font_size", 9)))
            idx = self.element_align.findData(element.get("align", "right"))
            self.element_align.setCurrentIndex(max(0, idx))
            self.element_bold.setChecked(bool(element.get("bold", False)))
        else:
            self.element_label.clear()
        self._loading = False

    def _selected_property_changed(self, *_args):
        if self._loading or not self._selected_id:
            return
        element = self._element_by_id(self._selected_id)
        item = self._items_by_id.get(self._selected_id)
        if element is None or item is None:
            return
        if element["type"] == "text":
            element["text"] = self.element_label.text()[:500]
            element["label"] = element["text"][:80]
        else:
            element["label"] = self.element_label.text()[:80]
        width, height = page_dimensions(self._values())
        element["w_mm"] = max(3.0, min(width, float(self.w_mm.value())))
        element["h_mm"] = max(3.0, min(height, float(self.h_mm.value())))
        element["x_mm"] = max(0.0, min(width - element["w_mm"], float(self.x_mm.value())))
        element["y_mm"] = max(0.0, min(height - element["h_mm"], float(self.y_mm.value())))
        element["font_size"] = self.element_font_size.value()
        element["align"] = self.element_align.currentData() or "right"
        element["bold"] = self.element_bold.isChecked()
        item.element = element
        item.setRect(QRectF(0, 0, element["w_mm"], element["h_mm"]))
        item.setPos(element["x_mm"], element["y_mm"])
        item.update()
        self._refresh_element_list()
        self._update_canvas_appearance()

    def _element_moved(self, item):
        if self._loading or not isinstance(item, _DesignerElementItem):
            return
        element = self._element_by_id(item.element["id"])
        if element is None:
            return
        element["x_mm"] = float(item.pos().x())
        element["y_mm"] = float(item.pos().y())
        item.element = element
        if item.isSelected():
            self._load_selected_properties(element["id"])
        self._refresh_element_list()
        self._update_page_info()

    def _global_setting_changed(self, *_args):
        if self._loading:
            return
        # Keep existing item objects so their drag positions and current selection do not jump.
        config = self._values()
        for item in self._items_by_id.values():
            item.page = self
            item.update()
        self._update_page_info()

    def add_element(self):
        kind = self.new_kind.currentData() or "text"
        used = {element["id"] for element in self._elements}
        base = kind.replace("_", "-")
        element_id = base
        number = 2
        while element_id in used:
            element_id = "{}-{}".format(base, number)
            number += 1
        width, height = page_dimensions(self._values())
        element = {
            "id": element_id, "type": kind,
            "label": ELEMENT_LABELS.get(kind, "متن جدید"),
            "text": "متن جدید" if kind == "text" else "",
            "x_mm": max(0, min(width - 20, width * 0.2)),
            "y_mm": max(0, min(height - 12, height * 0.45)),
            "w_mm": min(max(22, width * 0.6), width),
            "h_mm": 12 if kind != "items_table" else min(70, height * 0.35),
            "font_size": 9, "align": "right", "bold": kind in ("invoice_number", "totals"),
            "visible": True,
        }
        element = normalize_elements([element], self._values())[0]
        self._elements.append(element)
        self._rebuild_canvas()
        self._refresh_element_list()
        item = self._items_by_id[element_id]
        item.setSelected(True)
        self._canvas_selection_changed()

    def duplicate_element(self):
        original = self._element_by_id(self._selected_id)
        if original is None:
            return
        duplicate = deepcopy(original)
        used = {element["id"] for element in self._elements}
        index = 2
        base = original["id"][:36]
        duplicate["id"] = "{}-{}".format(base, index)
        while duplicate["id"] in used:
            index += 1
            duplicate["id"] = "{}-{}".format(base, index)
        duplicate["x_mm"] = min(page_dimensions(self._values())[0] - duplicate["w_mm"], duplicate["x_mm"] + 5)
        duplicate["y_mm"] = min(page_dimensions(self._values())[1] - duplicate["h_mm"], duplicate["y_mm"] + 5)
        self._elements.append(duplicate)
        self._selected_id = duplicate["id"]
        self._rebuild_canvas()
        self._refresh_element_list()
        self._load_selected_properties(duplicate["id"])
        self._items_by_id[duplicate["id"]].setSelected(True)

    def delete_element(self):
        if not self._selected_id:
            return
        self._elements = [element for element in self._elements if element["id"] != self._selected_id]
        self._selected_id = None
        self._rebuild_canvas()
        self._refresh_element_list()
        self._load_selected_properties(None)

    def reset_layout(self):
        answer = QMessageBox.question(
            self, "بازنشانی چیدمان",
            "موقعیت و اندازهٔ المان‌ها به چیدمان پیش‌فرض همین کاغذ برگردد؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._elements = normalize_elements(
            default_elements_for_paper(
                self.paper_size.currentData(), self.orientation.currentData(), self.margin_mm.value()
            ),
            self._values(),
        )
        self._selected_id = None
        self._rebuild_canvas()
        self._refresh_element_list()
        self._load_selected_properties(None)

    def apply_preset(self):
        preset = self.preset.currentData()
        values = deepcopy(DEFAULT_TEMPLATE)
        if preset == "minimal":
            values.update({"paper_size": "A4", "orientation": "portrait", "accent_color": "#475569", "show_border": False, "frame_border_color": "#CBD5E1"})
        elif preset == "a5":
            values.update({"paper_size": "A5", "orientation": "portrait", "accent_color": "#0F766E", "show_border": True})
        elif preset == "thermal80":
            values.update({"paper_size": "receipt80", "orientation": "portrait", "accent_color": "#111827", "show_border": True, "margin_mm": 4, "font_size": 9})
        elif preset == "thermal58":
            values.update({"paper_size": "receipt58", "orientation": "portrait", "accent_color": "#111827", "show_border": True, "margin_mm": 3, "font_size": 8})
        elif preset == "return":
            values.update({"paper_size": "A5", "orientation": "portrait", "accent_color": "#B45309", "show_border": True, "margin_mm": 8})
        elif preset == "cafe":
            values.update({"paper_size": "A5", "orientation": "portrait", "accent_color": "#7C3AED", "show_border": True})
        else:
            values.update({"paper_size": "A4", "orientation": "portrait", "accent_color": "#3157A4", "show_border": True})
        values["elements"] = default_elements_for_paper(
            values["paper_size"], values["orientation"], values["margin_mm"]
        )
        if preset == "cafe":
            for element in values["elements"]:
                if element["type"] == "seat_number":
                    element["visible"] = True
                    element["label"] = "شماره میز / صندلی"
        self._load_template(values)

    def save_template(self):
        values = self._values()
        if not values["company_name"]:
            self.window.show_error("نام کسب‌وکار نباید خالی باشد.")
            return
        if not self.window.api:
            self.window.show_error("اتصال سرور برقرار نیست.")
            return
        self.window.run_api(
            lambda: self.window.api.save_invoice_template(kind=self._template_kind, **values),
            self._saved,
            failure=lambda error: self.window.show_error(error),
            busy=self.save_button,
        )

    def _saved(self, values):
        self._load_template(values)
        label = dict(TEMPLATE_KINDS).get(self._template_kind, "قالب برگه")
        self.window.set_status("قالب «{}» روی سرور ذخیره شد.".format(label))
        QMessageBox.information(self, "ذخیره شد", "قالب «{}» مستقل ذخیره شد و در پیش‌نمایش و چاپ استفاده می‌شود.".format(label))
