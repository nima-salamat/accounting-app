"""Receipt-linked refund entry dialog and searchable return history."""
import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QHeaderView, QDateEdit,
)

from client.ui.permissions import can_access
from client.ui.currency import format_currency
from client.ui.invoice_dialog import InvoiceDialog


REFUND_METHODS = {
    "cash": "نقدی",
    "card": "کارت بانکی (ثبت دستی)",
    "bank_transfer": "واریز بانکی (ثبت دستی)",
    "store_credit": "اعتبار فروشگاه",
}


class ReturnDialog(QDialog):
    """Create a partial return against an existing receipt line-by-line."""

    def __init__(self, receipt, parent=None):
        super().__init__(parent)
        self.receipt = receipt
        self.setWindowTitle("مرجوعی و استرداد کالا")
        self.setMinimumSize(820, 580)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("ثبت مرجوعی از فاکتور")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "فاکتور روزانهٔ {} · مبلغ اصلی {}".format(
                receipt.get("day_receipt_id", "—"), format_currency(receipt.get("total_price"))
            )
        )
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box, 1)
        root.addLayout(heading)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "شناسه", "کالا", "خرید", "مرجوع شده", "قابل مرجوعی", "تعداد مرجوعی",
        ])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)
        self.quantity_inputs = {}
        for row, item in enumerate(receipt.get("items") or []):
            remaining = int(item.get("returnable_quantity", item.get("quantity", 0)) or 0)
            returned = int(item.get("returned_quantity", 0) or 0)
            self.table.insertRow(row)
            values = [
                item.get("id"),
                item.get("product_name") or "کالای حذف‌شده",
                item.get("quantity", 0),
                returned,
                remaining,
                "",
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value if value is not None else "—"))
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row, col, cell)
            quantity = QSpinBox()
            quantity.setRange(0, max(0, remaining))
            quantity.setValue(0)
            quantity.setMinimumHeight(38)
            quantity.valueChanged.connect(self.update_total)
            self.table.setCellWidget(row, 5, quantity)
            self.quantity_inputs[str(item.get("id"))] = (item, quantity)
        details = QHBoxLayout()
        self.reason = QComboBox()
        self.reason.addItem("کالای نامناسب", "customer_return")
        self.reason.addItem("کالای معیوب", "damaged")
        self.reason.addItem("کالای اشتباه", "wrong_item")
        self.reason.addItem("تاریخ انقضا", "expired")
        self.reason.addItem("سایر", "other")
        self.refund_method = QComboBox()
        for key, label in REFUND_METHODS.items():
            self.refund_method.addItem(label, key)
        details.addWidget(QLabel("علت"))
        details.addWidget(self.reason, 1)
        details.addWidget(QLabel("روش استرداد"))
        details.addWidget(self.refund_method, 1)
        root.addLayout(details)

        self.notes = QTextEdit()
        self.notes.setPlaceholderText("توضیح، شماره رسید مرجوعی فیزیکی یا علت استثنا (اختیاری)")
        self.notes.setFixedHeight(64)
        root.addWidget(self.notes)
        self.warning = QLabel(
            "این عملیات رسید مرجوعی، محدودیت تعداد و گردش موجودی را ثبت می‌کند. "
            "واریز بانکی یا برگشت واقعی تراکنش کارت‌خوان در این برنامه اجرا نمی‌شود و باید در دستگاه/بانک انجام شود."
        )
        self.warning.setObjectName("StatusPill")
        self.warning.setWordWrap(True)
        root.addWidget(self.warning)
        footer = QHBoxLayout()
        self.total_label = QLabel("مبلغ قابل استرداد: ۰")
        self.total_label.setObjectName("MetricValue")
        footer.addWidget(self.total_label, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ثبت مرجوعی")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        root.addLayout(footer)
        self.update_total()

    def selected_items(self):
        return [
            {"original_line_id": item.get("id"), "quantity": quantity.value()}
            for item, quantity in self.quantity_inputs.values()
            if quantity.value() > 0
        ]

    def update_total(self, *_args):
        total = 0.0
        for item, quantity in self.quantity_inputs.values():
            total += float(item.get("sell_price") or 0) * quantity.value()
        self.total_label.setText("مبلغ قابل استرداد: {}".format(format_currency(total)))

    def _validate(self):
        if not self.selected_items():
            QMessageBox.warning(self, "مرجوعی خالی", "حداقل یک ردیف با تعداد مثبت انتخاب کنید.")
            return
        self.accept()

    def values(self):
        return {
            "items": self.selected_items(),
            "refund_method": self.refund_method.currentData(),
            "reason": self.reason.currentData(),
            "notes": self.notes.toPlainText().strip() or None,
        }


class ReturnsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.rows = []
        self.page = 1
        self.page_size = 25
        self.total = 0
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("مرجوعی‌ها و استردادها")
        title.setObjectName("PageTitle")
        subtitle = QLabel("هر سند به فاکتور اصلی وصل است؛ تعداد تکراری بیش از خرید مجاز نیست.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.detail_button = QPushButton("جزئیات سند")
        self.detail_button.clicked.connect(self.show_detail)
        self.print_button = QPushButton("چاپ رسید")
        self.print_button.clicked.connect(self.print_document)
        header.addWidget(self.refresh_button)
        header.addWidget(self.detail_button)
        header.addWidget(self.print_button)
        root.addLayout(header)

        filters = QVBoxLayout()
        search_row = QHBoxLayout()
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("جست‌وجوی شماره فاکتور، شناسه، کارمند یا مبلغ…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.apply_filters)
        search_row.addWidget(self.search_input, 2)

        self.refund_method_filter = QComboBox(self)
        self.refund_method_filter.addItem("همهٔ روش‌های استرداد", "all")
        for key, label in REFUND_METHODS.items():
            self.refund_method_filter.addItem(label, key)
        search_row.addWidget(self.refund_method_filter)
        self.sort_combo = QComboBox(self)
        for label, value in (
            ("جدیدترین", "created_at:desc"),
            ("قدیمی‌ترین", "created_at:asc"),
            ("مبلغ: نزولی", "total_amount:desc"),
            ("مبلغ: صعودی", "total_amount:asc"),
            ("شماره فاکتور: نزولی", "day_receipt_id:desc"),
            ("شماره فاکتور: صعودی", "day_receipt_id:asc"),
            ("کارمند: الف تا ی", "operator_name:asc"),
            ("کارمند: ی تا الف", "operator_name:desc"),
        ):
            self.sort_combo.addItem(label, value)
        search_row.addWidget(self.sort_combo, 1)
        filters.addLayout(search_row)

        date_row = QHBoxLayout()
        self.start_date_enabled = QCheckBox("از تاریخ", self)
        self.start_date_edit = QDateEdit(self)
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setEnabled(False)
        self.start_date_enabled.toggled.connect(self.start_date_edit.setEnabled)
        date_row.addWidget(self.start_date_enabled)
        date_row.addWidget(self.start_date_edit)

        self.end_date_enabled = QCheckBox("تا تاریخ", self)
        self.end_date_edit = QDateEdit(self)
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setEnabled(False)
        self.end_date_enabled.toggled.connect(self.end_date_edit.setEnabled)
        date_row.addWidget(self.end_date_enabled)
        date_row.addWidget(self.end_date_edit)
        date_row.addStretch(1)

        self.apply_filter_button = QPushButton("اعمال فیلتر", self)
        self.apply_filter_button.clicked.connect(self.apply_filters)
        self.clear_filter_button = QPushButton("پاک‌کردن", self)
        self.clear_filter_button.clicked.connect(self.clear_filters)
        date_row.addWidget(self.apply_filter_button)
        date_row.addWidget(self.clear_filter_button)
        filters.addLayout(date_row)
        root.addLayout(filters)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["شناسه", "فاکتور اصلی", "تاریخ", "کارمند", "روش استرداد", "مبلغ"])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.page_label = QLabel("صفحه ۱ از ۱")
        self.page_label.setObjectName("PageSubtitle")
        self.previous_button = QPushButton("صفحهٔ قبل")
        self.next_button = QPushButton("صفحهٔ بعد")
        self.previous_button.clicked.connect(lambda: self._move(-1))
        self.next_button.clicked.connect(lambda: self._move(1))
        pager.addWidget(self.page_label)
        pager.addStretch(1)
        pager.addWidget(self.previous_button)
        pager.addWidget(self.next_button)
        root.addLayout(pager)

    def set_permissions(self, user):
        self.refresh_button.setVisible(can_access(user, "returns", "read"))
        self.detail_button.setVisible(can_access(user, "returns", "read"))
        self.print_button.setVisible(can_access(user, "returns", "read"))

    def refresh(self):
        if not self.window.api or not can_access(self.window.current_user, "returns", "read"):
            return
        sort_by, sort_order = str(self.sort_combo.currentData() or "created_at:desc").split(":", 1)
        self.window.run_api(
            lambda: self.window.api.list_returns_page(
                q=self.search_input.text().strip() or None,
                refund_method=self.refund_method_filter.currentData(),
                start_date=(
                    self.start_date_edit.date().toString("yyyy-MM-dd")
                    if self.start_date_enabled.isChecked() else None
                ),
                end_date=(
                    self.end_date_edit.date().toString("yyyy-MM-dd")
                    if self.end_date_enabled.isChecked() else None
                ),
                sort_by=sort_by, sort_order=sort_order,
                page=self.page, page_size=self.page_size,
            ),
            self.populate,
            busy=self.refresh_button,
        )

    def apply_filters(self, *_args):
        self.page = 1
        self.refresh()

    def clear_filters(self, *_args):
        self.search_input.clear()
        self.refund_method_filter.setCurrentIndex(0)
        self.start_date_enabled.setChecked(False)
        self.end_date_enabled.setChecked(False)
        self.sort_combo.setCurrentIndex(0)
        self.page = 1
        self.refresh()

    def populate(self, payload):
        self.rows = list(payload.get("items") or [])
        self.page = int(payload.get("page", self.page))
        self.page_size = int(payload.get("page_size", self.page_size))
        self.total = int(payload.get("total", len(self.rows)))
        self.table.setRowCount(0)
        for row, item in enumerate(self.rows):
            self.table.insertRow(row)
            values = [
                item.get("id"),
                "شمارهٔ {}".format(item.get("day_receipt_id", "—")),
                item.get("created_at", "—"),
                item.get("operator_name", "—"),
                REFUND_METHODS.get(item.get("refund_method"), item.get("refund_method", "—")),
                format_currency(item.get("total_amount")),
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value or "—"))
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row, col, cell)
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page_label.setText("صفحه {} از {} · {} سند".format(self.page, pages, self.total))
        self.previous_button.setEnabled(self.page > 1)
        self.next_button.setEnabled(self.page < pages)

    def _move(self, delta):
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        if 1 <= self.page + delta <= pages:
            self.page += delta
            self.refresh()

    def _selected(self):
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def print_document(self):
        selected = self._selected()
        if not selected:
            self.window.show_error("ابتدا یک سند مرجوعی را انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_return(selected["id"]),
            self._load_return_for_print,
        )

    def _load_return_for_print(self, document):
        items = [
            {
                "product_name": line.get("product_name") or "کالای حذف‌شده",
                "quantity": line.get("quantity", 0),
                "sell_price": line.get("unit_price", 0),
            }
            for line in document.get("items") or []
        ]
        receipt = {
            "id": document.get("id"),
            "day_receipt_id": "م-" + str(document.get("id") or "")[:8],
            "created_at": document.get("created_at"),
            "payed": True,
            "total_price": document.get("total_amount", 0),
            "items": items,
            "seat_number": "",
        }
        self.window.run_api(
            lambda: self.window.api.get_invoice_template(kind="return_slip"),
            lambda template: InvoiceDialog(receipt, template, self).exec(),
        )

    def show_detail(self):
        selected = self._selected()
        if not selected:
            self.window.show_error("ابتدا یک سند مرجوعی را انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_return(selected["id"]),
            self._show_detail_payload,
        )

    def _show_detail_payload(self, item):
        lines = [
            "مرجوعی از فاکتور روزانهٔ {}".format(item.get("day_receipt_id", "—")),
            "روش ثبت استرداد: {}".format(REFUND_METHODS.get(item.get("refund_method"), "—")),
            "مبلغ کل: {}".format(format_currency(item.get("total_amount"))),
            "علت: {}".format(item.get("reason", "—")),
            "",
        ]
        for row in item.get("items") or []:
            lines.append("{} × {} · {}".format(
                row.get("product_name", "کالا"), row.get("quantity", 0),
                format_currency(row.get("line_total")),
            ))
        if item.get("notes"):
            lines.extend(["", "یادداشت: " + item["notes"]])
        QMessageBox.information(self, "جزئیات مرجوعی", "\n".join(lines))
