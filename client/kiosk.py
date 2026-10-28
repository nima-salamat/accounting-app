"""Fullscreen self-service kiosk with first-run configuration and manager-protected settings."""
import os
import uuid

from PySide6.QtCore import Qt, Slot, QSettings, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

try:
    import keyring
except ImportError:
    keyring = None

from client.api_client import AccountingApiClient
from client.payment_terminal import (
    PaymentTerminalError, authorize_payment, void_payment,
)
from client.ui.device_settings import DeviceSettingsDialog, device_settings
from client.ui.invoice_dialog import auto_print_invoice
from client.ui.invoice_render import DEFAULT_TEMPLATE
from client.ui.permissions import can_access
from client.ui.theme import stylesheet
from client.ui.touch_keyboard import TouchKeyboardDialog
from client.ui.worker import ApiWorker


KIOSK_KEYRING_SERVICE = "Accounting App Self-service Kiosk"
KIOSK_GRANTS = "role:kiosk;products:r;sales:c;invoices:r"


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        if child_layout is not None:
            _clear_layout(child_layout)


class ManagerUnlockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تأیید هویت مدیر")
        self.setMinimumWidth(460)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        title = QLabel("تنظیمات کیوسک محافظت‌شده است")
        title.setObjectName("PageTitle")
        subtitle = QLabel("برای تغییر تنظیمات یا خروج از حالت تمام‌صفحه، با حساب مدیر وارد شوید.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)
        form = QFormLayout()
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.keyboard_button = QPushButton("⌨ صفحه‌کلید لمسی")
        self.keyboard_button.clicked.connect(self.show_keyboard)
        form.addRow("نام کاربری مدیر", self.username)
        form.addRow("رمز عبور", self.password)
        form.addRow("", self.keyboard_button)
        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("تأیید مدیر")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def show_keyboard(self):
        target = self.focusWidget()
        if not isinstance(target, QLineEdit):
            target = self.username
        TouchKeyboardDialog(target, self).exec()

    def _validate(self):
        if not self.username.text().strip() or not self.password.text():
            QMessageBox.warning(self, "اطلاعات ورود", "نام کاربری و رمز مدیر را وارد کنید.")
            return
        self.accept()


class KioskSetupPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)
        heading = QLabel("راه‌اندازی کیوسک خودخدمت")
        heading.setObjectName("PageTitle")
        sub = QLabel(
            "این صفحه در راه‌اندازی اولیه نمایش داده می‌شود. پس از تأیید، کیوسک تمام‌صفحه باز می‌شود؛ "
            "برای دسترسی دوباره به تنظیمات باید مدیر احراز هویت شود."
        )
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(sub)

        form_card = QFrame()
        form_card.setObjectName("Card")
        form = QFormLayout(form_card)
        form.setContentsMargins(20, 18, 20, 18)
        form.setVerticalSpacing(12)
        self.server_url = QLineEdit(os.environ.get("ACCOUNTING_APP_API_URL", "http://127.0.0.1:8000"))
        self.server_url.setPlaceholderText("https://accounting.example.com")
        self.company_name = QLineEdit("فروشگاه")
        self.company_name.setPlaceholderText("نام فروشگاه روی صفحهٔ مشتری")
        self.admin_username = QLineEdit()
        self.admin_username.setPlaceholderText("حساب مدیر اصلی")
        self.admin_password = QLineEdit()
        self.admin_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.kiosk_username = QLineEdit("selfservice_kiosk")
        self.kiosk_password = QLineEdit()
        self.kiosk_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.kiosk_password.setPlaceholderText("حداقل ۱۲ نویسه؛ فقط در مخزن امن سیستم‌عامل ذخیره می‌شود")
        self.allow_unpaid = QCheckBox("اجازهٔ ثبت سفارش پرداخت‌نشده برای پرداخت در باجه / تحویل توسط کارمند")
        self.allow_unpaid.setChecked(False)
        form.addRow("نشانی API", self.server_url)
        form.addRow("نام فروشگاه", self.company_name)
        form.addRow("نام کاربری مدیر", self.admin_username)
        form.addRow("رمز مدیر", self.admin_password)
        form.addRow("نام کاربری کیوسک", self.kiosk_username)
        form.addRow("رمز اختصاصی کیوسک", self.kiosk_password)
        form.addRow("", self.allow_unpaid)
        root.addWidget(form_card)

        note = QLabel(
            "امنیت: حساب کیوسک به مشاهدهٔ کالا، ایجاد فروش و خواندن قالب فاکتور محدود می‌شود. "
            "تنظیمات مدیر و خروج از کیوسک با Ctrl+Alt+S و Ctrl+Alt+Q محافظت می‌شوند. "
            "برای پرداخت مستقل با کارت‌خوان، پل پرداخت سازگار باید پاسخ امضاشده و تأیید واقعی بانک/دستگاه را برگرداند."
        )
        note.setObjectName("StatusPill")
        note.setWordWrap(True)
        root.addWidget(note)
        controls = QHBoxLayout()
        self.device_button = QPushButton("تنظیم چاپگر / کارت‌خوان")
        self.device_button.clicked.connect(lambda: DeviceSettingsDialog(self, kiosk=True).exec())
        self.keyboard_button = QPushButton("⌨ صفحه‌کلید لمسی")
        self.keyboard_button.clicked.connect(self.show_keyboard)
        self.save_button = QPushButton("تأیید و ورود به خرید")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_settings)
        controls.addWidget(self.device_button)
        controls.addWidget(self.keyboard_button)
        controls.addStretch(1)
        controls.addWidget(self.save_button)
        root.addLayout(controls)
        self.status = QLabel()
        self.status.setObjectName("PageSubtitle")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.setMinimumWidth(900)

    def prefill(self, server_url=None, company_name=None, admin_username=None, admin_password=None,
                kiosk_username=None, kiosk_password=None, allow_unpaid=None):
        settings = QSettings("AccountingApp", "SelfServiceKiosk")
        self.server_url.setText(server_url or settings.value("server_url", self.server_url.text(), type=str))
        self.company_name.setText(company_name or settings.value("company_name", self.company_name.text(), type=str))
        self.kiosk_username.setText(kiosk_username or settings.value("kiosk_username", self.kiosk_username.text(), type=str))
        self.admin_username.setText(admin_username or "")
        self.admin_password.setText(admin_password or "")
        self.kiosk_password.setText(kiosk_password or "")
        if allow_unpaid is not None:
            self.allow_unpaid.setChecked(bool(allow_unpaid))
        else:
            self.allow_unpaid.setChecked(settings.value("allow_unpaid_orders", False, type=bool))

    def show_keyboard(self):
        target = self.focusWidget()
        if not isinstance(target, QLineEdit):
            target = self.server_url
        TouchKeyboardDialog(target, self).exec()

    def save_settings(self):
        values = {
            "server_url": self.server_url.text().strip(),
            "company_name": self.company_name.text().strip(),
            "admin_username": self.admin_username.text().strip(),
            "admin_password": self.admin_password.text(),
            "kiosk_username": self.kiosk_username.text().strip(),
            "kiosk_password": self.kiosk_password.text(),
            "allow_unpaid": self.allow_unpaid.isChecked(),
        }
        if not values["server_url"] or not values["company_name"]:
            self.status.setText("نشانی سرور و نام فروشگاه الزامی است.")
            return
        if len(values["admin_username"]) < 4 or not values["admin_password"]:
            self.status.setText("برای تأیید تنظیمات، حساب مدیر و رمز آن را وارد کنید.")
            return
        if len(values["kiosk_username"]) < 4 or len(values["kiosk_password"]) < 12:
            self.status.setText("نام کاربری کیوسک حداقل ۴ و رمز آن حداقل ۱۲ نویسه باشد.")
            return
        if keyring is None:
            self.status.setText("مخزن امن رمز در دسترس نیست. بستهٔ keyring را نصب و سیستم‌عامل را پیکربندی کنید.")
            return
        self.save_button.setEnabled(False)
        self.status.setText("در حال تأیید مدیر و آماده‌سازی حساب محدود کیوسک…")
        self.window.run_api(
            lambda: self._provision(values),
            self.window.setup_completed,
            failure=self._provision_failed,
            busy=self.save_button,
        )

    def _provision(self, values):
        api = AccountingApiClient(values["server_url"])
        admin_login = api.login(
            values["admin_username"], values["admin_password"],
            client_name="Self-service kiosk configuration",
        )
        if admin_login.get("status") != "active" or not admin_login.get("access_token"):
            raise RuntimeError("نشست مدیر فعال نیست؛ اگر ورود به تأیید نیاز دارد، ابتدا نشست را تأیید کنید.")
        admin = admin_login.get("user") or {}
        if not admin.get("is_admin"):
            raise RuntimeError("فقط مدیر سیستم می‌تواند کیوسک را راه‌اندازی یا تنظیم کند.")

        users_response = api.list_users_page(q=values["kiosk_username"], page=1, page_size=50)
        existing = next(
            (item for item in users_response.get("items", [])
             if item.get("username", "").casefold() == values["kiosk_username"].casefold()),
            None,
        )
        if existing and existing.get("is_admin"):
            raise RuntimeError("نام کاربری انتخاب‌شده متعلق به مدیر است؛ نام دیگری برای کیوسک انتخاب کنید.")
        if existing:
            api.update_user(
                existing["id"],
                password=values["kiosk_password"],
                buttons=KIOSK_GRANTS,
                is_active=True,
                requires_session_activation=False,
            )
        else:
            api.create_user(
                username=values["kiosk_username"],
                password=values["kiosk_password"],
                is_admin=False,
                buttons=KIOSK_GRANTS,
                is_active=True,
                requires_session_activation=False,
            )

        kiosk_login = api.login(
            values["kiosk_username"], values["kiosk_password"],
            client_name="Self-service kiosk",
        )
        if kiosk_login.get("status") != "active" or not kiosk_login.get("access_token"):
            raise RuntimeError("ورود حساب کیوسک انجام نشد.")
        kiosk_user = kiosk_login.get("user") or {}
        if not (
            can_access(kiosk_user, "sales", "create")
            and can_access(kiosk_user, "products", "read")
        ):
            raise RuntimeError("مجوز حساب کیوسک کافی نیست؛ سیاست دسترسی در سمت سرور بررسی شود.")
        return {
            "api": api,
            "server_url": values["server_url"],
            "company_name": values["company_name"],
            "admin_username": values["admin_username"],
            "kiosk_username": values["kiosk_username"],
            "kiosk_password": values["kiosk_password"],
            "allow_unpaid": values["allow_unpaid"],
            "user": kiosk_user,
        }

    def _provision_failed(self, error):
        self.status.setText(str(error))
        self.save_button.setEnabled(True)


class KioskShopPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.api = None
        self.user = None
        self.products = []
        self.categories = []
        self.cart = {}
        self.setObjectName("AppRoot")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        catalog_card = QFrame()
        catalog_card.setObjectName("Card")
        catalog = QVBoxLayout(catalog_card)
        catalog.setContentsMargins(16, 14, 16, 14)
        catalog.setSpacing(10)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        self.shop_title = QLabel("انتخاب محصولات")
        self.shop_title.setObjectName("PageTitle")
        subtitle = QLabel("برای افزودن کالا به سبد، کارت محصول را لمس کنید.")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(self.shop_title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box, 1)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh_catalog)
        heading.addWidget(self.refresh_button)
        catalog.addLayout(heading)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("نام کالا یا بارکد را اسکن کنید…")
        self.search.setMinimumHeight(44)
        self.search.returnPressed.connect(self.refresh_catalog)
        self.keyboard_button = QPushButton("⌨")
        self.keyboard_button.setToolTip("صفحه‌کلید لمسی")
        self.keyboard_button.setMinimumWidth(54)
        self.keyboard_button.setMinimumHeight(44)
        self.keyboard_button.clicked.connect(lambda: TouchKeyboardDialog(self.search, self).exec())
        self.category = QComboBox()
        self.category.setMinimumHeight(44)
        self.category.currentIndexChanged.connect(self.refresh_catalog)
        filters.addWidget(self.search, 2)
        filters.addWidget(self.keyboard_button)
        filters.addWidget(self.category, 1)
        catalog.addLayout(filters)

        self.product_host = QWidget()
        self.product_grid = QGridLayout(self.product_host)
        self.product_grid.setContentsMargins(0, 0, 0, 0)
        self.product_grid.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.product_host)
        catalog.addWidget(scroll, 1)
        root.addWidget(catalog_card, 3)

        cart_card = QFrame()
        cart_card.setObjectName("Card")
        cart_layout = QVBoxLayout(cart_card)
        cart_layout.setContentsMargins(16, 14, 16, 14)
        cart_layout.setSpacing(10)
        cart_header = QHBoxLayout()
        cart_title = QLabel("سبد خرید")
        cart_title.setObjectName("PageTitle")
        self.cart_count = QLabel("۰ کالا")
        self.cart_count.setObjectName("StatusPill")
        cart_header.addWidget(cart_title)
        cart_header.addStretch(1)
        cart_header.addWidget(self.cart_count)
        cart_layout.addLayout(cart_header)
        self.cart_host = QWidget()
        self.cart_layout = QVBoxLayout(self.cart_host)
        self.cart_layout.setContentsMargins(0, 0, 0, 0)
        self.cart_layout.setSpacing(8)
        cart_scroll = QScrollArea()
        cart_scroll.setWidgetResizable(True)
        cart_scroll.setWidget(self.cart_host)
        cart_layout.addWidget(cart_scroll, 1)
        self.empty_cart = QLabel("هنوز کالایی انتخاب نشده است.")
        self.empty_cart.setObjectName("PageSubtitle")
        self.empty_cart.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cart_layout.addWidget(self.empty_cart)

        totals = QFrame()
        totals.setObjectName("Card")
        total_layout = QVBoxLayout(totals)
        self.total_label = QLabel("مبلغ: ۰")
        self.total_label.setObjectName("MetricValue")
        self.clear_button = QPushButton("خالی‌کردن سبد")
        self.clear_button.clicked.connect(self.clear_cart)
        self.checkout_button = QPushButton("ادامه و پرداخت")
        self.checkout_button.setObjectName("PrimaryButton")
        self.checkout_button.setMinimumHeight(56)
        self.checkout_button.clicked.connect(self.checkout)
        total_layout.addWidget(self.total_label)
        total_layout.addWidget(self.clear_button)
        total_layout.addWidget(self.checkout_button)
        cart_layout.addWidget(totals)
        root.addWidget(cart_card, 2)
        self._render_cart()

    def bind_session(self, api, user, company_name, allow_unpaid=False):
        self.api = api
        self.user = user
        self.allow_unpaid = bool(allow_unpaid)
        self.shop_title.setText(company_name or "انتخاب محصولات")
        self.refresh_catalog()

    def refresh_catalog(self, *_args):
        if not self.api:
            return
        self.refresh_button.setEnabled(False)
        query = self.search.text().strip() or None
        category_id = self.category.currentData()
        self.window.run_api(
            lambda: self._load_catalog(query, category_id),
            self._catalog_loaded,
            busy=self.refresh_button,
        )

    def _load_catalog(self, query, category_id):
        products, page = [], 1
        total = None
        while True:
            data = self.api.list_products_page(
                q=query, category_id=category_id, page=page, page_size=100
            )
            batch = list(data.get("items") or [])
            total = int(data.get("total", len(batch)))
            products.extend(batch)
            if not batch or len(products) >= total:
                break
            page += 1
        categories_data = self.api.list_categories_page(page=1, page_size=200)
        return {"products": products, "categories": categories_data.get("items") or []}

    def _catalog_loaded(self, data):
        self.products = list(data.get("products") or [])
        self.categories = list(data.get("categories") or [])
        current_category = self.category.currentData()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("همهٔ دسته‌ها", None)
        for item in self.categories:
            self.category.addItem(item.get("name", "—"), item.get("id"))
        index = self.category.findData(current_category)
        self.category.setCurrentIndex(index if index >= 0 else 0)
        self.category.blockSignals(False)
        self._render_products()

    def _render_products(self):
        _clear_layout(self.product_grid)
        columns = 3
        for index, product in enumerate(self.products):
            title = product.get("name", "کالا")
            price = float(product.get("sell_price") or 0)
            tracked = bool(product.get("track_stock"))
            stock = float(product.get("stock_quantity") or 0)
            text = "{}\n{:,.2f}".format(title, price)
            if tracked:
                text += "\nموجودی: {:g}".format(stock)
            button = QPushButton(text)
            button.setObjectName("Card")
            button.setMinimumHeight(112)
            button.setMinimumWidth(150)
            button.setWordWrap(True) if hasattr(button, "setWordWrap") else None
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            enabled = not (tracked and stock <= 0)
            button.setEnabled(enabled)
            if not enabled:
                button.setToolTip("موجودی کالا تمام شده است.")
            button.clicked.connect(lambda _checked=False, item=product: self.add_to_cart(item))
            self.product_grid.addWidget(button, index // columns, index % columns)
        self.product_grid.setRowStretch((len(self.products) // columns) + 1, 1)
        if not self.products:
            empty = QLabel("کالایی برای این جست‌وجو پیدا نشد.")
            empty.setObjectName("PageSubtitle")
            self.product_grid.addWidget(empty, 0, 0, 1, columns)

    def add_to_cart(self, product):
        key = str(product["id"])
        existing = self.cart.get(key, {"product": product, "quantity": 0})
        next_quantity = int(existing["quantity"]) + 1
        if product.get("track_stock") and next_quantity > int(float(product.get("stock_quantity") or 0)):
            QMessageBox.information(self, "موجودی کافی نیست", "تعداد انتخاب‌شده از موجودی فعلی بیشتر است.")
            return
        self.cart[key] = {"product": product, "quantity": next_quantity}
        self._render_cart()

    def _change_quantity(self, key, delta):
        if key not in self.cart:
            return
        row = self.cart[key]
        next_quantity = row["quantity"] + delta
        if next_quantity <= 0:
            self.cart.pop(key, None)
        else:
            product = row["product"]
            if product.get("track_stock") and next_quantity > int(float(product.get("stock_quantity") or 0)):
                return
            row["quantity"] = next_quantity
        self._render_cart()

    def clear_cart(self):
        self.cart.clear()
        self._render_cart()

    def _render_cart(self):
        _clear_layout(self.cart_layout)
        quantity_sum = sum(row["quantity"] for row in self.cart.values())
        total = sum(float(row["product"].get("sell_price") or 0) * row["quantity"] for row in self.cart.values())
        self.cart_count.setText("{} کالا".format(quantity_sum))
        self.empty_cart.setVisible(not bool(self.cart))
        self.total_label.setText("مبلغ: {:,.2f}".format(total))
        self.checkout_button.setEnabled(bool(self.cart))
        for key, row in self.cart.items():
            product, quantity = row["product"], row["quantity"]
            card = QFrame()
            card.setObjectName("Card")
            line = QHBoxLayout(card)
            line.setContentsMargins(8, 8, 8, 8)
            namebox = QVBoxLayout()
            name = QLabel(product.get("name", "کالا"))
            name.setWordWrap(True)
            detail = QLabel("{:,.2f} × {}".format(float(product.get("sell_price") or 0), quantity))
            detail.setObjectName("PageSubtitle")
            namebox.addWidget(name)
            namebox.addWidget(detail)
            line.addLayout(namebox, 1)
            minus = QPushButton("−")
            minus.setMinimumSize(42, 42)
            plus = QPushButton("+")
            plus.setMinimumSize(42, 42)
            minus.clicked.connect(lambda _checked=False, item_key=key: self._change_quantity(item_key, -1))
            plus.clicked.connect(lambda _checked=False, item_key=key: self._change_quantity(item_key, 1))
            line.addWidget(minus)
            line.addWidget(plus)
            self.cart_layout.addWidget(card)
        self.cart_layout.addStretch(1)

    def checkout(self):
        items = [
            {"product_id": row["product"]["id"], "quantity": row["quantity"]}
            for row in self.cart.values()
        ]
        if not items:
            return
        settings = device_settings()
        mode = settings.get("terminal_mode")
        if mode != "tcp" and not self.allow_unpaid:
            QMessageBox.warning(
                self, "پرداخت مستقل پیکربندی نشده است",
                "برای فروش خودخدمت، یک پل پرداخت امضاشده و متصل به SDK کارت‌خوان لازم است. "
                "بدون تأیید واقعی دستگاه، کیوسک فروش را پرداخت‌شده ثبت نمی‌کند. "
                "می‌توانید در تنظیمات مدیر گزینهٔ سفارش پرداخت‌نشده برای پرداخت در باجه را فعال کنید.",
            )
            return
        if mode != "tcp":
            answer = QMessageBox.question(
                self, "ثبت سفارش بدون پرداخت",
                "این سفارش به‌صورت پرداخت‌نشده ثبت می‌شود و نیاز به پرداخت/تحویل توسط کارمند دارد. ادامه می‌دهید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.window.run_api(
            lambda: self._checkout_operation(items, settings, mode),
            self._checkout_completed,
            busy=self.checkout_button,
        )

    def _checkout_operation(self, items, settings, mode):
        if mode != "tcp":
            receipt = self.api.create_sale(items, paid=False, payment_method="unpaid")
            return {
                "receipt": receipt,
                "template": self._safe_invoice_template(),
                "payment_status": "unpaid",
                "transaction_id": None,
            }

        quote = self.api.quote_sale(items, paid=True)
        amount = str(quote.get("total") or "0")
        reference = uuid.uuid4().hex
        payment = authorize_payment(amount, reference, settings)
        try:
            receipt = self.api.create_sale(items, paid=True, idempotency_key=reference, payment_method="card")
        except Exception as first_sale_error:
            # A socket timeout can happen after the API committed the receipt. Retry the
            # exact same idempotency key once before voiding a payment that may already
            # have a valid, paid receipt on the server.
            try:
                receipt = self.api.create_sale(items, paid=True, idempotency_key=reference, payment_method="card")
            except Exception as retry_error:
                try:
                    void_payment(amount, reference, payment["transaction_id"], settings)
                except Exception as void_error:
                    raise RuntimeError(
                        "کارت‌خوان پرداخت را تأیید کرده اما وضعیت فروش/لغو مبهم است. "
                        "شناسه تراکنش {} و مرجع {} را فوراً با مدیر/پرداخت‌یار بررسی کنید. "
                        "خطای ثبت: {}؛ خطای لغو: {}".format(
                            payment["transaction_id"], reference, retry_error, void_error
                        )
                    ) from retry_error
                raise RuntimeError(
                    "فروش تأیید نشد؛ پل پرداخت لغو تراکنش را تأیید کرد. مرجع: {}. علت: {}".format(
                        reference, retry_error
                    )
                ) from first_sale_error
        return {
            "receipt": receipt,
            "template": self._safe_invoice_template(),
            "payment_status": "paid",
            "transaction_id": payment["transaction_id"],
        }

    def _safe_invoice_template(self):
        try:
            return self.api.get_invoice_template()
        except Exception:
            return dict(DEFAULT_TEMPLATE)

    def _checkout_completed(self, result):
        receipt = result["receipt"]
        template = result.get("template") or DEFAULT_TEMPLATE
        paid = result.get("payment_status") == "paid"
        if paid:
            auto_print_invoice(receipt, template, self.window)
        self.clear_cart()
        self.window.show_confirmation(receipt, paid, result.get("transaction_id"))
        self.refresh_catalog()


class KioskWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Accounting App · کیوسک خودخدمت")
        self.setMinimumSize(1000, 680)
        self.resize(1280, 800)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(stylesheet("light"))
        self.local_settings = QSettings("AccountingApp", "SelfServiceKiosk")
        self.api = None
        self.current_user = None
        self._workers = {}
        self._callbacks = {}
        self._authorized_exit = False

        self.stack = QStackedWidget(self)
        self.setup_page = KioskSetupPage(self)
        self.shop_page = KioskShopPage(self)
        self.loading = QLabel("در حال اتصال امن به سرور…")
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading.setObjectName("PageTitle")
        self.stack.addWidget(self.loading)
        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.shop_page)
        self.setCentralWidget(self.stack)

        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+Alt+S"), self)
        self.settings_shortcut.activated.connect(self.open_protected_settings)
        self.exit_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Q"), self)
        self.exit_shortcut.activated.connect(self.request_exit)

        self._boot()

    def _boot(self):
        configured = self.local_settings.value("configured", False, type=bool)
        server_url = self.local_settings.value("server_url", "http://127.0.0.1:8000", type=str)
        kiosk_username = self.local_settings.value("kiosk_username", "", type=str)
        password = None
        if configured and keyring is not None and kiosk_username:
            try:
                password = keyring.get_password(KIOSK_KEYRING_SERVICE, kiosk_username)
            except Exception:
                password = None
        if configured and password:
            self.stack.setCurrentWidget(self.loading)
            self.showFullScreen()
            self.run_api(
                lambda: self._automatic_login(server_url, kiosk_username, password),
                self._auto_login_complete,
                failure=self._auto_login_failed,
            )
        else:
            self.setup_page.prefill()
            self.stack.setCurrentWidget(self.setup_page)
            self.show()

    def _automatic_login(self, server_url, username, password):
        api = AccountingApiClient(server_url)
        payload = api.login(username, password, client_name="Self-service kiosk")
        return {"api": api, "payload": payload}

    def _auto_login_complete(self, result):
        api, payload = result["api"], result["payload"]
        user = payload.get("user") or {}
        if payload.get("status") != "active" or not payload.get("access_token"):
            self._auto_login_failed("ورود حساب کیوسک فعال نیست؛ مدیر باید تنظیمات را بررسی کند.")
            return
        if not (
            can_access(user, "sales", "create") and can_access(user, "products", "read")
        ):
            self._auto_login_failed("مجوزهای حساب کیوسک معتبر نیست.")
            return
        self.api, self.current_user = api, user
        self._enter_shop()

    def _auto_login_failed(self, error):
        self.setup_page.prefill()
        self.setup_page.status.setText("اتصال/ورود خودکار انجام نشد: {}".format(error))
        self.stack.setCurrentWidget(self.setup_page)
        self.showNormal()

    def setup_completed(self, result):
        username = result["kiosk_username"]
        password = result["kiosk_password"]
        if keyring is None:
            self.setup_page.status.setText("مخزن امن سیستم‌عامل در دسترس نیست؛ تنظیمات ذخیره نشد.")
            return
        try:
            keyring.set_password(KIOSK_KEYRING_SERVICE, username, password)
        except Exception as exc:
            self.setup_page.status.setText(
                "ذخیره امن رمز کیوسک در سیستم‌عامل ناموفق بود؛ برای امنیت، حالت کیوسک فعال نشد: {}".format(exc)
            )
            return
        self.local_settings.setValue("configured", True)
        self.local_settings.setValue("server_url", result["server_url"])
        self.local_settings.setValue("company_name", result["company_name"])
        self.local_settings.setValue("kiosk_username", username)
        self.local_settings.setValue("allow_unpaid_orders", bool(result["allow_unpaid"]))
        self.local_settings.sync()
        self.api, self.current_user = result["api"], result["user"]
        self._enter_shop()

    def _enter_shop(self):
        company = self.local_settings.value("company_name", "فروشگاه", type=str)
        allow_unpaid = self.local_settings.value("allow_unpaid_orders", False, type=bool)
        self.shop_page.bind_session(self.api, self.current_user, company, allow_unpaid)
        self.stack.setCurrentWidget(self.shop_page)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.showFullScreen()
        self.shop_page.search.setFocus()

    def open_protected_settings(self):
        if self.api is None:
            self.stack.setCurrentWidget(self.setup_page)
            return
        dialog = ManagerUnlockDialog(self)
        if dialog.exec() != ManagerUnlockDialog.DialogCode.Accepted:
            return
        username, password = dialog.username.text().strip(), dialog.password.text()
        server_url = self.local_settings.value("server_url", "http://127.0.0.1:8000", type=str)
        self.run_api(
            lambda: self._verify_manager(server_url, username, password),
            lambda result: self._manager_unlocked(result, for_exit=False),
        )

    def request_exit(self):
        dialog = ManagerUnlockDialog(self)
        dialog.setWindowTitle("تأیید مدیر برای خروج")
        if dialog.exec() != ManagerUnlockDialog.DialogCode.Accepted:
            return
        username, password = dialog.username.text().strip(), dialog.password.text()
        server_url = self.local_settings.value("server_url", "http://127.0.0.1:8000", type=str)
        self.run_api(
            lambda: self._verify_manager(server_url, username, password),
            lambda result: self._manager_unlocked(result, for_exit=True),
        )

    @staticmethod
    def _verify_manager(server_url, username, password):
        api = AccountingApiClient(server_url)
        payload = api.login(username, password, client_name="Self-service kiosk manager")
        if payload.get("status") != "active" or not payload.get("access_token"):
            raise RuntimeError("نشست مدیر فعال نیست؛ ابتدا دستگاه را در پنل مدیر تأیید کنید.")
        user = payload.get("user") or {}
        if not user.get("is_admin"):
            raise RuntimeError("این عملیات فقط برای مدیر سیستم مجاز است.")
        return {"username": username, "password": password}

    def _manager_unlocked(self, result, for_exit=False):
        if for_exit:
            self._authorized_exit = True
            self.close()
            return
        self.setup_page.prefill(
            server_url=self.local_settings.value("server_url", "", type=str),
            company_name=self.local_settings.value("company_name", "", type=str),
            admin_username=result["username"],
            admin_password=result["password"],
            kiosk_username=self.local_settings.value("kiosk_username", "", type=str),
            kiosk_password=(
                keyring.get_password(
                    KIOSK_KEYRING_SERVICE,
                    self.local_settings.value("kiosk_username", "", type=str),
                ) if keyring is not None else ""
            ),
            allow_unpaid=self.local_settings.value("allow_unpaid_orders", False, type=bool),
        )
        self.stack.setCurrentWidget(self.setup_page)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.showNormal()
        self.resize(1050, 820)

    def show_confirmation(self, receipt, paid, transaction_id=None):
        page = QFrame()
        page.setObjectName("Card")
        page.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 50, 40, 50)
        layout.setSpacing(22)
        icon = QLabel("✓")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size:52px;font-weight:900;color:#17846D;")
        title = QLabel("خرید با موفقیت ثبت شد" if paid else "سفارش ثبت شد")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_text = "پرداخت توسط پل پرداخت تأیید شد." if paid else "پرداخت‌نشده است؛ برای پرداخت و تحویل به باجه مراجعه کنید."
        subtitle = QLabel(sub_text)
        subtitle.setObjectName("PageSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reference = QLabel("شماره فاکتور: {}    ·    مبلغ: {:,.2f}".format(
            receipt.get("day_receipt_id", "—"), float(receipt.get("total_price") or 0)
        ))
        reference.setObjectName("MetricValue")
        reference.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(reference)
        if transaction_id:
            tx = QLabel("شناسه پرداخت: {}".format(transaction_id))
            tx.setObjectName("PageSubtitle")
            tx.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(tx)
        button = QPushButton("بازگشت به خرید")
        button.setObjectName("PrimaryButton")
        button.setMinimumHeight(56)
        button.clicked.connect(lambda: self._return_to_shop(page))
        layout.addWidget(button)
        layout.addStretch(1)
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        QTimer.singleShot(18000, lambda: self._return_to_shop(page))

    def _return_to_shop(self, page):
        if page is not None:
            self.stack.removeWidget(page)
            page.deleteLater()
        if self.stack.count() > 2:
            self.stack.setCurrentWidget(self.shop_page)
        self.shop_page.search.setFocus()

    def run_api(self, operation, on_success, *, failure=None, busy=None):
        ticket = uuid.uuid4().hex
        worker = ApiWorker(operation, ticket, parent=self)
        self._workers[ticket] = worker
        self._callbacks[ticket] = (on_success, failure, busy)
        worker.succeeded.connect(self._worker_success)
        worker.failed.connect(self._worker_failure)
        worker.finished.connect(lambda: self._cleanup_worker(ticket))
        if busy:
            busy.setEnabled(False)
        worker.start()

    @Slot(str, object)
    def _worker_success(self, ticket, result):
        callback = self._callbacks.pop(ticket, None)
        if callback:
            success, _failure, busy = callback
            if busy:
                busy.setEnabled(True)
            success(result)

    @Slot(str, object)
    def _worker_failure(self, ticket, error):
        callback = self._callbacks.pop(ticket, None)
        if callback:
            _success, failure, busy = callback
            if busy:
                busy.setEnabled(True)
            if failure:
                failure(error)
            else:
                QMessageBox.warning(self, "خطای کیوسک", str(error))

    def _cleanup_worker(self, ticket):
        worker = self._workers.pop(ticket, None)
        if worker:
            worker.deleteLater()

    def closeEvent(self, event):
        if not self._authorized_exit and self.stack.currentWidget() is self.shop_page:
            event.ignore()
            return
        for worker in list(self._workers.values()):
            if worker.isRunning():
                worker.wait(35000)
        event.accept()


def main():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Accounting App Kiosk")
    window = KioskWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
