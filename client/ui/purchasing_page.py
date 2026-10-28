"""Accountant workspace for supplier invoices, partner records, and expenses."""
from decimal import Decimal

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QHeaderView,
)

from client.ui.forms import RecordDialog
from client.ui.permissions import can_access
from client.ui.invoice_dialog import InvoiceDialog


def _table(parent, headers, hidden_first=False):
    table = QTableWidget(0, len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    if hidden_first:
        table.setColumnHidden(0, True)
    return table


def _set_rows(table, rows, keys):
    table.setRowCount(0)
    for row, data in enumerate(rows):
        table.insertRow(row)
        for col, key in enumerate(keys):
            value = data.get(key, "—")
            cell = QTableWidgetItem(str(value if value not in (None, "") else "—"))
            if col == 0:
                cell.setData(Qt.ItemDataRole.UserRole, data)
            table.setItem(row, col, cell)


def _currency(value):
    try:
        return "{:,.2f}".format(float(value or 0))
    except (TypeError, ValueError):
        return "0.00"


class PurchaseInvoiceDialog(QDialog):
    def __init__(self, suppliers, products, parent=None):
        super().__init__(parent)
        self.suppliers = list(suppliers or [])
        self.products = list(products or [])
        self.rows = []
        self.setWindowTitle("ثبت فاکتور خرید تأمین‌کننده")
        self.resize(1040, 700)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        title = QLabel("ورود فاکتور خرید")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "بهای هر ردیف روی همین فاکتور نگهداری می‌شود. دریافت کالای رهگیری‌شده، موجودی را افزایش می‌دهد "
            "و بهای تمام‌شده را با روش میانگین موزون به‌روز می‌کند."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        meta = QFrame()
        meta.setObjectName("Card")
        form = QFormLayout(meta)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)
        self.supplier = QComboBox()
        self.supplier.setMinimumHeight(38)
        for item in self.suppliers:
            self.supplier.addItem(
                "{}{}".format(item.get("name", "—"), " · {}".format(item.get("phone")) if item.get("phone") else ""),
                item.get("id"),
            )
        self.invoice_number = QLineEdit()
        self.invoice_number.setPlaceholderText("شماره فاکتور روی سند تأمین‌کننده")
        self.invoice_date = QDateEdit(QDate.currentDate())
        self.invoice_date.setCalendarPopup(True)
        self.invoice_date.setDisplayFormat("yyyy-MM-dd")
        self.has_due_date = QComboBox()
        self.has_due_date.addItem("بدون سررسید", False)
        self.has_due_date.addItem("دارای سررسید", True)
        self.due_date = QDateEdit(QDate.currentDate())
        self.due_date.setCalendarPopup(True)
        self.due_date.setDisplayFormat("yyyy-MM-dd")
        self.due_date.setEnabled(False)
        self.has_due_date.currentIndexChanged.connect(
            lambda _index: self.due_date.setEnabled(bool(self.has_due_date.currentData()))
        )
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("یادداشت اختیاری")
        form.addRow("تأمین‌کننده", self.supplier)
        form.addRow("شماره فاکتور", self.invoice_number)
        form.addRow("تاریخ فاکتور", self.invoice_date)
        due_row = QHBoxLayout()
        due_row.addWidget(self.has_due_date)
        due_row.addWidget(self.due_date, 1)
        form.addRow("سررسید", due_row)
        form.addRow("یادداشت", self.notes)
        root.addWidget(meta)

        self.items_table = QTableWidget(0, 5)
        self.items_table.setHorizontalHeaderLabels(["کالا (اختیاری)", "شرح قلم", "تعداد", "بهای واحد", "جمع ردیف"])
        self.items_table.setAlternatingRowColors(True)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.items_table, 1)

        line_tools = QHBoxLayout()
        self.add_line_button = QPushButton("افزودن ردیف +")
        self.add_line_button.clicked.connect(self.add_line)
        self.remove_line_button = QPushButton("حذف ردیف انتخاب‌شده")
        self.remove_line_button.clicked.connect(self.remove_line)
        self.total_label = QLabel("جمع فاکتور: ۰")
        self.total_label.setObjectName("MetricValue")
        line_tools.addWidget(self.add_line_button)
        line_tools.addWidget(self.remove_line_button)
        line_tools.addStretch(1)
        line_tools.addWidget(self.total_label)
        root.addLayout(line_tools)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ثبت فاکتور و موجودی")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.add_line()

    def add_line(self):
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        product = QComboBox()
        product.addItem("قلم دستی / غیرانبارشده", None)
        for item in self.products:
            product.addItem(
                "{} · بهای فعلی {}".format(item.get("name", "کالا"), _currency(item.get("buy_price"))),
                item.get("id"),
            )
        description = QLineEdit()
        description.setPlaceholderText("شرح قلم، فقط اگر کالای کاتالوگ نیست")
        quantity = QDoubleSpinBox()
        quantity.setRange(0.0001, 999999999)
        quantity.setDecimals(4)
        quantity.setValue(1)
        cost = QDoubleSpinBox()
        cost.setRange(0, 999999999999.99)
        cost.setDecimals(2)
        cost.setSingleStep(1)
        total = QLabel("0.00")
        total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        product.currentIndexChanged.connect(
            lambda _idx, combo=product, name=description: self._product_changed(combo, name)
        )
        quantity.valueChanged.connect(lambda _value: self._refresh_total())
        cost.valueChanged.connect(lambda _value: self._refresh_total())
        self.items_table.setCellWidget(row, 0, product)
        self.items_table.setCellWidget(row, 1, description)
        self.items_table.setCellWidget(row, 2, quantity)
        self.items_table.setCellWidget(row, 3, cost)
        self.items_table.setCellWidget(row, 4, total)
        self.rows.append({"product": product, "description": description, "quantity": quantity, "cost": cost, "total": total})
        self._refresh_total()

    @staticmethod
    def _product_changed(combo, description):
        # Product identity is sent separately; description stays available for package/batch notes.
        if combo.currentData() is None:
            description.setPlaceholderText("شرح قلم دستی (الزامی)")
        else:
            description.setPlaceholderText("شرح تکمیلی / بسته‌بندی (اختیاری)")
        description.setReadOnly(False)

    def _refresh_total(self):
        grand = Decimal("0")
        for row_index, line in enumerate(self.rows):
            value = Decimal(str(line["quantity"].value())) * Decimal(str(line["cost"].value()))
            grand += value
            line["total"].setText(_currency(value))
        self.total_label.setText("جمع فاکتور: {}".format(_currency(grand)))

    def remove_line(self):
        row = self.items_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "انتخاب ردیف", "ابتدا ردیف موردنظر را انتخاب کنید.")
            return
        if len(self.rows) <= 1:
            QMessageBox.information(self, "حداقل یک ردیف", "فاکتور باید حداقل یک ردیف داشته باشد.")
            return
        self.items_table.removeRow(row)
        self.rows.pop(row)
        self._refresh_total()

    def _validate(self):
        if not self.suppliers:
            QMessageBox.warning(self, "تأمین‌کننده", "ابتدا یک تأمین‌کنندهٔ فعال بسازید.")
            return
        if len(self.invoice_number.text().strip()) < 1:
            QMessageBox.warning(self, "شماره فاکتور", "شمارهٔ فاکتور الزامی است.")
            return
        try:
            self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "فاکتور ناقص", str(exc))
            return
        self.accept()

    def values(self):
        items = []
        for index, line in enumerate(self.rows, 1):
            product_id = line["product"].currentData()
            description = line["description"].text().strip()
            quantity = line["quantity"].value()
            unit_cost = line["cost"].value()
            if product_id is None and len(description) < 2:
                raise ValueError("در ردیف {} که کالای کاتالوگ ندارد، شرح قلم را وارد کنید.".format(index))
            if quantity <= 0:
                raise ValueError("تعداد ردیف {} باید مثبت باشد.".format(index))
            items.append({
                "product_id": product_id,
                "description": description,
                "quantity": quantity,
                "unit_cost": unit_cost,
            })
        due_date = self.due_date.date().toString("yyyy-MM-dd") if self.has_due_date.currentData() else None
        return {
            "supplier_id": self.supplier.currentData(),
            "invoice_number": self.invoice_number.text().strip(),
            "invoice_date": self.invoice_date.date().toString("yyyy-MM-dd"),
            "due_date": due_date,
            "items": items,
            "notes": self.notes.text().strip() or None,
        }


