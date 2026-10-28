"""API connection, login, and pending-session approval screen."""
import os
import socket

try:
    import keyring
except ImportError:
    keyring = None

from PySide6.QtCore import Qt, QTimer, QSettings, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget, QProgressBar,
)

from client.api_client import AccountingApiClient
from client.ui.setup_wizard import SetupWizard
from client.ui.theme import stylesheet
from client.ui.worker import ApiWorker


class AuthPage(QWidget):
    authenticated = Signal(object)
    api_changed = Signal(object)
    theme_changed = Signal(str)

    def __init__(self, mode="light", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.api = None
        self.local_settings = QSettings("AccountingApp", "DesktopClient")
        self.setup_required = False
        self._restore_attempted_for_url = None
        self.pending_ticket = None
        self._poll_running = False
        self._workers = {}
        self.setObjectName("AuthRoot")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(36, 30, 36, 30)
        outer.setSpacing(30)

        hero = QFrame()
        hero.setObjectName("Sidebar")
        hero.setMinimumWidth(300)
        hero.setMaximumWidth(410)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 28, 28, 28)
        hero_layout.setSpacing(15)
        brandmark = QLabel("A")
        brandmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brandmark.setFixedSize(58, 58)
        brandmark.setStyleSheet("background:#4169E1;color:white;border-radius:17px;font-size:30px;font-weight:900;")
        hero_layout.addWidget(brandmark, 0, Qt.AlignmentFlag.AlignRight)
        self.hero_title = QLabel("حسابداری،\nشفاف و متمرکز")
        self.hero_title.setStyleSheet("font-size:28px;font-weight:900;color:white;")
        self.hero_title.setWordWrap(True)
        hero_layout.addWidget(self.hero_title)
        hero_sub = QLabel("مدیریت فروش، موجودی، رسیدها، کاربران و گزارش‌ها از یک محیط یکپارچه.")
        hero_sub.setStyleSheet("font-size:14px;color:#B6C5DC;")
        hero_sub.setWordWrap(True)
        hero_layout.addWidget(hero_sub)
        hero_layout.addSpacing(12)
        for title, subtitle in (
            ("امنیت در سمت سرور", "نشست‌ها و مجوزها در هر درخواست بررسی می‌شوند."),
            ("کنترل دسترسی مدیر", "ورود دستگاه‌های جدید قابل تأیید یا لغو است."),
            ("دادهٔ مرکزی", "کلاینت مستقیماً به فایل دیتابیس دسترسی ندارد."),
        ):
            item = QFrame()
            item.setStyleSheet("background:rgba(255,255,255,0.07);border-radius:10px;")
            il = QVBoxLayout(item)
            il.setContentsMargins(13, 11, 13, 11)
            label = QLabel("✓  " + title)
            label.setStyleSheet("font-weight:800;color:#FFFFFF;")
            desc = QLabel(subtitle)
            desc.setStyleSheet("color:#9FB0CA;")
            desc.setWordWrap(True)
            il.addWidget(label)
            il.addWidget(desc)
            hero_layout.addWidget(item)
        hero_layout.addStretch(1)
        footer = QLabel("ACCOUNTING APP  ·  SECURE CLIENT")
        footer.setStyleSheet("font-size:10px;letter-spacing:1px;color:#7F92B0;")
        hero_layout.addWidget(footer)
        outer.addWidget(hero, 2)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 12, 8, 12)
        content_layout.setSpacing(18)
        header = QHBoxLayout()
        header.addStretch(1)
        self.theme_button = QPushButton("☾  تم تاریک")
        self.theme_button.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_button)
        content_layout.addLayout(header)
        content_layout.addStretch(1)

        self.card = QFrame()
        self.card.setObjectName("Card")
        self.card.setMaximumWidth(520)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(16)
        self.title = QLabel("ورود به حساب")
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel("برای ادامه، نشانی سرور را بررسی و وارد حساب خود شوید.")
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        card_layout.addWidget(self.title)
        card_layout.addWidget(self.subtitle)

        self.server_url = QLineEdit(os.environ.get("ACCOUNTING_APP_API_URL", "http://127.0.0.1:8000"))
        self.server_url.setPlaceholderText("https://accounting.example.com")
        self.server_url.setClearButtonEnabled(True)
        connect_row = QHBoxLayout()
        connect_row.addWidget(self.server_url, 1)
        self.connect_button = QPushButton("بررسی")
        self.connect_button.clicked.connect(self.connect_server)
        connect_row.addWidget(self.connect_button)
        card_layout.addWidget(QLabel("نشانی سرور"))
        card_layout.addLayout(connect_row)
        self.server_status = QLabel("●  هنوز به سروری وصل نشده‌اید")
        self.server_status.setObjectName("PageSubtitle")
        card_layout.addWidget(self.server_status)

        self.login_form = QWidget()
        login_layout = QFormLayout(self.login_form)
        self.username = QLineEdit()
        self.username.setPlaceholderText("نام کاربری")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self.login)
        self.client_name = QLineEdit(socket.gethostname() or "Desktop client")
        self.client_name.setPlaceholderText("نام این دستگاه")
        login_layout.addRow("نام کاربری", self.username)
        login_layout.addRow("رمز عبور", self.password)
        login_layout.addRow("نام دستگاه", self.client_name)
        card_layout.addWidget(self.login_form)

        self.remember_session_checkbox = QCheckBox("بازیابی نشست این دستگاه در ورود بعدی")
        self.remember_session_checkbox.setChecked(
            self.local_settings.value("remember_session", True, type=bool)
        )
        self.remember_session_checkbox.toggled.connect(self._remember_setting_changed)
        card_layout.addWidget(self.remember_session_checkbox)

        self.login_button = QPushButton("ورود امن  ←")
        self.login_button.setObjectName("PrimaryButton")
        self.login_button.clicked.connect(self.login)
        card_layout.addWidget(self.login_button)
        self.setup_button = QPushButton("راه‌اندازی اولیه و ساخت مدیر")
        self.setup_button.clicked.connect(self.open_setup_wizard)
        self.setup_button.hide()
        card_layout.addWidget(self.setup_button)

        self.pending_panel = QFrame()
        self.pending_panel.setObjectName("Card")
        pending_layout = QVBoxLayout(self.pending_panel)
        self.pending_icon = QLabel("◷")
        self.pending_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pending_icon.setStyleSheet("font-size:34px;color:#4169E1;")
        self.pending_label = QLabel("در انتظار تأیید مدیر")
        self.pending_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pending_label.setStyleSheet("font-size:18px;font-weight:800;")
        self.pending_detail = QLabel("درخواست ورود برای این دستگاه ثبت شد. پس از تأیید مدیر، اتصال خودکار ادامه پیدا می‌کند.")
        self.pending_detail.setWordWrap(True)
        self.pending_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pending_progress = QProgressBar()
        self.pending_progress.setRange(0, 0)
        self.cancel_pending_button = QPushButton("لغو انتظار")
        self.cancel_pending_button.clicked.connect(self.cancel_pending)
        pending_layout.addWidget(self.pending_icon)
        pending_layout.addWidget(self.pending_label)
        pending_layout.addWidget(self.pending_detail)
        pending_layout.addWidget(self.pending_progress)
        pending_layout.addWidget(self.cancel_pending_button)
        self.pending_panel.hide()
        card_layout.addWidget(self.pending_panel)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color:#D64045;")
        card_layout.addWidget(self.message)
        content_layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignHCenter)
        content_layout.addStretch(2)
        outer.addWidget(content, 3)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(2500)
        self.poll_timer.timeout.connect(self.poll_activation)
        self.setStyleSheet(stylesheet(mode))
        self.connect_server()

    def set_mode(self, mode):
        self.mode = mode
        self.setStyleSheet(stylesheet(mode))
        self.theme_button.setText("☀  تم روشن" if mode == "dark" else "☾  تم تاریک")

    def toggle_theme(self):
        next_mode = "light" if self.mode == "dark" else "dark"
        self.set_mode(next_mode)
        self.theme_changed.emit(next_mode)

    def _run(self, operation, success, *, failure=None, busy=None):
        worker = ApiWorker(operation, parent=self)
        self._workers[worker.ticket] = worker
        worker.succeeded.connect(success)
        worker.failed.connect(failure or self._default_failure)
        worker.finished.connect(lambda: self._cleanup(worker.ticket))
        if busy:
            busy.setEnabled(False)
        worker.start()
        if busy:
            ticket = worker.ticket
            worker.finished.connect(lambda: busy.setEnabled(True))

    @Slot(str, object)
    def _default_failure(self, _ticket, error):
        self.message.setText(str(error))
        self.server_status.setText("●  اتصال یا درخواست ناموفق بود")

    def _cleanup(self, ticket):
        worker = self._workers.pop(ticket, None)
        if worker:
            worker.deleteLater()

    def connect_server(self):
        self.stop_pending()
        self.message.clear()
        try:
            api = AccountingApiClient(self.server_url.text().strip())
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        self.api = api
        self.api_changed.emit(api)
        self.server_status.setText("●  در حال بررسی سرور...")
        def check():
            return api.setup_status()
        self._run(
            check,
            self._connection_ready,
            failure=self._connection_failed,
            busy=self.connect_button,
        )

    @Slot(str, object)
    def _connection_ready(self, _ticket, payload):
        self.setup_required = bool(payload.get("setup_required"))
        self.setup_button.setVisible(self.setup_required)
        self.login_form.setVisible(not self.setup_required)
        self.login_button.setVisible(not self.setup_required)
        self.title.setText("راه‌اندازی اولیه" if self.setup_required else "ورود به حساب")
        self.subtitle.setText(
            "برای شروع، حساب مدیر اصلی را بسازید."
            if self.setup_required else
            "نشست کاربری خود را با نام کاربری و رمز عبور آغاز کنید."
        )
        self.server_status.setText("●  سرور آماده است")
        self.server_status.setStyleSheet("color:#0F9D83;font-weight:700;")
        self._attempt_restore_session()

    @Slot(str, object)
    def _connection_failed(self, _ticket, error):
        self.server_status.setText("●  سرور در دسترس نیست")
        self.message.setText(str(error))

    @staticmethod
    def _keyring_account(server_url):
        return str(server_url or "").strip().rstrip("/")

    def _remember_setting_changed(self, enabled):
        self.local_settings.setValue("remember_session", bool(enabled))
        self.local_settings.sync()
        if not enabled:
            self.clear_remembered_session()

    def clear_remembered_session(self):
        if keyring is not None:
            try:
                keyring.delete_password(
                    "Accounting App Desktop Session",
                    self._keyring_account(self.server_url.text()),
                )
            except Exception:
                pass

    def _persist_session(self):
        if not self.remember_session_checkbox.isChecked():
            self.clear_remembered_session()
            return
        if keyring is None or self.api is None or not self.api.access_token:
            self.message.setText("ورود انجام شد، اما ذخیرهٔ امن نشست در این سیستم در دسترس نیست.")
            return
        try:
            keyring.set_password(
                "Accounting App Desktop Session",
                self._keyring_account(self.api.base_url),
                self.api.access_token,
            )
            self.local_settings.setValue("last_server_url", self.api.base_url)
            self.local_settings.sync()
        except Exception as exc:
            self.message.setText("ورود انجام شد، اما ذخیرهٔ امن نشست ناموفق بود: {}".format(exc))

    def _attempt_restore_session(self):
        if self.api is None or not self.remember_session_checkbox.isChecked() or keyring is None:
            return
        url = self._keyring_account(self.api.base_url)
        if self._restore_attempted_for_url == url:
            return
        self._restore_attempted_for_url = url
        try:
            token = keyring.get_password("Accounting App Desktop Session", url)
        except Exception:
            token = None
        if not token:
            return
        self.api.set_access_token(token)
        self.server_status.setText("●  در حال بازیابی نشست امن…")
        self.login_button.setEnabled(False)
        self._run(
            self.api.me,
            self._session_restored,
            failure=self._session_restore_failed,
        )

    @Slot(str, object)
    def _session_restored(self, _ticket, user):
        if not isinstance(user, dict) or not user.get("username"):
            self._session_restore_failed("", RuntimeError("پاسخ نشست معتبر نیست."))
            return
        self.password.clear()
        self.username.setText(user.get("username", ""))
        self.server_status.setText("●  نشست قبلی بازیابی شد")
        self.server_status.setStyleSheet("color:#0F9D83;font-weight:700;")
        self.login_button.setEnabled(True)
        self.authenticated.emit(user)

    @Slot(str, object)
    def _session_restore_failed(self, _ticket, error):
        status_code = getattr(error, "status_code", None)
        if status_code == 401:
            self.clear_remembered_session()
        if self.api is not None:
            self.api.clear_session()
        self.login_button.setEnabled(True)
        self.server_status.setText("●  ورود دوباره لازم است")
        self.message.setText("نشست ذخیره‌شده دیگر معتبر نیست؛ رمز عبور را وارد کنید." if status_code == 401 else
                             "نشست قبلی بازیابی نشد؛ اتصال را بررسی کنید. {}".format(error))

    def login(self):
        if self.api is None:
            self.connect_server()
            return
        username = self.username.text().strip()
        password = self.password.text()
        if len(username) < 4 or len(password) < 4:
            self.message.setText("نام کاربری و رمز عبور معتبر وارد کنید.")
            return
        api = self.api
        self.message.clear()
        self._run(
            lambda: api.login(username, password, self.client_name.text().strip() or "Desktop client"),
            self._login_result,
            busy=self.login_button,
        )

    @Slot(str, object)
    def _login_result(self, _ticket, payload):
        self.password.clear()
        if payload.get("status") == "active" and payload.get("user"):
            self.stop_pending()
            self._persist_session()
            self.authenticated.emit(payload["user"])
            return
        if payload.get("status") == "pending_activation" and payload.get("session_ticket"):
            self.pending_ticket = payload["session_ticket"]
            self.pending_panel.show()
            self.login_form.hide()
            self.login_button.hide()
            self.setup_button.hide()
            self.pending_detail.setText(payload.get("message") or "در انتظار فعال‌سازی توسط مدیر هستید.")
            self.server_status.setText("●  درخواست ورود ثبت شد؛ منتظر تأیید")
            self.poll_timer.start()
            return
        self.message.setText(payload.get("message") or "ورود تکمیل نشد.")

    def poll_activation(self):
        if not self.pending_ticket or self._poll_running or self.api is None:
            return
        self._poll_running = True
        api, ticket = self.api, self.pending_ticket
        self._run(
            lambda: api.check_session_status(ticket),
            self._activation_result,
            failure=self._activation_failed,
        )

    @Slot(str, object)
    def _activation_result(self, _ticket, payload):
        self._poll_running = False
        status = payload.get("status")
        if status == "pending_activation":
            return
        if status == "active" and payload.get("user"):
            self.stop_pending()
            self._persist_session()
            self.authenticated.emit(payload["user"])
            return
        self.stop_pending()
        self.pending_label.setText("ورود لغو شد")
        self.pending_detail.setText(payload.get("message") or "نشست دیگر قابل فعال‌سازی نیست.")
        self.pending_progress.setRange(0, 100)
        self.pending_progress.setValue(100)
        self.cancel_pending_button.setText("بازگشت به ورود")
        self.cancel_pending_button.setEnabled(True)

    @Slot(str, object)
    def _activation_failed(self, _ticket, error):
        self._poll_running = False
        self.pending_detail.setText("بررسی وضعیت انجام نشد: {}".format(error))

    def stop_pending(self):
        self.poll_timer.stop()
        self.pending_ticket = None
        self._poll_running = False
        self.pending_panel.hide()
        self.login_form.show()
        if not self.setup_required:
            self.login_button.show()
        self.cancel_pending_button.setText("لغو انتظار")
        self.pending_progress.setRange(0, 0)
        self.cancel_pending_button.setEnabled(True)

    def cancel_pending(self):
        self.stop_pending()
        self.message.setText("انتظار لغو شد؛ نشست در صورت نیاز توسط مدیر قابل لغو است.")

    def open_setup_wizard(self):
        if self.api is None:
            self.connect_server()
            return
        wizard = SetupWizard(self.api, self, self.mode)
        wizard.completed.connect(self._setup_complete)
        wizard.exec()

    @Slot(object)
    def _setup_complete(self, user):
        self.setup_required = False
        self.setup_button.hide()
        self._persist_session()
        self.authenticated.emit(user)
