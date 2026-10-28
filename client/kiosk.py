"""Fullscreen self-service kiosk with first-run configuration and manager-protected settings."""
import os
import uuid

from PySide6.QtCore import Qt, Slot, QSettings, QTimer, QEvent, QObject
from PySide6.QtGui import QKeySequence, QShortcut, QPixmap
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

try:
    import keyring
except ImportError:
    keyring = None

from client.api_client import AccountingApiClient, ApiError
from client.payment_terminal import (
    PaymentTerminalError, authorize_payment, void_payment,
)
from client.ui.device_settings import DeviceSettingsDialog, device_settings
from client.ui.invoice_dialog import auto_print_invoice
from client.ui.invoice_render import DEFAULT_TEMPLATE
from client.ui.permissions import can_access
from client.ui.theme import set_design_config, stylesheet
from client.ui.touch_keyboard import TouchKeyboardDialog
from client.ui.worker import ApiWorker


KIOSK_KEYRING_SERVICE = "Accounting App Self-service Kiosk"
KIOSK_GRANTS = "role:kiosk;products:r;categories:r;sales:c;receipts:r;invoices:r;kiosk:r"


class _LineEditFocusTracker(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn and isinstance(watched, QLineEdit):
            self.owner._keyboard_target = watched
        return False


def _track_input_focus(owner, *fields):
    owner._keyboard_target = fields[0] if fields else None
    owner._keyboard_focus_tracker = _LineEditFocusTracker(owner)
    for field in fields:
        field.installEventFilter(owner._keyboard_focus_tracker)


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
        _track_input_focus(self, self.username, self.password)
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
        target = self._keyboard_target
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
        _track_input_focus(
            self, self.server_url, self.company_name, self.admin_username, self.admin_password,
            self.kiosk_username, self.kiosk_password,
        )
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
        self.setMinimumWidth(480)

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
        target = self._keyboard_target
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

        # Seed a usable first-run policy once only. Later admin-selected products and
        # an intentional disabled state must never be overwritten by this launcher.
        kiosk_settings = api.get_kiosk_settings()
        if not kiosk_settings.get("initialized"):
            all_products = []
            page = 1
            while True:
                batch = api.list_products_page(page=page, page_size=200)
                items = list(batch.get("items") or [])
                all_products.extend(items)
                total = int(batch.get("total", len(all_products)))
                if not items or len(all_products) >= total or len(items) < 200:
                    break
                page += 1
            company_profile = api.get_company_profile()
            product_ids = [item["id"] for item in all_products if item.get("id")]
            api.save_kiosk_settings(
                active=bool(product_ids),
                allowed_product_ids=product_ids,
                receipt_history_hours=int(kiosk_settings.get("receipt_history_hours", 48)),
                cafe_seat_selection=bool(company_profile.get("business_profile") == "cafe"),
                allow_unpaid_orders=bool(values["allow_unpaid"]),
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
        kiosk_config = api.get_kiosk_config()
        return {
            "api": api,
            "kiosk_config": kiosk_config,
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


class KioskConnectionPage(QFrame):
    """Shown at every launch so the operator can verify/edit connection settings."""
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("AppRoot")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)
        card = QFrame()
        card.setObjectName("Card")
        card.setMaximumWidth(680)
        card.setMinimumWidth(0)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 24)
        card_layout.setSpacing(14)
        brand = QLabel("Accounting App")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet("font-size:26px;font-weight:900;color:#3157A4;")
        title = QLabel("اتصال کیوسک")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel("تنظیمات اتصال را بررسی کنید، سپس برای ورود به صفحه خرید روی «اتصال و شروع» بزنید.")
        description.setObjectName("PageSubtitle")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(brand)
        card_layout.addWidget(title)
        card_layout.addWidget(description)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.server_url = QLineEdit()
        self.server_url.setPlaceholderText("https://accounting.example.com")
        self.username = QLineEdit()
        self.username.setPlaceholderText("حساب مخصوص کیوسک")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("رمز حساب کیوسک")
        _track_input_focus(self, self.server_url, self.username, self.password)
        form.addRow("نشانی سرور", self.server_url)
        form.addRow("نام کاربری کیوسک", self.username)
        form.addRow("رمز عبور", self.password)
        card_layout.addLayout(form)
        self.keyboard_button = QPushButton("⌨ صفحه‌کلید لمسی")
        self.keyboard_button.clicked.connect(self.show_keyboard)
        card_layout.addWidget(self.keyboard_button)
        device_row = QHBoxLayout()
        self.device_button = QPushButton("تنظیم کارت‌خوان / چاپگر")
        self.device_button.clicked.connect(lambda: DeviceSettingsDialog(self, kiosk=True).exec())
        self.manager_button = QPushButton("تنظیمات مدیر")
        self.manager_button.clicked.connect(self.window.open_protected_settings)
        self.exit_button = QPushButton("خروج از برنامه")
        self.exit_button.clicked.connect(self.window.close)
        device_row.addWidget(self.device_button)
        device_row.addWidget(self.manager_button)
        device_row.addWidget(self.exit_button)
        card_layout.addLayout(device_row)
        self.connect_button = QPushButton("اتصال و شروع خرید  ←")
        self.connect_button.setObjectName("PrimaryButton")
        self.connect_button.setMinimumHeight(52)
        self.connect_button.clicked.connect(self.connect)
        card_layout.addWidget(self.connect_button)
        self.status = QLabel("")
        self.status.setObjectName("PageSubtitle")
        self.status.setWordWrap(True)
        card_layout.addWidget(self.status)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

    def prefill(self):
        self.server_url.setText(self.window.local_settings.value(
            "server_url", os.environ.get("ACCOUNTING_APP_API_URL", "http://127.0.0.1:8000"), type=str
        ))
        self.username.setText(self.window.local_settings.value("kiosk_username", "selfservice_kiosk", type=str))
        password = None
        if keyring is not None:
            try:
                password = keyring.get_password(KIOSK_KEYRING_SERVICE, self.username.text())
            except Exception:
                password = None
        self.password.setText(password or "")
        if not self.window.local_settings.value("configured", False, type=bool):
            self.status.setText("این دستگاه هنوز راه‌اندازی نشده است.")
        elif not password:
            self.status.setText("رمز کیوسک در مخزن امن پیدا نشد؛ رمز را وارد کنید یا تنظیمات مدیر را باز کنید.")
        self.window.load_shared_appearance(self.server_url.text())

    def show_keyboard(self):
        target = self._keyboard_target
        if not isinstance(target, QLineEdit):
            target = self.username
        TouchKeyboardDialog(target, self).exec()

    def connect(self):
        server_url = self.server_url.text().strip()
        username = self.username.text().strip()
        password = self.password.text()
        if not server_url or not username or not password:
            self.status.setText("نشانی سرور، نام کاربری و رمز عبور را تکمیل کنید.")
            return
        self.window.run_api(
            lambda: self.window._connect_existing_kiosk(server_url, username, password),
            self.window._connection_complete,
            failure=self._connect_failed,
            busy=self.connect_button,
        )

    def _connect_failed(self, error):
        if getattr(error, "status_code", None) == 403:
            self.status.setText(
                "مجوز حساب کیوسک قدیمی است؛ برای به‌روزرسانی دسترسی‌ها، مدیر سیستم باید وارد شود."
            )
            self.window.open_protected_settings()
            return
        self.status.setText(str(error))


class KioskShopPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.api = None
        self.user = None
        self.products = []
        self.categories = []
        self.cart = {}
        self.runtime_config = {}
        self.catalog_page = 1
        self.catalog_page_size = 24
        self.catalog_total = 0
        self.setObjectName("AppRoot")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QHBoxLayout(self)
        self.main_layout = root
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
        self.refresh_button = QPushButton("بازخوانی کالاها")
        self.refresh_button.clicked.connect(self.refresh_catalog)
        self.manager_settings_button = QPushButton("تنظیمات مدیر")
        self.manager_settings_button.clicked.connect(self.window.open_protected_settings)
        self.exit_button = QPushButton("خروج")
        self.exit_button.setObjectName("DangerButton")
        self.exit_button.clicked.connect(self.window.request_exit)
        heading.addWidget(self.refresh_button)
        heading.addWidget(self.manager_settings_button)
        heading.addWidget(self.exit_button)
        catalog.addLayout(heading)

        filters = QHBoxLayout()
        self.category = QComboBox()
        self.category.setMinimumHeight(48)
        self.category.setMinimumWidth(180)
        self.category.currentIndexChanged.connect(self._category_changed)
        category_label = QLabel("دسته‌بندی")
        category_label.setObjectName("PageSubtitle")
        filters.addWidget(category_label)
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
        catalog_pager = QHBoxLayout()
        self.catalog_previous = QPushButton("صفحه قبل")
        self.catalog_previous.clicked.connect(lambda: self._change_catalog_page(-1))
        self.catalog_page_label = QLabel("صفحه ۱")
        self.catalog_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.catalog_page_label.setObjectName("PageSubtitle")
        self.catalog_next = QPushButton("صفحه بعد")
        self.catalog_next.clicked.connect(lambda: self._change_catalog_page(1))
        catalog_pager.addWidget(self.catalog_previous)
        catalog_pager.addWidget(self.catalog_page_label, 1)
        catalog_pager.addWidget(self.catalog_next)
        catalog.addLayout(catalog_pager)
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

        self.seat_row = QWidget()
        seat_layout = QHBoxLayout(self.seat_row)
        seat_layout.setContentsMargins(0, 0, 0, 0)
        seat_label = QLabel("شماره صندلی / میز")
        seat_label.setObjectName("PageSubtitle")
        self.seat_number = QComboBox()
        self.seat_number.setMinimumHeight(44)
        self.seat_number.addItem("انتخاب صندلی…", None)
        for seat in range(1, 31):
            self.seat_number.addItem("صندلی {}".format(seat), str(seat))
        seat_layout.addWidget(seat_label)
        seat_layout.addWidget(self.seat_number, 1)
        self.seat_row.hide()
        cart_layout.addWidget(self.seat_row)
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

    def bind_session(self, api, user, company_name, kiosk_config=None):
        self.api = api
        self.user = user
        self.runtime_config = dict(kiosk_config or {})
        self.allow_unpaid = bool(self.runtime_config.get("allow_unpaid_orders", False))
        self.shop_title.setText(company_name or "انتخاب محصولات")
        self._update_checkout_label()
        self.seat_row.setVisible(bool(self.runtime_config.get("cafe_seat_selection")))
        self.refresh_catalog()

    def refresh_catalog(self, *_args):
        if not self.api:
            return
        self.refresh_button.setEnabled(False)
        category_id = self.category.currentData()
        page = self.catalog_page
        self.window.run_api(
            lambda: self._load_catalog(category_id, page),
            self._catalog_loaded,
            busy=self.refresh_button,
        )

    def _category_changed(self, *_args):
        self.catalog_page = 1
        self.refresh_catalog()

    def _change_catalog_page(self, delta):
        page_count = max(1, (self.catalog_total + self.catalog_page_size - 1) // self.catalog_page_size)
        requested = self.catalog_page + delta
        if 1 <= requested <= page_count:
            self.catalog_page = requested
            self.refresh_catalog()

    def _load_catalog(self, category_id, page):
        config = self.api.get_kiosk_config()
        if not config.get("active"):
            raise RuntimeError("کیوسک در پنل مدیر غیرفعال است. از برنامه حسابداری > مدیریت کیوسک آن را فعال کنید.")
        if not config.get("allowed_product_ids"):
            raise RuntimeError("هنوز محصولی برای کیوسک انتخاب نشده است. در پنل مدیر، محصولات کیوسک را مشخص کنید.")
        data = self.api.list_products_page(
            category_id=category_id, page=page, page_size=self.catalog_page_size
        )
        products = list(data.get("items") or [])
        # Image downloads happen on the API worker. QPixmap creation happens later on the GUI thread.
        for product in products:
            if product.get("image_path"):
                try:
                    product["_image_bytes"] = self.api.get_product_image_bytes(product["id"])
                except Exception:
                    product["_image_bytes"] = None
        categories_data = self.api.list_categories_page(page=1, page_size=200)
        return {
            "products": products,
            "categories": categories_data.get("items") or [],
            "config": config,
            "page": int(data.get("page", page)),
            "page_size": int(data.get("page_size", self.catalog_page_size)),
            "total": int(data.get("total", len(products))),
        }

    def _catalog_loaded(self, data):
        self.products = list(data.get("products") or [])
        self.categories = list(data.get("categories") or [])
        self.runtime_config = dict(data.get("config") or self.runtime_config)
        self.allow_unpaid = bool(self.runtime_config.get("allow_unpaid_orders", False))
        self.seat_row.setVisible(bool(self.runtime_config.get("cafe_seat_selection")))
        self._update_checkout_label()
        self.catalog_page = int(data.get("page", self.catalog_page))
        self.catalog_page_size = int(data.get("page_size", self.catalog_page_size))
        self.catalog_total = int(data.get("total", len(self.products)))
        current_category = self.category.currentData()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("همهٔ دسته‌ها", None)
        for item in self.categories:
            self.category.addItem(item.get("name", "—"), item.get("id"))
        index = self.category.findData(current_category)
        self.category.setCurrentIndex(index if index >= 0 else 0)
        self.category.blockSignals(False)
        page_count = max(1, (self.catalog_total + self.catalog_page_size - 1) // self.catalog_page_size)
        self.catalog_page_label.setText("صفحه {} از {} · {} محصول".format(
            self.catalog_page, page_count, self.catalog_total
        ))
        self.catalog_previous.setEnabled(self.catalog_page > 1)
        self.catalog_next.setEnabled(self.catalog_page < page_count)
        self._render_products()

    def _update_checkout_label(self):
        terminal_mode = device_settings().get("terminal_mode")
        if terminal_mode == "tcp":
            self.checkout_button.setText("پرداخت با کارت‌خوان و دریافت رسید")
        elif self.allow_unpaid:
            self.checkout_button.setText("ثبت سفارش و دریافت کد")
        else:
            self.checkout_button.setText("پرداخت / تنظیم کارت‌خوان")

    def _render_products(self):
        _clear_layout(self.product_grid)
        columns = 2 if self.height() > self.width() else (3 if self.width() < 1300 else 4)
        for index, product in enumerate(self.products):
            card = QFrame()
            card.setObjectName("KioskProductCard")
            card.setFrameShape(QFrame.Shape.NoFrame)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.setSpacing(8)

            image = QLabel()
            image.setObjectName("KioskProductImage")
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setMinimumHeight(64)
            image.setMaximumHeight(92)
            pixmap = QPixmap()
            image_bytes = product.get("_image_bytes")
            if image_bytes and pixmap.loadFromData(image_bytes):
                image.setPixmap(pixmap.scaled(
                    120, 82, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            else:
                image.setText("▦")
            card_layout.addWidget(image)

            title = QLabel(str(product.get("name") or "کالا"))
            title.setObjectName("KioskProductTitle")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setWordWrap(True)
            title.setMinimumHeight(42)
            card_layout.addWidget(title)

            price = QLabel("{:,.2f}".format(float(product.get("sell_price") or 0)))
            price.setObjectName("KioskProductPrice")
            price.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(price)

            tracked = bool(product.get("track_stock"))
            stock = float(product.get("stock_quantity") or 0)
            badge = QLabel(
                "ناموجود" if tracked and stock <= 0
                else ("موجودی: {:g}".format(stock) if tracked else "آماده فروش")
            )
            badge.setObjectName("KioskStockBadge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if tracked and stock <= 0:
                badge.setProperty("outOfStock", True)
            card_layout.addWidget(badge)

            add = QPushButton("افزودن به سبد  +")
            add.setObjectName("KioskAddButton")
            add.setMinimumHeight(44)
            available = not (tracked and stock <= 0)
            add.setEnabled(available)
            card.setProperty("outOfStock", bool(not available))
            add.clicked.connect(lambda _checked=False, item=product: self.add_to_cart(item))
            card_layout.addWidget(add)
            self.product_grid.addWidget(card, index // columns, index % columns)
        self.product_grid.setRowStretch((len(self.products) // columns) + 1, 1)
        if not self.products:
            empty = QLabel("در این دسته محصول مجازی برای کیوسک موجود نیست.")
            empty.setObjectName("PageSubtitle")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        seat_number = self.seat_number.currentData() if self.seat_row.isVisible() else None
        if self.seat_row.isVisible() and not seat_number:
            QMessageBox.information(self, "شماره صندلی", "برای ثبت سفارش کافه، ابتدا شماره صندلی یا میز را انتخاب کنید.")
            self.seat_number.setFocus()
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
            lambda: self._checkout_operation(items, settings, mode, seat_number),
            self._checkout_completed,
            busy=self.checkout_button,
        )

    def _checkout_operation(self, items, settings, mode, seat_number=None):
        if mode != "tcp":
            receipt = self.api.create_sale(
                items, paid=False, payment_method="unpaid", seat_number=seat_number
            )
            return {
                "receipt": receipt,
                "template": self._safe_invoice_template(),
                "payment_status": "unpaid",
                "transaction_id": None,
            }

        quote = self.api.quote_sale(items, paid=True, payment_method="card", seat_number=seat_number)
        amount = str(quote.get("total") or "0")
        reference = uuid.uuid4().hex
        payment = authorize_payment(amount, reference, settings)
        try:
            receipt = self.api.create_sale(items, paid=True, idempotency_key=reference, payment_method="card", seat_number=seat_number)
        except Exception as first_sale_error:
            # A socket timeout can happen after the API committed the receipt. Retry the
            # exact same idempotency key once before voiding a payment that may already
            # have a valid, paid receipt on the server.
            try:
                receipt = self.api.create_sale(items, paid=True, idempotency_key=reference, payment_method="card", seat_number=seat_number)
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
        self.seat_number.setCurrentIndex(0)
        self.window.show_confirmation(receipt, paid, result.get("transaction_id"))
        self.refresh_catalog()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "main_layout"):
            return
        portrait = self.height() > self.width()
        self.main_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if portrait else QBoxLayout.Direction.LeftToRight
        )
        if hasattr(self, "product_grid"):
            self._render_products()


class KioskWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Accounting App · کیوسک خودخدمت")
        self.setMinimumSize(480, 480)
        self.resize(1280, 800)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._kiosk_stylesheet = """
            QFrame#KioskProductCard { background:#FFFFFF; border:1px solid #DDE5F0; border-radius:16px; }
            QLabel#KioskProductImage { background:#F1F5FB; color:#5D79A3; border-radius:12px; font-size:44px; font-weight:800; }
            QLabel#KioskProductTitle { color:#1F2937; font-size:15px; font-weight:750; }
            QLabel#KioskProductPrice { color:#244EAA; font-size:20px; font-weight:900; }
            QLabel#KioskStockBadge { color:#18715D; background:#E7F6F0; border-radius:9px; padding:4px; font-size:11px; }
            QLabel#KioskStockBadge[outOfStock="true"] { color:#9B1C1C; background:#FCE8E6; }
            QFrame#KioskProductCard[outOfStock="true"] { border-color:#E8C5C2; }
            QPushButton#KioskAddButton { color:white; background:#3157A4; border:0; border-radius:10px; font-size:13px; font-weight:800; }
            QPushButton#KioskAddButton:hover { background:#25498D; }
            QPushButton#KioskAddButton:disabled { background:#E5E7EB; color:#9CA3AF; }
        """
        self.setStyleSheet(stylesheet("light") + self._kiosk_stylesheet)
        self.local_settings = QSettings("AccountingApp", "SelfServiceKiosk")
        self.api = None
        self.current_user = None
        self._workers = {}
        self._callbacks = {}
        self._authorized_exit = False
        self._appearance_url_requested = None

        self.stack = QStackedWidget(self)
        self.setup_page = KioskSetupPage(self)
        self.shop_page = KioskShopPage(self)
        self.loading = QLabel("در حال اتصال امن به سرور…")
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading.setObjectName("PageTitle")
        self.connection_page = KioskConnectionPage(self)
        self.stack.addWidget(self.loading)
        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.connection_page)
        self.stack.addWidget(self.shop_page)
        self.setCentralWidget(self.stack)

        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+Alt+S"), self)
        self.settings_shortcut.activated.connect(self.open_protected_settings)
        self.exit_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Q"), self)
        self.exit_shortcut.activated.connect(self.request_exit)

        self._boot()

    def load_shared_appearance(self, url):
        """Fetch non-sensitive shared design settings asynchronously for the kiosk UI."""
        url = str(url or "").strip()
        if not url or url == self._appearance_url_requested:
            return
        try:
            api = AccountingApiClient(url)
        except ValueError:
            return
        self._appearance_url_requested = url
        self.run_api(
            api.get_appearance_settings,
            self._apply_shared_appearance,
            failure=lambda _error: None,
        )

    def _apply_shared_appearance(self, values):
        if not isinstance(values, dict):
            return
        set_design_config(values)
        self.setStyleSheet(stylesheet("light") + self._kiosk_stylesheet)

    def _boot(self):
        configured = self.local_settings.value("configured", False, type=bool)
        if configured:
            # Connection settings are deliberately presented on every launch.
            self.connection_page.prefill()
            self.stack.setCurrentWidget(self.connection_page)
            self.showNormal()
        else:
            self.setup_page.prefill()
            self.stack.setCurrentWidget(self.setup_page)
            self.showNormal()

    def _connect_existing_kiosk(self, server_url, username, password):
        api = AccountingApiClient(server_url)
        payload = api.login(username, password, client_name="Self-service kiosk")
        if payload.get("status") != "active" or not payload.get("access_token"):
            raise RuntimeError("ورود حساب کیوسک فعال نیست؛ مدیر باید درخواست ورود را تأیید کند.")
        user = payload.get("user") or {}
        required_permissions = (
            ("sales", "create"), ("products", "read"), ("categories", "read"),
            ("receipts", "read"), ("invoices", "read"), ("kiosk", "read"),
        )
        if not all(can_access(user, resource, action) for resource, action in required_permissions):
            raise ApiError(
                403,
                "حساب کیوسک به مجوزهای جدید نیاز دارد؛ ورود مدیر برای به‌روزرسانی آن لازم است.",
            )
        config = api.get_kiosk_config()
        if not config.get("active"):
            raise RuntimeError("کیوسک در پنل مدیر غیرفعال است. از برنامه حسابداری > مدیریت کیوسک آن را فعال کنید.")
        if not config.get("allowed_product_ids"):
            raise RuntimeError("هیچ محصولی برای کیوسک انتخاب نشده است. در صفحه مدیریت کیوسک محصولات را انتخاب کنید.")
        try:
            appearance = api.get_appearance_settings()
        except Exception:
            appearance = None
        return {
            "api": api, "user": user, "config": config,
            "server_url": server_url, "username": username,
            "appearance": appearance,
        }

    def _connection_complete(self, result):
        self.api, self.current_user = result["api"], result["user"]
        self.local_settings.setValue("server_url", result["server_url"])
        self.local_settings.setValue("kiosk_username", result["username"])
        self.local_settings.setValue("configured", True)
        self.local_settings.sync()
        self._apply_shared_appearance(result.get("appearance"))
        if keyring is not None and self.connection_page.password.text():
            try:
                keyring.set_password(KIOSK_KEYRING_SERVICE, result["username"], self.connection_page.password.text())
            except Exception:
                pass
        self._enter_shop(result["config"])

    def _automatic_login(self, server_url, username, password):
        api = AccountingApiClient(server_url)
        payload = api.login(username, password, client_name="Self-service kiosk")
        config = api.get_kiosk_config() if payload.get("status") == "active" else {}
        try:
            appearance = api.get_appearance_settings()
        except Exception:
            appearance = None
        return {"api": api, "payload": payload, "config": config, "appearance": appearance}

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
        config = result.get("config") or {}
        if not config.get("active") or not config.get("allowed_product_ids"):
            self._auto_login_failed("کیوسک در پنل مدیر فعال نیست یا محصولی برای نمایش انتخاب نشده است.")
            return
        self.api, self.current_user = api, user
        try:
            appearance = api.get_appearance_settings()
        except Exception:
            appearance = None
        self._apply_shared_appearance(appearance)
        self._enter_shop(config)

    def _auto_login_failed(self, error):
        self.connection_page.prefill()
        self.connection_page.status.setText("اتصال/ورود انجام نشد: {}".format(error))
        self.stack.setCurrentWidget(self.connection_page)
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
        self._enter_shop(result.get("kiosk_config"))

    def _enter_shop(self, kiosk_config=None):
        kiosk_config = dict(kiosk_config or {})
        company = kiosk_config.get("company_name") or self.local_settings.value("company_name", "فروشگاه", type=str)
        if not kiosk_config.get("active") or not kiosk_config.get("allowed_product_ids"):
            self.connection_page.prefill()
            self.connection_page.status.setText(
                "کیوسک هنوز فعال نشده یا محصولی انتخاب نشده است. تنظیمات را در پنل مدیریت بررسی کنید."
            )
            self.stack.setCurrentWidget(self.connection_page)
            self.showNormal()
            return
        self.shop_page.bind_session(self.api, self.current_user, company, kiosk_config)
        self.stack.setCurrentWidget(self.shop_page)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.showFullScreen()

    def open_protected_settings(self):
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
        reference_text = "شماره فاکتور: {}    ·    مبلغ: {:,.2f}".format(
            receipt.get("day_receipt_id", "—"), float(receipt.get("total_price") or 0)
        )
        if receipt.get("seat_number"):
            reference_text += "    ·    صندلی / میز: {}".format(receipt["seat_number"])
        reference = QLabel(reference_text)
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
        self.shop_page.setFocus()

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
