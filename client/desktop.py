"""Minimal standalone PySide2 client backed exclusively by the HTTP API."""
import os
import uuid

from PySide2.QtCore import Qt, QThread, Signal, Slot
from PySide2.QtGui import QDoubleValidator
from PySide2.QtWidgets import (
    QApplication, QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QStackedWidget,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QHeaderView,
)

from client.api_client import AccountingApiClient, ApiError


class ApiWorker(QThread):
    succeeded = Signal(str, object)
    failed = Signal(str, object)

    def __init__(self, ticket, operation, parent=None):
        super().__init__(parent)
        self.ticket = ticket
        self.operation = operation

    def run(self):
        try:
            self.succeeded.emit(self.ticket, self.operation())
        except Exception as exc:
            self.failed.emit(self.ticket, exc)


class AccountingClientWindow(QMainWindow):
    """Small API-first client used to validate the separated architecture."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Accounting App — Client")
        self.resize(1080, 720)
        self.setMinimumSize(760, 520)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("""
            QWidget { font-size: 13px; }
            QLineEdit, QSpinBox, QTableWidget {
                padding: 6px; border: 1px solid #b8c2cf; border-radius: 5px;
            }
            QPushButton { padding: 8px 14px; border-radius: 5px; }
            QPushButton:disabled { color: #888; }
            QTabWidget::pane { border: 1px solid #c9d1dc; }
        """)
        self.api = None
        self._workers = {}
        self._callbacks = {}
        self.products = []
        self.receipts = []
        self.current_user = None

        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        server_row = QHBoxLayout()
        server_row.addWidget(QLabel("نشانی سرور"))
        self.server_url = QLineEdit(
            os.environ.get("ACCOUNTING_APP_API_URL", "http://127.0.0.1:8000")
        )
        self.server_url.setPlaceholderText("http://127.0.0.1:8000")
        server_row.addWidget(self.server_url, 1)
        self.connect_button = QPushButton("بررسی اتصال")
        self.connect_button.clicked.connect(self.check_server)
        server_row.addWidget(self.connect_button)
        root_layout.addLayout(server_row)

        self.status_label = QLabel("در حال آماده‌سازی کلاینت...")
        self.status_label.setWordWrap(True)
        root_layout.addWidget(self.status_label)

        self.pages = QStackedWidget()
        self.auth_screen = self._build_auth_screen()
        self.main_screen = self._build_main_screen()
        self.pages.addWidget(self.auth_screen)
        self.pages.addWidget(self.main_screen)
        root_layout.addWidget(self.pages, 1)

        self.setCentralWidget(root)
        self.check_server()

    def _build_auth_screen(self):
        screen = QWidget()
        layout = QVBoxLayout(screen)
        layout.addStretch(1)
        self.auth_forms = QStackedWidget()
        self.login_form = self._build_login_form()
        self.setup_form = self._build_setup_form()
        self.auth_forms.addWidget(self.login_form)
        self.auth_forms.addWidget(self.setup_form)
        layout.addWidget(self.auth_forms)
        layout.addStretch(2)
        return screen

    def _build_login_form(self):
        panel = QGroupBox("ورود به حسابداری")
        panel.setMaximumWidth(520)
        form = QFormLayout(panel)
        self.login_username = QLineEdit()
        self.login_username.setPlaceholderText("نام کاربری")
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.Password)
        self.login_password.setPlaceholderText("رمز عبور")
        self.login_password.returnPressed.connect(self.login)
        form.addRow("نام کاربری", self.login_username)
        form.addRow("رمز عبور", self.login_password)
        buttons = QHBoxLayout()
        self.login_button = QPushButton("ورود")
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self.login)
        self.show_setup_button = QPushButton("نصب اولیه")
        self.show_setup_button.clicked.connect(lambda: self.auth_forms.setCurrentWidget(self.setup_form))
        buttons.addWidget(self.login_button)
        buttons.addWidget(self.show_setup_button)
        form.addRow(buttons)
        return panel

    def _build_setup_form(self):
        panel = QGroupBox("ساخت مدیر اولیه")
        panel.setMaximumWidth(520)
        form = QFormLayout(panel)
        self.setup_username = QLineEdit()
        self.setup_password = QLineEdit()
        self.setup_password.setEchoMode(QLineEdit.Password)
        self.setup_password_confirmation = QLineEdit()
        self.setup_password_confirmation.setEchoMode(QLineEdit.Password)
        self.setup_token = QLineEdit()
        self.setup_token.setEchoMode(QLineEdit.Password)
        self.setup_token.setPlaceholderText("فقط در صورت فعال بودن نصب راه دور")
        form.addRow("نام مدیر", self.setup_username)
        form.addRow("رمز", self.setup_password)
        form.addRow("تکرار رمز", self.setup_password_confirmation)
        form.addRow("توکن نصب راه دور", self.setup_token)
        buttons = QHBoxLayout()
        self.setup_button = QPushButton("ساخت مدیر")
        self.setup_button.clicked.connect(self.complete_setup)
        self.back_to_login_button = QPushButton("بازگشت به ورود")
        self.back_to_login_button.clicked.connect(lambda: self.auth_forms.setCurrentWidget(self.login_form))
        buttons.addWidget(self.setup_button)
        buttons.addWidget(self.back_to_login_button)
        form.addRow(buttons)
        return panel

    def _build_main_screen(self):
        tabs = QTabWidget()
        self.products_tab = self._build_products_tab()
        self.sales_tab = self._build_sales_tab()
        self.receipts_tab = self._build_receipts_tab()
        self.reports_tab = self._build_reports_tab()
        tabs.addTab(self.products_tab, "کالاها")
        tabs.addTab(self.sales_tab, "ثبت فروش")
        tabs.addTab(self.receipts_tab, "رسیدها")
        tabs.addTab(self.reports_tab, "گزارش")
        self.main_tabs = tabs
        return tabs

    @staticmethod
    def _make_table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def _build_products_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        actions = QHBoxLayout()
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText("جست‌وجوی نام کالا")
        self.product_search.returnPressed.connect(self.refresh_products)
        self.product_search_button = QPushButton("جست‌وجو")
        self.product_search_button.clicked.connect(self.refresh_products)
        self.refresh_products_button = QPushButton("بازخوانی")
        self.refresh_products_button.clicked.connect(self.refresh_products)
        actions.addWidget(self.product_search, 1)
        actions.addWidget(self.product_search_button)
        actions.addWidget(self.refresh_products_button)
        layout.addLayout(actions)

        self.products_table = self._make_table(["شناسه", "نام کالا", "قیمت خرید", "قیمت فروش"])
        self.products_table.setColumnHidden(0, True)
        layout.addWidget(self.products_table, 1)

        self.product_create_box = QGroupBox("افزودن کالا (مدیر)")
        create_form = QHBoxLayout(self.product_create_box)
        self.new_product_name = QLineEdit()
        self.new_product_name.setPlaceholderText("نام کالا")
        self.new_product_buy = QLineEdit()
        self.new_product_buy.setPlaceholderText("قیمت خرید")
        self.new_product_buy.setValidator(QDoubleValidator(0.0, 1e14, 4, self))
        self.new_product_sell = QLineEdit()
        self.new_product_sell.setPlaceholderText("قیمت فروش")
        self.new_product_sell.setValidator(QDoubleValidator(0.0, 1e14, 4, self))
        self.create_product_button = QPushButton("افزودن")
        self.create_product_button.clicked.connect(self.create_product)
        self.delete_product_button = QPushButton("حذف انتخاب‌شده")
        self.delete_product_button.clicked.connect(self.delete_product)
        create_form.addWidget(self.new_product_name, 2)
        create_form.addWidget(self.new_product_buy)
        create_form.addWidget(self.new_product_sell)
        create_form.addWidget(self.create_product_button)
        create_form.addWidget(self.delete_product_button)
        layout.addWidget(self.product_create_box)
        return tab

    def _build_sales_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("تعداد هر کالا را مشخص کنید؛ قیمت نهایی در سمت سرور محاسبه می‌شود."))
        self.sale_table = self._make_table(["شناسه", "کالا", "قیمت فروش", "تعداد"])
        self.sale_table.setColumnHidden(0, True)
        layout.addWidget(self.sale_table, 1)
        footer = QHBoxLayout()
        self.sale_paid_checkbox = QCheckBox("پرداخت‌شده")
        self.submit_sale_button = QPushButton("ثبت اتمیک فروش")
        self.submit_sale_button.clicked.connect(self.submit_sale)
        self.refresh_sale_button = QPushButton("بازخوانی کالاها")
        self.refresh_sale_button.clicked.connect(self.refresh_products)
        footer.addWidget(self.sale_paid_checkbox)
        footer.addStretch(1)
        footer.addWidget(self.refresh_sale_button)
        footer.addWidget(self.submit_sale_button)
        layout.addLayout(footer)
        return tab

    def _build_receipts_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        header = QHBoxLayout()
        header.addWidget(QLabel("رسیدهای قابل مشاهده برای کاربر واردشده"))
        header.addStretch(1)
        refresh = QPushButton("بازخوانی رسیدها")
        refresh.clicked.connect(self.refresh_receipts)
        header.addWidget(refresh)
        layout.addLayout(header)
        self.receipts_table = self._make_table(
            ["شناسه", "شماره روزانه", "مبلغ", "پرداخت", "تاریخ"]
        )
        self.receipts_table.setColumnHidden(0, True)
        self.receipts_table.cellDoubleClicked.connect(self.open_receipt)
        layout.addWidget(self.receipts_table, 1)
        layout.addWidget(QLabel("برای مشاهده اقلام، روی یک رسید دوبار کلیک کنید."))
        return tab

    def _build_reports_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.report_labels = {}
        for key, label in (
            ("receipt_count", "تعداد رسیدها"),
            ("sales_total", "جمع فروش"),
            ("paid_count", "رسیدهای پرداخت‌شده"),
            ("unpaid_count", "رسیدهای پرداخت‌نشده"),
            ("item_count", "تعداد اقلام فروخته‌شده"),
        ):
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(QLabel(label))
            layout.addWidget(value)
            self.report_labels[key] = value
        refresh = QPushButton("به‌روزرسانی گزارش")
        refresh.clicked.connect(self.refresh_summary)
        layout.addWidget(refresh)
        layout.addStretch(1)
        return tab

    def _new_client(self):
        url = self.server_url.text().strip()
        if not url:
            raise ValueError("نشانی سرور را وارد کنید.")
        return AccountingApiClient(url)

    def check_server(self):
        if self.pages.currentWidget() is self.main_screen:
            if self.api is not None:
                self.api.clear_session()
            self.pages.setCurrentWidget(self.auth_screen)
        try:
            self.api = self._new_client()
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.status_label.setText("در حال بررسی سرور...")
        self._run(
            self.api.setup_status,
            self._on_setup_status,
            on_error=self._on_connection_error,
            busy=self.connect_button,
        )

    def _on_setup_status(self, result):
        setup_required = bool(result.get("setup_required"))
        self.show_setup_button.setVisible(setup_required)
        if setup_required:
            self.auth_forms.setCurrentWidget(self.setup_form)
            self.status_label.setText("سرور آماده است؛ ابتدا مدیر اولیه را بسازید.")
        else:
            self.auth_forms.setCurrentWidget(self.login_form)
            self.status_label.setText("سرور آمادهٔ ورود است.")

    def _on_connection_error(self, error):
        self.status_label.setText("اتصال برقرار نشد: {}".format(error))
        self.pages.setCurrentWidget(self.auth_screen)

    def _run(self, operation, on_success, *, on_error=None, busy=None):
        ticket = uuid.uuid4().hex
        self._callbacks[ticket] = (on_success, on_error, busy)
        worker = ApiWorker(ticket, operation, self)
        worker.succeeded.connect(self._on_worker_success)
        worker.failed.connect(self._on_worker_failure)
        worker.finished.connect(self._on_worker_finished)
        self._workers[ticket] = worker
        if busy is not None:
            busy.setEnabled(False)
        worker.start()

    def _finish_callback(self, ticket):
        callback = self._callbacks.pop(ticket, None)
        if callback:
            _, _, busy = callback
            if busy is not None:
                busy.setEnabled(True)
        return callback

    @Slot(str, object)
    def _on_worker_success(self, ticket, result):
        callback = self._finish_callback(ticket)
        if callback:
            on_success, _on_error, _busy = callback
            on_success(result)

    @Slot(str, object)
    def _on_worker_failure(self, ticket, error):
        callback = self._finish_callback(ticket)
        if not callback:
            return
        _on_success, on_error, _busy = callback
        if on_error is not None:
            on_error(error)
        else:
            self.show_error(error)

    @Slot()
    def _on_worker_finished(self):
        worker = self.sender()
        for ticket, candidate in list(self._workers.items()):
            if candidate is worker:
                self._workers.pop(ticket, None)
                break
        if worker is not None:
            worker.deleteLater()

    def login(self):
        try:
            self.api = self._new_client()
        except ValueError as exc:
            self.show_error(exc)
            return
        username = self.login_username.text().strip()
        password = self.login_password.text()
        if len(username) < 4 or len(password) < 4:
            self.show_error("نام کاربری و رمز عبور باید دست‌کم ۴ نویسه باشند.")
            return
        self._run(
            lambda: self.api.login(username, password),
            self._enter_main,
            busy=self.login_button,
        )

    def complete_setup(self):
        try:
            self.api = self._new_client()
        except ValueError as exc:
            self.show_error(exc)
            return
        username = self.setup_username.text().strip()
        password = self.setup_password.text()
        confirmation = self.setup_password_confirmation.text()
        if len(username) < 4 or len(password) < 4:
            self.show_error("نام کاربری و رمز عبور باید دست‌کم ۴ نویسه باشند.")
            return
        if password != confirmation:
            self.show_error("تکرار رمز عبور با رمز یکسان نیست.")
            return
        token = self.setup_token.text().strip() or None
        self._run(
            lambda: self.api.complete_setup(username, password, confirmation, setup_token=token),
            self._enter_main,
            busy=self.setup_button,
        )

    def _enter_main(self, user):
        self.current_user = user
        self.pages.setCurrentWidget(self.main_screen)
        self.status_label.setText("واردشده به‌عنوان {}{}".format(
            user.get("username", ""),
            " — مدیر" if user.get("is_admin") else "",
        ))
        admin = bool(user.get("is_admin"))
        self.product_create_box.setVisible(admin)
        self._run(self.refresh_products_data, self._populate_products)
        self.refresh_receipts()
        self.refresh_summary()

    def refresh_products_data(self):
        query = self.product_search.text().strip()
        return self.api.list_products(q=query or None, page_size=200)

    def refresh_products(self):
        if self.api is None:
            return
        self._run(self.refresh_products_data, self._populate_products, busy=self.refresh_products_button)

    def _populate_products(self, products):
        self.products = products
        self.products_table.setRowCount(0)
        self.sale_table.setRowCount(0)
        for row_index, product in enumerate(products):
            self.products_table.insertRow(row_index)
            values = [
                product["id"], product["name"],
                self._money(product["buy_price"]), self._money(product["sell_price"]),
            ]
            for column, value in enumerate(values):
                self.products_table.setItem(row_index, column, QTableWidgetItem(str(value)))

            self.sale_table.insertRow(row_index)
            self.sale_table.setItem(row_index, 0, QTableWidgetItem(str(product["id"])))
            self.sale_table.setItem(row_index, 1, QTableWidgetItem(str(product["name"])))
            self.sale_table.setItem(row_index, 2, QTableWidgetItem(self._money(product["sell_price"])))
            quantity = QSpinBox()
            quantity.setRange(0, 100000)
            quantity.setValue(0)
            self.sale_table.setCellWidget(row_index, 3, quantity)

    def create_product(self):
        name = self.new_product_name.text().strip()
        buy = self.new_product_buy.text().strip()
        sell = self.new_product_sell.text().strip()
        if not name or not buy or not sell:
            self.show_error("نام و هر دو قیمت را وارد کنید.")
            return
        self._run(
            lambda: self.api.create_product(name=name, buy_price=buy, sell_price=sell),
            self._product_created,
            busy=self.create_product_button,
        )

    def _product_created(self, product):
        self.new_product_name.clear()
        self.new_product_buy.clear()
        self.new_product_sell.clear()
        self.status_label.setText("کالا «{}» ساخته شد.".format(product["name"]))
        self.refresh_products()

    def delete_product(self):
        row = self.products_table.currentRow()
        if row < 0:
            self.show_error("ابتدا یک کالا را انتخاب کنید.")
            return
        product_id = self.products_table.item(row, 0).text()
        name = self.products_table.item(row, 1).text()
        answer = QMessageBox.question(
            self, "حذف کالا", "کالای «{}» حذف شود؟".format(name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run(
            lambda: self.api.delete_product(product_id),
            lambda _result: self._product_deleted(),
            busy=self.delete_product_button,
        )

    def _product_deleted(self):
        self.status_label.setText("کالا حذف شد.")
        self.refresh_products()

    def submit_sale(self):
        items = []
        for row in range(self.sale_table.rowCount()):
            quantity = self.sale_table.cellWidget(row, 3).value()
            if quantity > 0:
                items.append({
                    "product_id": self.sale_table.item(row, 0).text(),
                    "quantity": quantity,
                })
        if not items:
            self.show_error("برای ثبت فروش حداقل یک تعداد مثبت وارد کنید.")
            return
        paid = self.sale_paid_checkbox.isChecked()
        self._run(
            lambda: self.api.create_sale(items, paid=paid),
            self._sale_created,
            busy=self.submit_sale_button,
        )

    def _sale_created(self, receipt):
        self.sale_paid_checkbox.setChecked(False)
        self.status_label.setText("فروش ثبت شد؛ شماره روزانه {}".format(receipt["day_receipt_id"]))
        QMessageBox.information(
            self, "ثبت فروش",
            "رسید با موفقیت ثبت شد.\nشماره روزانه: {}\nجمع: {}".format(
                receipt["day_receipt_id"], self._money(receipt["total_price"])
            ),
        )
        self.refresh_products()
        self.refresh_receipts()
        self.refresh_summary()

    def refresh_receipts(self):
        if self.api is not None:
            self._run(self.api.list_receipts, self._populate_receipts)

    def _populate_receipts(self, receipts):
        self.receipts = receipts
        self.receipts_table.setRowCount(0)
        for row_index, receipt in enumerate(receipts):
            self.receipts_table.insertRow(row_index)
            values = [
                receipt["id"], receipt["day_receipt_id"],
                self._money(receipt["total_price"]),
                "بله" if receipt["payed"] else "خیر",
                str(receipt["created_at"]).replace("T", " "),
            ]
            for column, value in enumerate(values):
                self.receipts_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def open_receipt(self, row, _column):
        if row < 0 or row >= len(self.receipts):
            return
        receipt_id = self.receipts_table.item(row, 0).text()
        self._run(
            lambda: self.api.get_receipt(receipt_id),
            self._show_receipt_detail,
        )

    def _show_receipt_detail(self, receipt):
        lines = [
            "شماره روزانه: {}".format(receipt["day_receipt_id"]),
            "جمع: {}".format(self._money(receipt["total_price"])),
            "وضعیت پرداخت: {}".format("پرداخت‌شده" if receipt["payed"] else "پرداخت‌نشده"),
            "",
            "اقلام:",
        ]
        for item in receipt["items"]:
            product = next(
                (record for record in self.products if record["id"] == item.get("product_id")),
                None,
            )
            name = product["name"] if product else str(item.get("product_id") or "محصول حذف‌شده")
            lines.append("{} × {} — {}".format(name, item["quantity"], self._money(item["sell_price"])))
        QMessageBox.information(self, "جزئیات رسید", "\n".join(lines))

    def refresh_summary(self):
        if self.api is not None:
            self._run(self.api.sales_summary, self._populate_summary)

    def _populate_summary(self, summary):
        self.report_labels["receipt_count"].setText(str(summary["receipt_count"]))
        self.report_labels["sales_total"].setText(self._money(summary["sales_total"]))
        self.report_labels["paid_count"].setText(str(summary["paid_count"]))
        self.report_labels["unpaid_count"].setText(str(summary["unpaid_count"]))
        self.report_labels["item_count"].setText(str(summary["item_count"]))

    @staticmethod
    def _money(value):
        try:
            return "{:,.2f}".format(float(value)).rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return str(value)

    def show_error(self, error):
        text = str(error)
        if getattr(error, "status_code", None) == 401 and self.pages.currentWidget() is self.main_screen:
            if self.api is not None:
                self.api.clear_session()
            self.pages.setCurrentWidget(self.auth_screen)
            self.auth_forms.setCurrentWidget(self.login_form)
            self.status_label.setText("نشست پایان یافته است؛ دوباره وارد شوید.")
        QMessageBox.warning(self, "خطا", text)

    def closeEvent(self, event):
        for worker in list(self._workers.values()):
            if worker.isRunning():
                worker.wait(35000)
        event.accept()


def main():
    app = QApplication([])
    app.setApplicationName("Accounting App Client")
    window = AccountingClientWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