class PurchasePaymentDialog(QDialog):
    def __init__(self, invoice, parent=None):
        super().__init__(parent)
        self.invoice = invoice
        self.setWindowTitle("ثبت پرداخت فاکتور خرید")
        self.setMinimumWidth(470)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        title = QLabel("پرداخت به {}".format(invoice.get("supplier_name", "تأمین‌کننده")))
        title.setObjectName("PageTitle")
        root.addWidget(title)
        total = Decimal(str(invoice.get("total_amount") or 0))
        paid = Decimal(str(invoice.get("paid_amount") or 0))
        info = QLabel("شماره: {} · مانده: {}".format(invoice.get("invoice_number"), _currency(total - paid)))
        info.setObjectName("StatusPill")
        root.addWidget(info)
        form = QFormLayout()
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.01, max(0.01, float(total - paid)))
        self.amount.setDecimals(2)
        self.amount.setValue(float(total - paid))
        self.paid_on = QDateEdit(QDate.currentDate())
        self.paid_on.setCalendarPopup(True)
        self.paid_on.setDisplayFormat("yyyy-MM-dd")
        self.method = QComboBox()
        self.method.addItem("نقدی", "cash")
        self.method.addItem("کارت‌خوان / بانکی", "card")
        self.method.addItem("انتقال بانکی", "bank_transfer")
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("مرجع پرداخت (اختیاری)")
        self.notes = QLineEdit()
        form.addRow("مبلغ پرداخت", self.amount)
        form.addRow("تاریخ پرداخت", self.paid_on)
        form.addRow("روش پرداخت", self.method)
        form.addRow("مرجع", self.reference)
        form.addRow("یادداشت", self.notes)
        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ثبت پرداخت")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self):
        return {
            "amount": self.amount.value(),
            "paid_on": self.paid_on.date().toString("yyyy-MM-dd"),
            "payment_method": self.method.currentData(),
            "reference": self.reference.text().strip() or None,
            "notes": self.notes.text().strip() or None,
        }


