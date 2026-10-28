"""Polished multi-step first-run wizard for provisioning the initial administrator."""
import uuid

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget, QDialog,
)

from client.ui.worker import ApiWorker


class SetupWizard(QDialog):
    completed = Signal(object)

    def __init__(self, api, parent=None, mode="light"):
        super().__init__(parent)
        self.api = api
        self.mode = mode
        self._workers = {}
        self._busy = False
        self.setWindowTitle("راه‌اندازی امن حسابداری")
        self.setMinimumSize(760, 560)
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setObjectName("WizardRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(18)

        top = QHBoxLayout()
        brand = QVBoxLayout()
        logo = QLabel("A")
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("background:#4169E1;color:white;border-radius:13px;font-size:24px;font-weight:900;")
        brand.addWidget(logo, 0, Qt.AlignmentFlag.AlignRight)
        brand_title = QLabel("Accounting App")
        brand_title.setObjectName("Brand")
        brand_sub = QLabel("راه‌اندازی اولیه و امن")
        brand_sub.setObjectName("PageSubtitle")
        brand.addWidget(brand_title)
        brand.addWidget(brand_sub)
        top.addLayout(brand)
        top.addStretch(1)
        self.secure_badge = QLabel("●  راه‌اندازی محلی")
        self.secure_badge.setObjectName("StatusPill")
        top.addWidget(self.secure_badge, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(15)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        self.step_header = QLabel("مرحله ۱ از ۳ · آشنایی")
        self.step_header.setObjectName("PageSubtitle")
        root.addWidget(self.step_header)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.pages.addWidget(self._welcome_page())
        self.pages.addWidget(self._admin_page())
        self.pages.addWidget(self._review_page())

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color:#D64045;")
        root.addWidget(self.message)

        footer = QHBoxLayout()
        self.cancel_button = QPushButton("انصراف")
        self.cancel_button.clicked.connect(self.reject)
        self.back_button = QPushButton("مرحله قبل")
        self.back_button.clicked.connect(self.back)
        self.next_button = QPushButton("شروع راه‌اندازی  ←")
        self.next_button.setObjectName("PrimaryButton")
        self.next_button.clicked.connect(self.next)
        self.finish_button = QPushButton("ساخت مدیر و پایان")
        self.finish_button.setObjectName("PrimaryButton")
        self.finish_button.clicked.connect(self.finish)
        self.finish_button.hide()
        footer.addWidget(self.cancel_button)
        footer.addStretch(1)
        footer.addWidget(self.back_button)
        footer.addWidget(self.next_button)
        footer.addWidget(self.finish_button)
        root.addLayout(footer)
        self.back_button.hide()
        self._update_theme(mode)

    def _card(self, title, subtitle):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        detail = QLabel(subtitle)
        detail.setObjectName("PageSubtitle")
        detail.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(detail)
        return page, layout

    def _welcome_page(self):
        page, layout = self._card(
            "به حسابداری خوش آمدید",
            "در چند گام کوتاه، پایگاه داده را آماده کنید و حساب مدیر اصلی را بسازید. رمز عبور به‌صورت هش ذخیره می‌شود و حساب مدیر اولیه برای شروع به تأیید دستگاه نیاز ندارد.",
        )
        cards = QHBoxLayout()
        for number, title, text in (
            ("01", "ساخت مدیر", "اولین حساب، مدیر کل سیستم خواهد بود."),
            ("02", "کنترل دسترسی", "فعال‌سازی نشست‌های کاربران از پنل مدیر."),
            ("03", "آمادهٔ کار", "داده‌ها در سرور می‌مانند و کلاینت از API استفاده می‌کند."),
        ):
            card = QFrame()
            card.setObjectName("Card")
            c = QVBoxLayout(card)
            n = QLabel(number)
            n.setStyleSheet("color:#4169E1;font-size:22px;font-weight:900;")
            h = QLabel(title)
            h.setStyleSheet("font-size:14px;font-weight:800;")
            body = QLabel(text)
            body.setObjectName("PageSubtitle")
            body.setWordWrap(True)
            c.addWidget(n)
            c.addWidget(h)
            c.addWidget(body)
            c.addStretch(1)
            cards.addWidget(card, 1)
        layout.addSpacing(10)
        layout.addLayout(cards, 1)
        note = QLabel("نکته امنیتی: حساب مدیر اولیه فقط یک بار ساخته می‌شود. برای نصب اولیه روی سرور راه دور، توکن نصب جداگانه لازم است.")
        note.setObjectName("StatusPill")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _admin_page(self):
        page, layout = self._card(
            "ساخت حساب مدیر اصلی",
            "نام کاربری و رمز این حساب برای مدیریت کاربران، تأیید نشست‌ها و تنظیمات نگهداری استفاده می‌شوند.",
        )
        form_card = QFrame()
        form_card.setObjectName("Card")
        form_layout = QFormLayout(form_card)
        form_layout.setContentsMargins(18, 18, 18, 18)
        form_layout.setVerticalSpacing(13)
        self.username = QLineEdit()
        self.username.setPlaceholderText("مثلاً system_admin")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("یک رمز عبور قوی انتخاب کنید")
        self.confirmation = QLineEdit()
        self.confirmation.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmation.setPlaceholderText("رمز را دوباره وارد کنید")
        self.setup_token = QLineEdit()
        self.setup_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.setup_token.setPlaceholderText("اگر سرور راه دور است، توکن نصب را وارد کنید")
        self.reveal = QCheckBox("نمایش رمزها")
        self.reveal.toggled.connect(self._toggle_passwords)
        form_layout.addRow("نام کاربری", self.username)
        form_layout.addRow("رمز عبور", self.password)
        form_layout.addRow("تکرار رمز", self.confirmation)
        form_layout.addRow("توکن نصب (در صورت نیاز)", self.setup_token)
        form_layout.addRow("", self.reveal)
        layout.addSpacing(6)
        layout.addWidget(form_card)
        layout.addStretch(1)
        return page

    def _review_page(self):
        page, layout = self._card(
            "بررسی و تأیید",
            "پس از ساخت مدیر، نصب اولیه قفل می‌شود. دیگر نیازی به راه‌اندازی مجدد یا ساخت حساب مدیر با رمز پیش‌فرض نیست.",
        )
        review_card = QFrame()
        review_card.setObjectName("Card")
        detail = QVBoxLayout(review_card)
        self.review_user = QLabel("مدیر: —")
        self.review_user.setStyleSheet("font-size:17px;font-weight:800;")
        self.review_connection = QLabel("اتصال: API حسابداری")
        self.review_connection.setObjectName("PageSubtitle")
        self.review_security = QLabel("وضعیت: مدیر اصلی فعال؛ تأیید نشست برای این حساب لازم نیست.")
        self.review_security.setWordWrap(True)
        self.review_security.setObjectName("StatusPill")
        detail.addWidget(self.review_user)
        detail.addWidget(self.review_connection)
        detail.addWidget(self.review_security)
        layout.addSpacing(10)
        layout.addWidget(review_card)
        layout.addStretch(1)
        return page

    def _toggle_passwords(self, visible):
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.password.setEchoMode(mode)
        self.confirmation.setEchoMode(mode)
        self.setup_token.setEchoMode(mode)

    def _update_theme(self, mode):
        from client.ui.theme import stylesheet
        self.setStyleSheet(stylesheet(mode))

    def _set_step(self, index):
        self.pages.setCurrentIndex(index)
        labels = ["مرحله ۱ از ۳ · آشنایی", "مرحله ۲ از ۳ · حساب مدیر", "مرحله ۳ از ۳ · بررسی نهایی"]
        self.step_header.setText(labels[index])
        self.progress.setValue((index + 1) * 33 if index < 2 else 100)
        self.back_button.setVisible(index > 0)
        self.next_button.setVisible(index < 2)
        self.finish_button.setVisible(index == 2)
        self.message.clear()

    def back(self):
        self._set_step(max(0, self.pages.currentIndex() - 1))

    def next(self):
        index = self.pages.currentIndex()
        if index == 0:
            self._set_step(1)
            self.username.setFocus()
            return
        if index == 1:
            username = self.username.text().strip()
            password = self.password.text()
            if len(username) < 4:
                self.message.setText("نام کاربری باید حداقل ۴ نویسه داشته باشد.")
                return
            if len(password) < 12:
                self.message.setText("برای حساب مدیر، رمز عبور حداقل ۱۲ نویسه‌ای انتخاب کنید.")
                return
            if password != self.confirmation.text():
                self.message.setText("تکرار رمز عبور با رمز یکسان نیست.")
                return
            self.review_user.setText("مدیر اصلی: {}".format(username))
            self._set_step(2)

    def finish(self):
        if self._busy:
            return
        self._busy = True
        self.finish_button.setEnabled(False)
        self.back_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        username = self.username.text().strip()
        password = self.password.text()
        confirmation = self.confirmation.text()
        setup_token = self.setup_token.text().strip() or None
        worker = ApiWorker(
            lambda: self.api.complete_setup(
                username, password, confirmation, setup_token=setup_token
            ),
            parent=self,
        )
        self._workers[worker.ticket] = worker
        worker.succeeded.connect(self._setup_succeeded)
        worker.failed.connect(self._setup_failed)
        worker.finished.connect(lambda: self._cleanup_worker(worker.ticket))
        worker.start()
        self.message.setText("در حال ساخت حساب مدیر و ثبت تنظیمات اولیه...")

    @Slot(str, object)
    def _setup_succeeded(self, _ticket, user):
        self.completed.emit(user)
        self.accept()

    @Slot(str, object)
    def _setup_failed(self, _ticket, error):
        self._busy = False
        self.finish_button.setEnabled(True)
        self.back_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.message.setText(str(error))

    def _cleanup_worker(self, ticket):
        worker = self._workers.pop(ticket, None)
        if worker:
            worker.deleteLater()
