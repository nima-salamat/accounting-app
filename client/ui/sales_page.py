"""API-driven point-of-sale screen with search, quantity selection, and idempotent checkout."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
import uuid

from client.payment_terminal import authorize_payment, void_payment
from client.ui.device_settings import device_settings
from client.ui.invoice_dialog import InvoiceDialog, auto_print_invoice
from client.ui.invoice_render import DEFAULT_TEMPLATE
from client.ui.permissions import can_access

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHeaderView,
)


class SalesPage(QFrame):
    def __init__(self,window):
        super().__init__()
        self.window = window
        self.products = []
        self.product_page = 1
        self.product_page_size = 50
        self.total_products = 0
        self._last_query = None
        self._loaded_product_page = 1
        self._cart = {}
        self._product_cache = {}
        self.setObjectName("Card");self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,18,18,18);layout.setSpacing(12)
        header=QHBoxLayout();title_box=QVBoxLayout()
        title=QLabel("فروش جدید");title.setObjectName("PageTitle")
        sub=QLabel("سبد خرید در کلاینت ساخته می‌شود؛ قیمت معتبر، جمع نهایی و ثبت اتمیک همیشه سمت سرور است.")
        sub.setObjectName("PageSubtitle");sub.setWordWrap(True)
        title_box.addWidget(title);title_box.addWidget(sub);header.addLayout(title_box,1)
        self.refresh_button=QPushButton("↻ کالاها")
        self.refresh_button.clicked.connect(self.refresh_products)
        header.addWidget(self.refresh_button)
        self.history_button=QPushButton("فاکتورهای اخیر")
        self.history_button.clicked.connect(self.show_recent_receipts)
        header.addWidget(self.history_button)
        layout.addLayout(header)
        filter_row=QHBoxLayout()
        self.search=QLineEdit();self.search.setPlaceholderText("جست‌وجوی کالا...")
        self.search.returnPressed.connect(self.refresh_products)
        self.search_button=QPushButton("جست‌وجو");self.search_button.clicked.connect(self.refresh_products)
        filter_row.addWidget(self.search,1);filter_row.addWidget(self.search_button);layout.addLayout(filter_row)

        self.table=QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(["شناسه","محصول","قیمت فروش","تعداد"])
        self.table.setColumnHidden(0,True);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True);self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.previous_page_button = QPushButton("صفحه قبل")
        self.previous_page_button.clicked.connect(lambda: self._change_product_page(-1))
        self.product_page_label = QLabel("صفحه 1 از 1")
        self.product_page_label.setObjectName("PageSubtitle")
        self.next_page_button = QPushButton("صفحه بعد")
        self.next_page_button.clicked.connect(lambda: self._change_product_page(1))
        self.cart_status_label = QLabel("سبد: ۰ قلم")
        self.cart_status_label.setObjectName("StatusPill")
        pager.addWidget(self.previous_page_button)
        pager.addWidget(self.product_page_label, 1)
        pager.addWidget(self.next_page_button)
        pager.addWidget(self.cart_status_label)
        layout.addLayout(pager)
        self.seat_row=QFrame()
        self.seat_row.setObjectName("Card")
        seat_layout=QHBoxLayout(self.seat_row)
        seat_layout.setContentsMargins(12,8,12,8)
        self.seat_label=QLabel("شماره صندلی / میز")
        self.seat_label.setObjectName("PageSubtitle")
        self.seat_number=QComboBox()
        self.seat_number.addItem("انتخاب صندلی…",None)
        for seat in range(1,31):
            self.seat_number.addItem("صندلی {}".format(seat),str(seat))
        seat_layout.addWidget(self.seat_label)
        seat_layout.addWidget(self.seat_number,1)
        self.seat_row.hide()
        layout.addWidget(self.seat_row)
        footer_card=QFrame();footer_card.setObjectName("Card")
        footer=QHBoxLayout(footer_card);footer.setContentsMargins(14,12,14,12)
        self.paid=QCheckBox("فاکتور پرداخت شده است")
        self.total_label=QLabel("مبلغ تخمینی: —")
        self.total_label.setObjectName("MetricValue")
        self.submit_button=QPushButton("ثبت امن فروش  ←")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.clicked.connect(self.checkout)
        footer.addWidget(self.paid);footer.addStretch(1);footer.addWidget(self.total_label);footer.addWidget(self.submit_button)
        layout.addWidget(footer_card)
        self.table.cellWidget if False else None
        self._business_profile = {}

    def set_permissions(self, user):
        self.history_button.setVisible(can_access(user, "receipts", "read"))

    def set_business_profile(self, profile):
        self._business_profile = dict(profile or {})
        self.seat_row.setVisible(
            self._business_profile.get("business_profile") == "cafe"
            or bool(self._business_profile.get("cafe_seat_selection"))
        )

    def refresh_products(self):
        """Fetch one server-paginated page instead of silently omitting later products."""
        if not self.window.api:
            return
        query = self.search.text().strip() or None
        if query != self._last_query:
            self._last_query = query
            self.product_page = 1
        self.window.run_api(
            lambda: self.window.api.list_products_page(
                q=query, page=self.product_page, page_size=self.product_page_size
            ),
            self.populate,
            failure=self._products_load_failed,
            busy=self.refresh_button,
        )

    def _update_pagination_controls(self):
        page_count = max(1, (self.total_products + self.product_page_size - 1) // self.product_page_size)
        self.product_page_label.setText(
            "صفحه {} از {} · {} کالا".format(self.product_page, page_count, self.total_products)
        )
        self.previous_page_button.setEnabled(self.product_page > 1)
        self.next_page_button.setEnabled(self.product_page < page_count)

    def _products_load_failed(self, error):
        self.product_page = self._loaded_product_page
        self.window.show_error(error)
        self._update_pagination_controls()

    def _change_product_page(self, delta):
        page_count = max(1, (self.total_products + self.product_page_size - 1) // self.product_page_size)
        target = self.product_page + int(delta)
        if 1 <= target <= page_count and target != self.product_page:
            self.product_page = target
            self.refresh_products()

    def populate(self, payload):
        if isinstance(payload, dict):
            products = list(payload.get("items") or [])
            try:
                self.total_products = max(len(products), int(payload.get("total", len(products)) or 0))
            except (TypeError, ValueError):
                self.total_products = len(products)
        else:
            products = list(payload or [])
            self.total_products = len(products)
        page_count = max(1, (self.total_products + self.product_page_size - 1) // self.product_page_size)
        if self.product_page > page_count:
            self.product_page = page_count
            self.refresh_products()
            return

        self._loaded_product_page = self.product_page
        self.products = products
        self.table.setRowCount(0)
        for row, product in enumerate(self.products):
            product_key = str(product["id"])
            self._product_cache[product_key] = product
            self.table.insertRow(row)
            values = (
                product["id"], product["name"], "{:,.2f}".format(float(product.get("sell_price") or 0))
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, product)
                self.table.setItem(row, col, item)
            quantity = QSpinBox()
            quantity.setRange(0, 100000)
            quantity.setValue(int(self._cart.get(product_key, 0)))
            quantity.valueChanged.connect(
                lambda value, key=product_key: self._set_cart_quantity(key, value)
            )
            self.table.setCellWidget(row, 3, quantity)
        self._update_pagination_controls()
        self.update_estimate()

    def _set_cart_quantity(self, product_key, quantity):
        quantity = max(0, int(quantity))
        if quantity:
            self._cart[product_key] = quantity
        else:
            self._cart.pop(product_key, None)
        self.update_estimate()

    def collect_items(self):
        output = []
        for product_key, quantity in self._cart.items():
            if quantity <= 0:
                continue
            product = self._product_cache.get(product_key)
            product_id = product.get("id") if product else product_key
            output.append({"product_id": product_id, "quantity": quantity})
        return output

    def update_estimate(self, *_):
        total = 0.0
        for product_key, quantity in self._cart.items():
            product = self._product_cache.get(product_key)
            if not product:
                continue
            try:
                price = float(product.get("sell_price") or 0)
            except (TypeError, ValueError):
                continue
            total += price * quantity
        self.total_label.setText("جمع تخمینی: {:,.2f}".format(total))
        units = sum(self._cart.values())
        self.cart_status_label.setText("سبد: {} نوع · {} عدد".format(len(self._cart), units))

    def checkout(self):
        items=self.collect_items()
        if not items:
            self.window.show_error("برای ثبت فروش حداقل یک تعداد مثبت وارد کنید.");return
        answer=QMessageBox.question(self,"تأیید فروش",
            "فروش با {} نوع کالا ثبت شود؟ مبلغ نهایی در سرور محاسبه می‌شود.".format(len(items)),
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.Yes)
        if answer!=QMessageBox.StandardButton.Yes:return
        paid = self.paid.isChecked()
        seat_number = self.seat_number.currentData() if self.seat_row.isVisible() else None
        if self.seat_row.isVisible() and not seat_number:
            self.window.show_error("برای فروش کافه، شماره صندلی یا میز را انتخاب کنید.")
            self.seat_number.setFocus()
            return
        settings = device_settings()
        if paid and settings.get("terminal_mode") == "tcp":
            self.window.run_api(
                lambda: self._checkout_via_terminal(items, settings),
                self._terminal_sale_created,
                busy=self.submit_button,
            )
        else:
            self.window.run_api(
                lambda: self.window.api.create_sale(items, paid=paid, seat_number=seat_number),
                self._sale_created,
                busy=self.submit_button,
            )

    def _checkout_via_terminal(self, items, settings, seat_number=None):
        quote = self.window.api.quote_sale(items, paid=True, payment_method="card", seat_number=seat_number)
        amount = str(quote.get("total") or "0")
        reference = uuid.uuid4().hex
        payment = authorize_payment(amount, reference, settings)
        try:
            receipt = self.window.api.create_sale(
                items, paid=True, idempotency_key=reference, payment_method="card",
                seat_number=seat_number,
            )
        except Exception as first_error:
            try:
                receipt = self.window.api.create_sale(
                    items, paid=True, idempotency_key=reference, payment_method="card",
                    seat_number=seat_number,
                )
            except Exception as retry_error:
                try:
                    void_payment(amount, reference, payment["transaction_id"], settings)
                except Exception as void_error:
                    raise RuntimeError(
                        "کارت‌خوان تراکنش را تأیید کرده اما ثبت فروش/لغو نامشخص است. "
                        "شناسه تراکنش {} و مرجع {} را با مدیر/پرداخت‌یار بررسی کنید. خطا: {}؛ {}".format(
                            payment["transaction_id"], reference, retry_error, void_error
                        )
                    ) from retry_error
                raise RuntimeError(
                    "ثبت فروش ناموفق بود و لغو وجه تأیید شد؛ مرجع {}. {}".format(reference, retry_error)
                ) from first_error
        return {"receipt": receipt, "transaction_id": payment["transaction_id"]}

    def _terminal_sale_created(self, result):
        receipt = result["receipt"]
        self.window.set_status(
            "پرداخت کارت‌خوان تأیید شد · شناسه تراکنش {}".format(result.get("transaction_id", "—"))
        )
        self._sale_created(receipt)

    def _sale_created(self,receipt):
        self.paid.setChecked(False)
        self.seat_number.setCurrentIndex(0)
        self._cart.clear()
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row,3)
            if widget:
                widget.setValue(0)
        self.update_estimate()
        self.window.set_status(
            "فروش شمارهٔ {} با مبلغ {:,.2f} ثبت شد.".format(
                receipt.get("day_receipt_id", "—"), float(receipt.get("total_price") or 0)
            )
        )
        self.refresh_products()
        refresh_dashboard = getattr(self.window, "refresh_dashboard_data", None)
        if callable(refresh_dashboard):
            refresh_dashboard()
        receipts_page = getattr(self.window, "receipts_page", None)
        if receipts_page is not None:
            receipts_page.refresh()
        if self.window.api:
            self.window.run_api(
                lambda: self.window.api.get_invoice_template(kind="pos_receipt"),
                lambda template: self._present_invoice(receipt, template),
                failure=lambda _error: self._present_invoice(receipt, DEFAULT_TEMPLATE),
            )
        else:
            self._present_invoice(receipt, DEFAULT_TEMPLATE)

    def _present_invoice(self, receipt, template):
        auto_print_invoice(receipt, template, self.window)
        InvoiceDialog(receipt, template, self.window).exec()

    def show_recent_receipts(self):
        if not self.window.api:
            return
        hours = int((getattr(self.window, "company_profile", None) or {}).get("receipt_history_hours", 48))
        from PySide6.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView
        dialog = QDialog(self)
        dialog.setWindowTitle("فاکتورهای اخیر")
        dialog.resize(980, 580)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(dialog)
        title = QLabel("فاکتورهای {} ساعت اخیر".format(hours))
        title.setObjectName("PageTitle")
        hint = QLabel("فاکتورهای پرداخت‌نشده با رنگ قرمز علامت‌گذاری شده‌اند. این فهرست بر اساس بازه تنظیم‌شده در پنل مدیریت محدود است.")
        hint.setObjectName("PageSubtitle")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["شناسه", "وضعیت پرداخت", "تاریخ", "صندلی / میز", "مبلغ", "روش پرداخت"])
        table.setColumnHidden(0, True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(table, 1)
        footer = QHBoxLayout()
        status = QLabel("")
        status.setObjectName("PageSubtitle")
        open_button = QPushButton("نمایش و چاپ فاکتور")
        open_button.setObjectName("PrimaryButton")
        close_button = QPushButton("بستن")
        footer.addWidget(status, 1)
        footer.addWidget(open_button)
        footer.addWidget(close_button)
        root.addLayout(footer)
        close_button.clicked.connect(dialog.reject)

        def populate(payload):
            records = list(payload.get("items") or [])
            table.setRowCount(0)
            for row, item in enumerate(records):
                table.insertRow(row)
                paid = bool(item.get("payed"))
                created_at = str(item.get("created_at") or "—").replace("T", " ")[:19]
                values = [
                    str(item.get("id") or ""),
                    "پرداخت‌شده" if paid else "پرداخت‌نشده",
                    created_at,
                    str(item.get("seat_number") or "—"),
                    "{:,.2f}".format(float(item.get("total_price") or 0)),
                    str(item.get("payment_method") or "—"),
                ]
                for col, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    if col == 0:
                        cell.setData(Qt.ItemDataRole.UserRole, item)
                    if not paid:
                        cell.setBackground(QBrush(QColor("#FCE8E6")))
                        cell.setForeground(QBrush(QColor("#9B1C1C")))
                    table.setItem(row, col, cell)
            status.setText("{} فاکتور · {} مورد پرداخت‌نشده".format(
                len(records), sum(not bool(item.get("payed")) for item in records)
            ))

        def open_selected():
            row = table.currentRow()
            cell = table.item(row, 0) if row >= 0 else None
            record = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if not record:
                QMessageBox.information(dialog, "انتخاب فاکتور", "ابتدا یک فاکتور را انتخاب کنید.")
                return
            self.window.run_api(
                lambda: self._load_recent_invoice(record["id"]),
                lambda result: self._show_recent_invoice(result, dialog),
            )

        open_button.clicked.connect(open_selected)
        table.cellDoubleClicked.connect(lambda _row, _column: open_selected())
        dialog.setMinimumSize(760, 460)
        self.window.run_api(
            self.window.api.list_recent_receipts_page,
            populate,
            failure=lambda error: QMessageBox.warning(dialog, "خطای دریافت فاکتورها", str(error)),
        )
        dialog.exec()

    def _load_recent_invoice(self, receipt_id):
        receipt = self.window.api.get_receipt(receipt_id)
        try:
            template = self.window.api.get_invoice_template()
        except Exception:
            template = DEFAULT_TEMPLATE
        return {"receipt": receipt, "template": template}

    def _show_recent_invoice(self, payload, dialog):
        InvoiceDialog(payload["receipt"], payload.get("template") or DEFAULT_TEMPLATE, self.window).exec()