class PartnersTab(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.items = []
        self.page = 1
        self.page_size = 25
        self.total = 0
        self.setObjectName("Card")
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("نام، تلفن، ایمیل یا شناسه مالیاتی…")
        self.search.returnPressed.connect(self.refresh)
        self.type_filter = QComboBox()
        self.type_filter.addItem("همه طرف‌حساب‌ها", None)
        self.type_filter.addItem("تأمین‌کنندگان", "supplier")
        self.type_filter.addItem("مشتریان", "customer")
        self.type_filter.currentIndexChanged.connect(self.refresh)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.create_supplier_button = QPushButton("تأمین‌کننده +")
        self.create_supplier_button.setObjectName("PrimaryButton")
        self.create_supplier_button.clicked.connect(lambda: self.create_partner("supplier"))
        self.create_customer_button = QPushButton("مشتری +")
        self.create_customer_button.clicked.connect(lambda: self.create_partner("customer"))
        for widget in (self.search, self.type_filter, self.refresh_button, self.create_supplier_button, self.create_customer_button):
            header.addWidget(widget)
        root.addLayout(header)
        self.table = _table(self, ["شناسه", "نوع", "نام", "تلفن", "ایمیل", "شناسه مالیاتی", "فعال"], True)
        root.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.page_label = QLabel("صفحه ۱ از ۱")
        self.previous = QPushButton("قبل"); self.next = QPushButton("بعد")
        self.previous.clicked.connect(lambda: self.move_page(-1))
        self.next.clicked.connect(lambda: self.move_page(1))
        pager.addWidget(self.page_label); pager.addStretch(1); pager.addWidget(self.previous); pager.addWidget(self.next)
        root.addLayout(pager)

    def set_permissions(self, user):
        self.refresh_button.setVisible(can_access(user, "partners", "read"))
        self.create_supplier_button.setVisible(can_access(user, "partners", "create"))
        self.create_customer_button.setVisible(can_access(user, "partners", "create"))

    def refresh(self, *_args):
        if self.window.api and can_access(self.window.current_user, "partners", "read"):
            self.window.run_api(
                lambda: self.window.api.list_partners_page(
                    q=self.search.text().strip() or None, partner_type=self.type_filter.currentData(),
                    page=self.page, page_size=self.page_size,
                ),
                self.populate, busy=self.refresh_button,
            )

    def populate(self, data):
        self.items = list(data.get("items") or [])
        self.page, self.page_size, self.total = int(data.get("page", self.page)), int(data.get("page_size", self.page_size)), int(data.get("total", len(self.items)))
        rows = []
        for item in self.items:
            rows.append({
                "id": item.get("id"), "partner_type": "تأمین‌کننده" if item.get("partner_type") == "supplier" else "مشتری",
                "name": item.get("name"), "phone": item.get("phone"), "email": item.get("email"),
                "tax_id": item.get("tax_id"), "is_active": "فعال" if item.get("is_active") else "غیرفعال",
            })
        _set_rows(self.table, rows, ["id", "partner_type", "name", "phone", "email", "tax_id", "is_active"])
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page_label.setText("صفحه {} از {} · {} طرف‌حساب".format(self.page, pages, self.total))
        self.previous.setEnabled(self.page > 1); self.next.setEnabled(self.page < pages)

    def move_page(self, delta):
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        if 1 <= self.page + delta <= pages:
            self.page += delta
            self.refresh()

    def create_partner(self, partner_type):
        specs = [
            {"key": "name", "label": "نام", "required": True},
            {"key": "phone", "label": "تلفن", "nullable": True},
            {"key": "email", "label": "ایمیل", "nullable": True},
            {"key": "tax_id", "label": "شناسه مالیاتی", "nullable": True},
            {"key": "address", "label": "نشانی", "nullable": True},
            {"key": "payment_terms", "label": "شرایط پرداخت", "nullable": True},
            {"key": "credit_limit", "label": "سقف اعتبار", "kind": "number", "default": 0},
            {"key": "is_active", "label": "فعال", "kind": "bool", "default": True},
            {"key": "notes", "label": "یادداشت", "nullable": True},
        ]
        dialog = RecordDialog("افزودن " + ("تأمین‌کننده" if partner_type == "supplier" else "مشتری"), specs, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        values["partner_type"] = partner_type
        self.window.run_api(
            lambda: self.window.api.create_partner(**values),
            lambda _result: self.refresh(),
            busy=self.create_supplier_button if partner_type == "supplier" else self.create_customer_button,
        )


class PurchaseInvoicesTab(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.items = []
        self.page = 1
        self.page_size = 25
        self.total = 0
        self.setObjectName("Card")
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("شماره فاکتور یا نام تأمین‌کننده…")
        self.search.returnPressed.connect(self.refresh)
        self.status_filter = QComboBox()
        self.status_filter.addItem("همه وضعیت‌ها", None)
        self.status_filter.addItem("پرداخت‌نشده", "posted")
        self.status_filter.addItem("پرداخت ناقص", "partial")
        self.status_filter.addItem("پرداخت کامل", "paid")
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.create_button = QPushButton("ثبت فاکتور خرید +")
        self.create_button.setObjectName("PrimaryButton")
        self.create_button.clicked.connect(self.create_invoice)
        self.detail_button = QPushButton("جزئیات")
        self.detail_button.clicked.connect(self.show_detail)
        self.print_button = QPushButton("چاپ سند")
        self.print_button.clicked.connect(self.print_document)
        self.payment_button = QPushButton("ثبت پرداخت")
        self.payment_button.clicked.connect(self.record_payment)
        for widget in (self.search, self.status_filter, self.refresh_button, self.create_button, self.detail_button, self.print_button, self.payment_button):
            header.addWidget(widget)
        root.addLayout(header)
        self.table = _table(self, ["شناسه", "شماره فاکتور", "تأمین‌کننده", "تاریخ", "جمع", "پرداخت‌شده", "مانده", "وضعیت"], True)
        root.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.page_label = QLabel("صفحه ۱ از ۱")
        self.previous = QPushButton("قبل"); self.next = QPushButton("بعد")
        self.previous.clicked.connect(lambda: self.move_page(-1))
        self.next.clicked.connect(lambda: self.move_page(1))
        pager.addWidget(self.page_label); pager.addStretch(1); pager.addWidget(self.previous); pager.addWidget(self.next)
        root.addLayout(pager)

    def set_permissions(self, user):
        self.refresh_button.setVisible(can_access(user, "purchase_invoices", "read"))
        self.detail_button.setVisible(can_access(user, "purchase_invoices", "read"))
        self.print_button.setVisible(can_access(user, "purchase_invoices", "read"))
        self.create_button.setVisible(can_access(user, "purchase_invoices", "create"))
        self.payment_button.setVisible(can_access(user, "purchase_invoices", "create"))

    def refresh(self, *_args):
        if self.window.api and can_access(self.window.current_user, "purchase_invoices", "read"):
            self.window.run_api(
                lambda: self.window.api.list_purchase_invoices_page(
                    q=self.search.text().strip() or None, status_filter=self.status_filter.currentData(),
                    page=self.page, page_size=self.page_size,
                ), self.populate, busy=self.refresh_button,
            )

    def populate(self, data):
        self.items = list(data.get("items") or [])
        self.page, self.page_size, self.total = int(data.get("page", self.page)), int(data.get("page_size", self.page_size)), int(data.get("total", len(self.items)))
        rows = []
        for item in self.items:
            rows.append({
                "id": item.get("id"), "invoice_number": item.get("invoice_number"),
                "supplier_name": item.get("supplier_name"), "invoice_date": item.get("invoice_date"),
                "total_amount": _currency(item.get("total_amount")), "paid_amount": _currency(item.get("paid_amount")),
                "outstanding_amount": _currency(item.get("outstanding_amount")),
                "status": {"posted": "پرداخت‌نشده", "partial": "پرداخت ناقص", "paid": "پرداخت کامل"}.get(item.get("status"), item.get("status")),
            })
        _set_rows(self.table, rows, ["id", "invoice_number", "supplier_name", "invoice_date", "total_amount", "paid_amount", "outstanding_amount", "status"])
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page_label.setText("صفحه {} از {} · {} فاکتور".format(self.page, pages, self.total))
        self.previous.setEnabled(self.page > 1); self.next.setEnabled(self.page < pages)

    def move_page(self, delta):
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        if 1 <= self.page + delta <= pages:
            self.page += delta
            self.refresh()

    def _selected(self):
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def _load_reference_data(self):
        suppliers = self.window.api.list_partners_page(partner_type="supplier", page=1, page_size=200)
        products = self.window.api.list_products_page(page=1, page_size=200)
        return {
            "suppliers": [item for item in suppliers.get("items", []) if item.get("is_active", True)],
            "products": products.get("items", []),
        }

    def create_invoice(self):
        if not can_access(self.window.current_user, "purchase_invoices", "create"):
            self.window.show_error("مجوز ثبت فاکتور خرید ندارید.")
            return
        self.window.run_api(self._load_reference_data, self._open_create_dialog, busy=self.create_button)

    def _open_create_dialog(self, data):
        if not data["suppliers"]:
            self.window.show_error("ابتدا از تب طرف‌حساب‌ها، یک تأمین‌کننده بسازید.")
            return
        dialog = PurchaseInvoiceDialog(data["suppliers"], data["products"], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.window.run_api(
            lambda: self.window.api.create_purchase_invoice(**values),
            self._created, busy=self.create_button,
        )

    def _created(self, result):
        self.window.set_status("فاکتور خرید {} ثبت شد؛ سند حسابداری و گردش موجودی ایجاد شد.".format(result.get("invoice_number")))
        self.refresh()
        page = getattr(self.window, "accounting_reports_page", None)
        if page:
            page.refresh()

    def print_document(self):
        item = self._selected()
        if not item:
            self.window.show_error("ابتدا یک فاکتور خرید را انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_purchase_invoice(item["id"]),
            self._load_purchase_for_print,
        )

    def _load_purchase_for_print(self, invoice):
        receipt = {
            "id": invoice.get("id"),
            "day_receipt_id": invoice.get("invoice_number") or str(invoice.get("id") or "")[:8],
            "created_at": invoice.get("invoice_date"),
            "payed": invoice.get("status") == "paid",
            "total_price": invoice.get("total_amount", 0),
            "items": [
                {
                    "product_name": line.get("product_name") or line.get("description") or "کالا",
                    "quantity": line.get("quantity", 0),
                    "sell_price": line.get("unit_cost", 0),
                }
                for line in invoice.get("items") or []
            ],
            "seat_number": invoice.get("supplier_name") or "",
        }
        self.window.run_api(
            lambda: self.window.api.get_invoice_template(kind="purchase_slip"),
            lambda template: self._show_purchase_print_preview(receipt, template),
        )

    def _show_purchase_print_preview(self, receipt, template):
        template = dict(template or {})
        for element in template.get("elements") or []:
            if element.get("type") == "seat_number":
                element["label"] = "تأمین‌کننده"
            elif element.get("type") == "payment_status":
                element["label"] = "وضعیت تسویه"
        InvoiceDialog(receipt, template, self).exec()

    def show_detail(self):
        item = self._selected()
        if not item:
            self.window.show_error("ابتدا یک فاکتور خرید را انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_purchase_invoice(item["id"]),
            self._show_detail_payload,
        )

    def _show_detail_payload(self, item):
        lines = [
            "شماره: {}".format(item.get("invoice_number")),
            "تأمین‌کننده: {}".format(item.get("supplier_name")),
            "تاریخ: {}".format(item.get("invoice_date")),
            "جمع: {}".format(_currency(item.get("total_amount"))),
            "پرداخت‌شده: {}".format(_currency(item.get("paid_amount"))),
            "مانده: {}".format(_currency(item.get("outstanding_amount"))),
            "", "اقلام:",
        ]
        for line in item.get("items") or []:
            lines.append("{} · {} × {} · جمع {}".format(
                line.get("product_name"), line.get("quantity"), _currency(line.get("unit_cost")),
                _currency(line.get("line_total")),
            ))
        if item.get("payments"):
            lines.extend(["", "پرداخت‌ها:"])
            for payment in item["payments"]:
                lines.append("{} · {} · {}".format(payment.get("paid_on"), _currency(payment.get("amount")), payment.get("payment_method")))
        QMessageBox.information(self, "جزئیات فاکتور خرید", "\n".join(lines))

    def record_payment(self):
        item = self._selected()
        if not item:
            self.window.show_error("ابتدا فاکتور خرید را انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_purchase_invoice(item["id"]),
            self._open_payment_dialog,
        )

    def _open_payment_dialog(self, invoice):
        if Decimal(str(invoice.get("outstanding_amount") or 0)) <= 0:
            QMessageBox.information(self, "پرداخت کامل", "این فاکتور قبلاً به‌طور کامل تسویه شده است.")
            return
        dialog = PurchasePaymentDialog(invoice, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.window.run_api(
            lambda: self.window.api.add_purchase_payment(invoice["id"], **values),
            lambda _result: self.refresh(),
            busy=self.payment_button,
        )


class ExpensesTab(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.items = []
        self.page = 1
        self.page_size = 25
        self.total = 0
        self.setObjectName("Card")
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("شرح، دسته هزینه یا مرجع…")
        self.search.returnPressed.connect(self.refresh)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.create_button = QPushButton("ثبت هزینه +")
        self.create_button.setObjectName("PrimaryButton")
        self.create_button.clicked.connect(self.create_expense)
        header.addWidget(self.search, 1); header.addWidget(self.refresh_button); header.addWidget(self.create_button)
        root.addLayout(header)
        self.table = _table(self, ["شناسه", "تاریخ", "شرح", "دسته", "حساب هزینه", "روش پرداخت", "مبلغ"], True)
        root.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.page_label = QLabel("صفحه ۱ از ۱")
        self.previous = QPushButton("قبل"); self.next = QPushButton("بعد")
        self.previous.clicked.connect(lambda: self.move_page(-1))
        self.next.clicked.connect(lambda: self.move_page(1))
        pager.addWidget(self.page_label); pager.addStretch(1); pager.addWidget(self.previous); pager.addWidget(self.next)
        root.addLayout(pager)

    def set_permissions(self, user):
        self.refresh_button.setVisible(can_access(user, "expenses", "read"))
        self.create_button.setVisible(can_access(user, "expenses", "create"))

    def refresh(self, *_args):
        if self.window.api and can_access(self.window.current_user, "expenses", "read"):
            self.window.run_api(lambda: self.window.api.list_expenses_page(
                q=self.search.text().strip() or None, page=self.page, page_size=self.page_size
            ), self.populate, busy=self.refresh_button)

    def populate(self, data):
        self.items = list(data.get("items") or [])
        self.page, self.page_size, self.total = int(data.get("page", self.page)), int(data.get("page_size", self.page_size)), int(data.get("total", len(self.items)))
        rows = [{
            "id": item.get("id"), "expense_date": item.get("expense_date"), "description": item.get("description"),
            "category": item.get("category"), "expense_account_name": item.get("expense_account_name"),
            "payment_method": item.get("payment_method"), "amount": _currency(item.get("amount")),
        } for item in self.items]
        _set_rows(self.table, rows, ["id", "expense_date", "description", "category", "expense_account_name", "payment_method", "amount"])
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page_label.setText("صفحه {} از {} · {} هزینه".format(self.page, pages, self.total))
        self.previous.setEnabled(self.page > 1); self.next.setEnabled(self.page < pages)

    def move_page(self, delta):
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        if 1 <= self.page + delta <= pages:
            self.page += delta
            self.refresh()

    def create_expense(self):
        if not can_access(self.window.current_user, "expenses", "create"):
            self.window.show_error("مجوز ثبت هزینه ندارید.")
            return
        self.window.run_api(self.window.api.list_accounts, self._open_expense_dialog)

    def _open_expense_dialog(self, accounts):
        choices = [(item.get("name"), item.get("id")) for item in accounts if item.get("account_type") == "expense" and item.get("is_active")]
        fields = [
            {"key": "description", "label": "شرح هزینه", "required": True},
            {"key": "category", "label": "دسته هزینه", "required": True, "default": "general"},
            {"key": "expense_date", "label": "تاریخ (YYYY-MM-DD)", "required": True, "default": QDate.currentDate().toString("yyyy-MM-dd")},
            {"key": "amount", "label": "مبلغ", "kind": "number", "required": True},
            {"key": "payment_method", "label": "روش پرداخت", "kind": "select", "required": True,
             "choices": [("نقدی", "cash"), ("کارت / بانکی", "card"), ("انتقال بانکی", "bank_transfer"), ("پرداخت‌نشده", "unpaid")]},
            {"key": "expense_account_id", "label": "حساب هزینه", "kind": "select", "nullable": True,
             "choices": [("پیش‌فرض هزینه‌های عملیاتی", None)] + choices},
            {"key": "reference", "label": "مرجع", "nullable": True},
            {"key": "notes", "label": "یادداشت", "nullable": True},
        ]
        dialog = RecordDialog("ثبت هزینه و سند حسابداری", fields, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            values = dialog.values()
        except ValueError as exc:
            self.window.show_error(exc)
            return
        self.window.run_api(lambda: self.window.api.create_expense(**values),
                            lambda _result: self.refresh(), busy=self.create_button)


class PurchasingPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("AppRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.tabs = QTabWidget()
        self.partners_page = PartnersTab(window)
        self.purchase_invoices_page = PurchaseInvoicesTab(window)
        self.expenses_page = ExpensesTab(window)
        self.tabs.addTab(self.purchase_invoices_page, "فاکتورهای خرید")
        self.tabs.addTab(self.partners_page, "تأمین‌کنندگان و مشتریان")
        self.tabs.addTab(self.expenses_page, "هزینه‌ها و پرداخت‌ها")
        root.addWidget(self.tabs)

    def set_permissions(self, user):
        self.purchase_invoices_page.set_permissions(user)
        self.partners_page.set_permissions(user)
        self.expenses_page.set_permissions(user)
        visible = [
            can_access(user, "purchase_invoices", "read"),
            can_access(user, "partners", "read"),
            can_access(user, "expenses", "read"),
        ]
        self.tabs.setTabVisible(0, visible[0] or can_access(user, "purchase_invoices", "create"))
        self.tabs.setTabVisible(1, visible[1] or can_access(user, "partners", "create"))
        self.tabs.setTabVisible(2, visible[2] or can_access(user, "expenses", "create"))

    def refresh(self):
        self.purchase_invoices_page.refresh()
        self.partners_page.refresh()
        self.expenses_page.refresh()
