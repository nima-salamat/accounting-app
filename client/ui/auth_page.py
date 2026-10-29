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
    QPushButton, QVBoxLayout, QWidget, QProgressBar, QScrollArea,
)

from client.api_client import AccountingApiClient
from client.ui.setup_wizard import SetupWizard
from client.ui.theme import set_design_config, stylesheet
from client.ui.icons import apply_button_icons
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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(8)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 0, 8, 0)
        content_layout.setSpacing(8)
        header = QHBoxLayout()
        header.addStretch(1)
        self.theme_button = QPushButton("☾  تم تاریک")
        self.theme_button.setToolTip("تغییر تم روشن / تاریک")
        self.theme_button.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_button)
        content_layout.addLayout(header)
        content_layout.addStretch(1)

        self.card = QFrame()
        self.card.setObjectName("AuthCard")
        self.card.setMaximumWidth(500)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(11)
        self.auth_eyebrow = QLabel("حساب کاربری شما")
        self.auth_eyebrow.setObjectName("AuthEyebrow")
        self.title = QLabel("ورود به حساب")
        self.title.setObjectName("AuthTitle")
        self.subtitle = QLabel("برای ادامه، به سرور حسابداری متصل شوید و با حساب خود وارد شوید.")
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        self.auth_eyebrow.hide()
        self.subtitle.hide()
        card_layout.addWidget(self.title)

        self.connection_panel = QFrame()
        self.connection_panel.setObjectName("AuthSection")
        connection_layout = QVBoxLayout(self.connection_panel)
        connection_layout.setContentsMargins(14, 12, 14, 12)
        connection_layout.setSpacing(9)
        connection_heading = QHBoxLayout()
        connection_title = QLabel("اتصال به سرور")
        connection_title.setObjectName("AuthSectionTitle")
        connection_hint = QLabel("IP یا دامنه به‌همراه پورت")
        connection_hint.setObjectName("PageSubtitle")
        connection_heading.addWidget(connection_title)
        connection_heading.addStretch(1)
        connection_heading.addWidget(connection_hint)
        connection_layout.addLayout(connection_heading)
        configured_url = os.environ.get("ACCOUNTING_APP_API_URL")
        last_server_url = self.local_settings.value("last_server_url", "", type=str)
        self.server_url = QLineEdit(configured_url or last_server_url or "http://127.0.0.1:8000")
        self.server_url.setObjectName("AuthInput")
        self.server_url.setPlaceholderText("https://accounting.example.com یا http://192.168.1.10:8000")
        self.server_url.setClearButtonEnabled(True)
        self.server_url.editingFinished.connect(self._store_server_url)
        connect_row = QHBoxLayout()
        connect_row.setSpacing(8)
        connect_row.addWidget(self.server_url, 1)
        self.connect_button = QPushButton("اتصال")
        self.connect_button.setObjectName("AuthConnectButton")
        self.connect_button.clicked.connect(self.connect_server)
        connect_row.addWidget(self.connect_button)
        connection_layout.addLayout(connect_row)
        self.server_status = QLabel("●  هنوز به سروری وصل نشده‌اید")
        self.server_status.setObjectName("AuthConnectionStatus")
        connection_layout.addWidget(self.server_status)
        card_layout.addWidget(self.connection_panel)

        self.login_form = QWidget()
        self.login_form.setObjectName("AuthForm")
        login_layout = QFormLayout(self.login_form)
        login_layout.setContentsMargins(2, 2, 2, 2)
        login_layout.setHorizontalSpacing(14)
        login_layout.setVerticalSpacing(10)
        login_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.username = QLineEdit()
        self.username.setObjectName("AuthInput")
        self.username.setPlaceholderText("نام کاربری")
        self.password = QLineEdit()
        self.password.setObjectName("AuthInput")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("رمز عبور")
        self.password.returnPressed.connect(self.login)
        password_row = QWidget(self.login_form)
        password_row_layout = QHBoxLayout(password_row)
        password_row_layout.setContentsMargins(0, 0, 0, 0)
        password_row_layout.setSpacing(6)
        password_row_layout.addWidget(self.password, 1)
        self.password_visibility_button = QPushButton("نمایش")
        self.password_visibility_button.setCheckable(True)
        self.password_visibility_button.setMaximumWidth(88)
        self.password_visibility_button.setAccessibleName("نمایش رمز عبور")
        self.password_visibility_button.toggled.connect(self._set_password_visibility)
        password_row_layout.addWidget(self.password_visibility_button)
        self.client_name = QLineEdit(socket.gethostname() or "Desktop client")
        self.client_name.setObjectName("AuthInput")
        self.client_name.setPlaceholderText("نام این دستگاه")
        login_layout.addRow("نام کاربری", self.username)
        login_layout.addRow("رمز عبور", password_row)
        login_layout.addRow("نام دستگاه", self.client_name)
        card_layout.addWidget(self.login_form)

        self.remember_session_checkbox = QCheckBox("ورود خودکار در اجرای بعدی")
        self.remember_session_checkbox.setObjectName("AuthRemember")
        self.remember_session_checkbox.setChecked(
            self.local_settings.value("remember_session", True, type=bool)
        )
        self.remember_session_checkbox.toggled.connect(self._remember_setting_changed)
        card_layout.addWidget(self.remember_session_checkbox)

        self.login_button = QPushButton("ورود به محیط کار   ←")
        self.login_button.setObjectName("AuthLoginButton")
        self.login_button.setMinimumHeight(42)
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
        self.pending_icon.setObjectName("AuthPendingIcon")
        self.pending_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pending_label = QLabel("در انتظار تأیید مدیر")
        self.pending_label.setObjectName("AuthPendingTitle")
        self.pending_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self.message.setObjectName("AuthMessage")
        self.message.setWordWrap(True)
        card_layout.addWidget(self.message)
        content_layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignHCenter)
        content_layout.addStretch(2)
        # Scroll instead of clipping login controls on short or high-DPI displays.
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(content)
        outer.addWidget(scroll_area, 1)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(2500)
        self.poll_timer.timeout.connect(self.poll_activation)
        self.setStyleSheet(stylesheet(mode))
        self.connect_server()

    def _set_password_visibility(self, visible):
        """Toggle password display without modifying the credential value."""
        self.password.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        self.password_visibility_button.setText("مخفی‌کردن" if visible else "نمایش")
        self.password_visibility_button.setAccessibleName(
            "مخفی‌کردن رمز عبور" if visible else "نمایش رمز عبور"
        )

    def set_mode(self, mode):
        self.mode = mode
        self.setStyleSheet(stylesheet(mode))
        self.theme_button.setText("☀  تم روشن" if mode == "dark" else "☾  تم تاریک")
        apply_button_icons(self, mode)

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
        self.local_settings.setValue("last_server_url", api.base_url)
        self.local_settings.sync()
        self._restore_attempted_for_url = None
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
        self.server_status.setProperty("connected", True)
        self.server_status.style().unpolish(self.server_status)
        self.server_status.style().polish(self.server_status)
        if self.api is not None:
            self._run(
                self.api.get_appearance_settings,
                self._appearance_loaded,
                failure=lambda _ticket, _error: None,
            )
        self._attempt_restore_session()

    @Slot(str, object)
    def _connection_failed(self, _ticket, error):
        self.server_status.setText("●  سرور در دسترس نیست")
        self.message.setText(str(error))

    @staticmethod
    def _keyring_account(server_url):
        return str(server_url or "").strip().rstrip("/")

    def _store_server_url(self):
        """Remember the last valid API endpoint independently of session persistence."""
        candidate = self.server_url.text().strip()
        if not candidate:
            return
        try:
            normalized = AccountingApiClient(candidate).base_url
        except ValueError:
            return
        self.local_settings.setValue("last_server_url", normalized)
        self.local_settings.sync()

    def _remember_setting_changed(self, enabled):
        self.local_settings.setValue("remember_session", bool(enabled))
        self.local_settings.sync()
        if not enabled:
            self.clear_remembered_session()
        else:
            self._restore_attempted_for_url = None
            if self.api is not None:
                self._attempt_restore_session()

    def clear_remembered_session(self):
        """Delete stored credentials for the current and last-used endpoints."""
        if keyring is None:
            return
        candidates = [self.server_url.text(), self.local_settings.value("last_server_url", "", type=str)]
        if self.api is not None:
            candidates.append(self.api.base_url)
        for account in {self._keyring_account(value) for value in candidates if value}:
            try:
                keyring.delete_password("Accounting App Desktop Session", account)
            except Exception:
                pass

    def _persist_session(self):
        # Keep endpoint preferences even when the user explicitly opts out of session storage.
        if self.api is not None:
            self.local_settings.setValue("last_server_url", self.api.base_url)
            self.local_settings.sync()
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
        except Exception as exc:
            self.message.setText("ورود انجام شد، اما ذخیرهٔ امن نشست ناموفق بود: {}".format(exc))

    @Slot(str, object)
    def _appearance_loaded(self, _ticket, values):
        set_design_config(values)
        self.setStyleSheet(stylesheet(self.mode))
        # Notify the main shell so it applies the same database-backed design tokens.
        self.theme_changed.emit(self.mode)

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
        self.server_status.setProperty("connected", True)
        self.server_status.style().unpolish(self.server_status)
        self.server_status.style().polish(self.server_status)
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
