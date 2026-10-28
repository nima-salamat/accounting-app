"""Visual invoice designer with draggable sections, page setup and editable alignment."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QSpinBox, QTextBrowser, QTextEdit, QVBoxLayout,
    QWidget, QAbstractItemView,
)

from client.ui.invoice_render import DEFAULT_TEMPLATE, render_invoice_html
from client.ui.permissions import can_access


BLOCK_LABELS = {
    "company": "سربرگ و مشخصات شرکت",
    "metadata": "شماره فاکتور، تاریخ و وضعیت",
    "items": "جدول کالاها",
    "totals": "مبلغ نهایی",
    "footer": "متن پایانی",
}
COLUMN_LABELS = (("تمام عرض", "full"), ("ستون راست", "right"), ("ستون چپ", "left"))
ALIGN_LABELS = (("راست‌چین", "right"), ("وسط‌چین", "center"), ("چپ‌چین", "left"))
TABLE_COLUMN_LABELS = {
    "index": "شماره ردیف", "name": "نام کالا", "quantity": "تعداد",
    "unit_price": "قیمت واحد", "line_total": "جمع ردیف",
}


class InvoiceTemplatesPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self._loading = False
        self.block_settings = dict(DEFAULT_TEMPLATE["block_settings"])
        self.table_alignment = dict(DEFAULT_TEMPLATE["table_alignment"])
        self.accent_color_value = DEFAULT_TEMPLATE["accent_color"]
        self.frame_border_color_value = DEFAULT_TEMPLATE["frame_border_color"]
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("طراحی حرفه‌ای فاکتور و برگه‌های چاپی")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "اندازه و جهت کاغذ، قاب، رنگ، ترتیب بلوک‌ها با کشیدن، ستون و تراز را تنظیم کنید. "
            "همین قالب روی پیش‌نمایش، PDF و چاپ رسیدهای فروش اعمال می‌شود."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles, 1)
        self.refresh_button = QPushButton("بازخوانی قالب")
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button)
        root.addLayout(heading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setMinimumWidth(430)
        editor = QWidget()
        editor.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(4, 4, 4, 4)
        editor_layout.setSpacing(12)

        identity_card = QFrame()
        identity_card.setObjectName("Card")
        identity_form = QFormLayout(identity_card)
        identity_form.setContentsMargins(14, 14, 14, 14)
        identity_form.setSpacing(9)
        self.company_name = QLineEdit()
        self.company_name.setPlaceholderText("نام فروشگاه / شرکت")
        self.legal_id = QLineEdit()
        self.legal_id.setPlaceholderText("شناسه ثبت یا مالیاتی (اختیاری)")
        self.address = QTextEdit()
        self.address.setPlaceholderText("نشانی چاپ‌شده روی برگه")
        self.address.setFixedHeight(64)
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("تلفن تماس")
        self.footer = QTextEdit()
        self.footer.setPlaceholderText("متن پایین فاکتور")
        self.footer.setFixedHeight(64)
        identity_form.addRow("نام مجموعه", self.company_name)
        identity_form.addRow("شناسه", self.legal_id)
        identity_form.addRow("نشانی", self.address)
        identity_form.addRow("تلفن", self.phone)
        identity_form.addRow("متن پایین", self.footer)
        editor_layout.addWidget(identity_card)

        page_card = QFrame()
        page_card.setObjectName("Card")
        page_form = QFormLayout(page_card)
        page_form.setContentsMargins(14, 14, 14, 14)
        page_form.setSpacing(9)
        self.paper_size = QComboBox()
        self.paper_size.addItem("A4 · 210 × 297 mm", "A4")
        self.paper_size.addItem("A5 · 148 × 210 mm", "A5")
        self.paper_size.addItem("A6 · 105 × 148 mm", "A6")
        self.paper_size.addItem("رسید حرارتی · 80 mm", "receipt80")
        self.paper_size.addItem("رسید حرارتی · 58 mm", "receipt58")
        self.orientation = QComboBox()
        self.orientation.addItem("عمودی (Portrait)", "portrait")
        self.orientation.addItem("افقی (Landscape)", "landscape")
        self.margin_mm = QSpinBox()
        self.margin_mm.setRange(3, 30)
        self.margin_mm.setSuffix(" mm")
        self.show_border = QCheckBox("نمایش قاب دور برگه")
        self.show_border.setChecked(True)
        self.accent_color_button = QPushButton("انتخاب رنگ اصلی…")
        self.accent_color_button.clicked.connect(lambda: self._pick_color("accent"))
        self.border_color_button = QPushButton("رنگ قاب…")
        self.border_color_button.clicked.connect(lambda: self._pick_color("border"))
        self.accent_swatch = QLabel()
        self.accent_swatch.setMinimumHeight(18)
        self.border_swatch = QLabel()
        self.border_swatch.setMinimumHeight(18)
        page_form.addRow("اندازه کاغذ", self.paper_size)
        page_form.addRow("جهت صفحه", self.orientation)
        page_form.addRow("حاشیه کاغذ", self.margin_mm)
        page_form.addRow("", self.show_border)
        page_form.addRow("رنگ اصلی", self._color_row(self.accent_color_button, self.accent_swatch))
        page_form.addRow("رنگ قاب", self._color_row(self.border_color_button, self.border_swatch))
        editor_layout.addWidget(page_card)

        layout_card = QFrame()
        layout_card.setObjectName("Card")
        layout_form = QVBoxLayout(layout_card)
        layout_form.setContentsMargins(14, 14, 14, 14)
        layout_form.setSpacing(8)
        block_title = QLabel("ترتیب و جای بلوک‌ها")
        block_title.setObjectName("PageTitle")
        block_hint = QLabel("با ماوس یا لمس، بلوک‌ها را جابه‌جا کنید. سپس بلوک را انتخاب و ستون و تراز آن را تغییر دهید.")
        block_hint.setObjectName("PageSubtitle")
        block_hint.setWordWrap(True)
        layout_form.addWidget(block_title)
        layout_form.addWidget(block_hint)
        self.layout_order_list = QListWidget()
        self.layout_order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.layout_order_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.layout_order_list.setMinimumHeight(170)
        for key in DEFAULT_TEMPLATE["layout_order"]:
            item = QListWidgetItem(BLOCK_LABELS[key])
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.layout_order_list.addItem(item)
        self.layout_order_list.setCurrentRow(0)
        layout_form.addWidget(self.layout_order_list)

        block_picker_form = QFormLayout()
        self.block_picker = QComboBox()
        for key, label in BLOCK_LABELS.items():
            self.block_picker.addItem(label, key)
        self.block_column = QComboBox()
        for label, value in COLUMN_LABELS:
            self.block_column.addItem(label, value)
        self.block_align = QComboBox()
        for label, value in ALIGN_LABELS:
            self.block_align.addItem(label, value)
        block_picker_form.addRow("بلوک تنظیم‌شونده", self.block_picker)
        block_picker_form.addRow("جایگاه", self.block_column)
        block_picker_form.addRow("تراز متن", self.block_align)
        layout_form.addLayout(block_picker_form)
        editor_layout.addWidget(layout_card)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(14, 14, 14, 14)
        table_layout.setSpacing(8)
        table_title = QLabel("تراز ستون‌های جدول کالا")
        table_title.setObjectName("PageTitle")
        table_layout.addWidget(table_title)
        table_form = QFormLayout()
        self.table_alignment_inputs = {}
        for key, label in TABLE_COLUMN_LABELS.items():
            combo = QComboBox()
            for align_label, value in ALIGN_LABELS:
                combo.addItem(align_label, value)
            combo.currentIndexChanged.connect(self._table_alignment_changed)
            self.table_alignment_inputs[key] = combo
            table_form.addRow(label, combo)
        table_layout.addLayout(table_form)
        editor_layout.addWidget(table_card)

        self.save_button = QPushButton("ذخیره قالب در سرور")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setMinimumHeight(44)
        self.save_button.clicked.connect(self.save_template)
        editor_layout.addWidget(self.save_button)
        editor_scroll.setWidget(editor)
        splitter.addWidget(editor_scroll)

        preview_card = QFrame()
        preview_card.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_title = QLabel("پیش‌نمایش چاپ")
        preview_title.setObjectName("PageTitle")
        preview_layout.addWidget(preview_title)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setStyleSheet("QTextBrowser { background:#FFFFFF; color:#182235; border:1px solid #CBD5E1; }")
        preview_layout.addWidget(self.preview, 1)
        splitter.addWidget(preview_card)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        for field in (self.company_name, self.legal_id, self.phone):
            field.textChanged.connect(self.update_preview)
        self.address.textChanged.connect(self.update_preview)
        self.footer.textChanged.connect(self.update_preview)
        for control in (self.paper_size, self.orientation, self.margin_mm):
            control.currentIndexChanged.connect(self.update_preview) if isinstance(control, QComboBox) else control.valueChanged.connect(self.update_preview)
        self.show_border.toggled.connect(self.update_preview)
        self.layout_order_list.model().rowsMoved.connect(self.update_preview)
        self.layout_order_list.currentRowChanged.connect(self._layout_block_selected)
        self.block_picker.currentIndexChanged.connect(self._block_picker_changed)
        self.block_column.currentIndexChanged.connect(self._block_setting_changed)
        self.block_align.currentIndexChanged.connect(self._block_setting_changed)
        self._load_template(dict(DEFAULT_TEMPLATE))
        self.set_permissions(window.current_user)

    @staticmethod
    def _color_row(button, swatch):
        row = QHBoxLayout()
        row.addWidget(button, 1)
        row.addWidget(swatch)
        return row

    def _pick_color(self, target):
        current = self.accent_color_value if target == "accent" else self.frame_border_color_value
        chosen = QColorDialog.getColor(QColor(current), self, "انتخاب رنگ")
        if not chosen.isValid():
            return
        color = chosen.name().upper()
        if target == "accent":
            self.accent_color_value = color
            self.accent_swatch.setStyleSheet("background:{};border:1px solid #9AA9BB;border-radius:4px;".format(color))
        else:
            self.frame_border_color_value = color
            self.border_swatch.setStyleSheet("background:{};border:1px solid #9AA9BB;border-radius:4px;".format(color))
        self.update_preview()

    def set_permissions(self, user):
        self.save_button.setVisible(can_access(user, "invoices", "update"))
        self.refresh_button.setVisible(can_access(user, "invoices", "read"))

    def refresh(self):
        if self.window.api and can_access(self.window.current_user, "invoices", "read"):
            self.window.run_api(
                self.window.api.get_invoice_template,
                self._load_template,
                failure=lambda error: self.window.show_error(error),
                busy=self.refresh_button,
            )

    def _load_template(self, values):
        values = dict(DEFAULT_TEMPLATE, **(values or {}))
        self._loading = True
        for field, value in (
            (self.company_name, values.get("company_name", "")),
            (self.legal_id, values.get("legal_id", "")),
            (self.phone, values.get("phone", "")),
        ):
            field.setText(str(value))
        self.address.setPlainText(str(values.get("address", "")))
        self.footer.setPlainText(str(values.get("footer", "")))
        self.paper_size.setCurrentIndex(max(0, self.paper_size.findData(values.get("paper_size", "A4"))))
        self.orientation.setCurrentIndex(max(0, self.orientation.findData(values.get("orientation", "portrait"))))
        self.margin_mm.setValue(int(values.get("margin_mm", 12)))
        self.show_border.setChecked(bool(values.get("show_border", True)))
        self.accent_color_value = str(values.get("accent_color", "#3157A4"))
        self.frame_border_color_value = str(values.get("frame_border_color", "#CBD5E1"))
        self.accent_swatch.setStyleSheet("background:{};border:1px solid #9AA9BB;border-radius:4px;".format(self.accent_color_value))
        self.border_swatch.setStyleSheet("background:{};border:1px solid #9AA9BB;border-radius:4px;".format(self.frame_border_color_value))
        self.block_settings = dict(DEFAULT_TEMPLATE["block_settings"])
        self.block_settings.update(values.get("block_settings") or {})
        self.table_alignment = dict(DEFAULT_TEMPLATE["table_alignment"])
        self.table_alignment.update(values.get("table_alignment") or {})
        order = values.get("layout_order") or list(DEFAULT_TEMPLATE["layout_order"])
        self.layout_order_list.clear()
        seen = set()
        for key in order + [key for key in BLOCK_LABELS if key not in order]:
            if key not in BLOCK_LABELS or key in seen:
                continue
            seen.add(key)
            item = QListWidgetItem(BLOCK_LABELS[key])
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.layout_order_list.addItem(item)
        for key, combo in self.table_alignment_inputs.items():
            combo.setCurrentIndex(max(0, combo.findData(self.table_alignment.get(key, "right"))))
        self.block_picker.setCurrentIndex(0)
        self._loading = False
        selected_key = self.block_picker.currentData() or "company"
        self._load_block_settings(selected_key)
        self.update_preview()

    def _load_block_settings(self, key):
        if self._loading or key not in BLOCK_LABELS:
            return
        settings = self.block_settings.get(key, {"column": "full", "align": "right"})
        self.block_column.blockSignals(True)
        self.block_align.blockSignals(True)
        self.block_column.setCurrentIndex(max(0, self.block_column.findData(settings.get("column", "full"))))
        self.block_align.setCurrentIndex(max(0, self.block_align.findData(settings.get("align", "right"))))
        self.block_column.blockSignals(False)
        self.block_align.blockSignals(False)

    def _layout_block_selected(self, row):
        if self._loading or row < 0 or row >= self.layout_order_list.count():
            return
        key = self.layout_order_list.item(row).data(Qt.ItemDataRole.UserRole)
        idx = self.block_picker.findData(key)
        if idx >= 0 and self.block_picker.currentIndex() != idx:
            self.block_picker.blockSignals(True)
            self.block_picker.setCurrentIndex(idx)
            self.block_picker.blockSignals(False)
        self._load_block_settings(key)

    def _block_picker_changed(self, *_args):
        if self._loading:
            return
        key = self.block_picker.currentData()
        for row in range(self.layout_order_list.count()):
            if self.layout_order_list.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.layout_order_list.blockSignals(True)
                self.layout_order_list.setCurrentRow(row)
                self.layout_order_list.blockSignals(False)
                break
        self._load_block_settings(key)

    def _block_setting_changed(self, *_args):
        if self._loading:
            return
        key = self.block_picker.currentData()
        if key:
            self.block_settings[key] = {
                "column": self.block_column.currentData(),
                "align": self.block_align.currentData(),
            }
        self.update_preview()

    def _table_alignment_changed(self, *_args):
        if self._loading:
            return
        for key, combo in self.table_alignment_inputs.items():
            self.table_alignment[key] = combo.currentData()
        self.update_preview()

    def _values(self):
        order = []
        for row in range(self.layout_order_list.count()):
            order.append(self.layout_order_list.item(row).data(Qt.ItemDataRole.UserRole))
        return {
            "company_name": self.company_name.text().strip(),
            "legal_id": self.legal_id.text().strip(),
            "address": self.address.toPlainText().strip(),
            "phone": self.phone.text().strip(),
            "footer": self.footer.toPlainText().strip(),
            "paper_size": self.paper_size.currentData() or "A4",
            "orientation": self.orientation.currentData() or "portrait",
            "margin_mm": self.margin_mm.value(),
            "accent_color": self.accent_color_value,
            "show_border": self.show_border.isChecked(),
            "frame_border_color": self.frame_border_color_value,
            "layout_order": order,
            "block_settings": dict(self.block_settings),
            "table_alignment": dict(self.table_alignment),
        }

    def update_preview(self, *_args):
        if not hasattr(self, "preview"):
            return
        sample = {
            "id": "preview", "day_receipt_id": "۱۰۰۱", "created_at": "2026-10-28T12:00:00",
            "payed": True, "total_price": 1285000,
            "items": [
                {"product_name": "نمونه کالا", "quantity": 2, "sell_price": 450000},
                {"product_name": "کالای دوم", "quantity": 1, "sell_price": 385000},
            ],
        }
        self.preview.setHtml(render_invoice_html(sample, self._values()))

    def save_template(self):
        values = self._values()
        if not values["company_name"]:
            self.window.show_error("نام کسب‌وکار نباید خالی باشد.")
            return
        if not self.window.api:
            self.window.show_error("اتصال سرور برقرار نیست.")
            return
        self.window.run_api(
            lambda: self.window.api.save_invoice_template(**values),
            self._saved,
            busy=self.save_button,
        )

    def _saved(self, values):
        self._load_template(values)
        self.window.set_status("قالب فاکتور روی سرور ذخیره شد.")
        QMessageBox.information(self, "ذخیره شد", "چیدمان جدید در پیش‌نمایش، PDF و چاپ فروش استفاده می‌شود.")
