"""Connection settings and database-backed application-wide appearance preferences."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from client.ui.permissions import can_access
from client.ui.theme import DEFAULT_DESIGN, set_design_config
from client.ui.currency import set_currency_unit


class SettingsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self._loading = False
        self.current_user = None
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("تنظیمات برنامه")
        title.setObjectName("PageTitle")
        subtitle = QLabel("اتصال، ظاهر رابط و قواعد تایپوگرافی از یک محل مدیریت می‌شوند.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(14)

        connection = QFrame()
        connection.setObjectName("Card")
        connection_layout = QVBoxLayout(connection)
        connection_layout.setContentsMargins(18, 16, 18, 16)
        connection_layout.setSpacing(10)
        connection_title = QLabel("اتصال به سرور")
        connection_title.setObjectName("PageTitle")
        connection_layout.addWidget(connection_title)
        connection_layout.addWidget(QLabel("نشانی API (IP یا دامنه به‌همراه پورت)"))
        self.url = QLineEdit(window.api.base_url if window.api else "")
        self.url.setPlaceholderText("http://127.0.0.1:8000 یا https://accounting.example.com")
        self.url.setClearButtonEnabled(True)
        connection_layout.addWidget(self.url)
        self.save_connection_button = QPushButton("ذخیره نشانی و اتصال مجدد")
        self.save_connection_button.setObjectName("PrimaryButton")
        self.save_connection_button.clicked.connect(self.reconnect)
        connection_layout.addWidget(self.save_connection_button)
        layout.addWidget(connection)

        appearance = QFrame()
        appearance.setObjectName("Card")
        appearance_layout = QVBoxLayout(appearance)
        appearance_layout.setContentsMargins(18, 16, 18, 16)
        appearance_layout.setSpacing(12)
        appearance_title = QLabel("ظاهر، فونت و واحد پول مشترک برنامه‌ها")
        appearance_title.setObjectName("PageTitle")
        appearance_description = QLabel(
            "فونت، چیدمان و واحد پول در دیتابیس سرور ذخیره می‌شوند تا کلاینت‌های دسکتاپ و POS "
            "واحد نمایش یکسانی داشته باشند. تم روشن/تاریک همچنان انتخاب شخصی این دستگاه است."
        )
        appearance_description.setObjectName("PageSubtitle")
        appearance_description.setWordWrap(True)
        appearance_layout.addWidget(appearance_title)
        appearance_layout.addWidget(appearance_description)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.currency_unit = QComboBox()
        self.currency_unit.addItem("تومان", "toman")
        self.currency_unit.addItem("ریال (هر تومان = ۱۰ ریال)", "rial")
        currency_hint = QLabel(
            "مبالغ در سرور با مبنای تومان نگهداری می‌شوند؛ انتخاب ریال فقط نمایش را "
            "۱۰ برابر می‌کند و مقدار اصلی ذخیره‌شده را تغییر نمی‌دهد."
        )
        currency_hint.setObjectName("PageSubtitle")
        currency_hint.setWordWrap(True)

        self.font_family = QComboBox()
        self.font_family.setEditable(True)
        self.font_family.addItems([
            "Vazirmatn", "Noto Sans Arabic", "Noto Naskh Arabic", "Tahoma",
            "Segoe UI", "Arial", "IRANSans", "B Nazanin",
        ])
        self.font_family.setCurrentText(DEFAULT_DESIGN["font_family"])
        self.font_size = QSpinBox()
        self.font_size.setRange(10, 18)
        self.font_size.setSuffix(" px")
        self.heading_scale = QDoubleSpinBox()
        self.heading_scale.setRange(0.9, 1.5)
        self.heading_scale.setSingleStep(0.1)
        self.heading_scale.setDecimals(1)
        self.density = QComboBox()
        self.density.addItem("فشرده", "compact")
        self.density.addItem("معمولی", "comfortable")
        self.density.addItem("باز و خوانا", "spacious")
        self.corner_radius = QSpinBox()
        self.corner_radius.setRange(4, 20)
        self.corner_radius.setSuffix(" px")
        self.control_height = QSpinBox()
        self.control_height.setRange(28, 52)
        self.control_height.setSuffix(" px")
        self.control_padding = QSpinBox()
        self.control_padding.setRange(4, 16)
        self.control_padding.setSuffix(" px")
        self.horizontal_padding = QSpinBox()
        self.horizontal_padding.setRange(4, 24)
        self.horizontal_padding.setSuffix(" px")
        self.section_spacing = QSpinBox()
        self.section_spacing.setRange(4, 24)
        self.section_spacing.setSuffix(" px")
        form.addRow("واحد پول نمایش", self.currency_unit)
        form.addRow(currency_hint)
        form.addRow("خانوادهٔ فونت", self.font_family)
        form.addRow("اندازهٔ متن پایه", self.font_size)
        form.addRow("مقیاس تیترها", self.heading_scale)
        form.addRow("تراکم اجزای رابط", self.density)
        form.addRow("گردی گوشه‌ها", self.corner_radius)
        form.addRow("ارتفاع کنترل‌ها", self.control_height)
        form.addRow("فاصلهٔ عمودی کنترل‌ها", self.control_padding)
        form.addRow("فاصلهٔ افقی کنترل‌ها", self.horizontal_padding)
        form.addRow("فاصلهٔ بخش‌ها", self.section_spacing)
        appearance_layout.addLayout(form)

        actions = QGridLayout()
        actions.setHorizontalSpacing(10)
        self.save_appearance_button = QPushButton("ذخیره در دیتابیس سرور")
        self.save_appearance_button.setObjectName("PrimaryButton")
        self.save_appearance_button.clicked.connect(self.save_appearance)
        self.reset_appearance_button = QPushButton("بازگردانی مقادیر پیش‌فرض")
        self.reset_appearance_button.clicked.connect(self.reset_appearance)
        self.reload_appearance_button = QPushButton("بازخوانی تنظیمات سرور")
        self.reload_appearance_button.clicked.connect(self.refresh_appearance)
        actions.addWidget(self.save_appearance_button, 0, 0)
        actions.addWidget(self.reset_appearance_button, 0, 1)
        actions.addWidget(self.reload_appearance_button, 1, 0, 1, 2)
        appearance_layout.addLayout(actions)
        self.appearance_status = QLabel("تنظیمات ظاهری هنوز از سرور بارگذاری نشده‌اند.")
        self.appearance_status.setObjectName("PageSubtitle")
        self.appearance_status.setWordWrap(True)
        appearance_layout.addWidget(self.appearance_status)
        layout.addWidget(appearance)

        local = QFrame()
        local.setObjectName("Card")
        local_layout = QFormLayout(local)
        local_layout.setContentsMargins(18, 16, 18, 16)
        local_layout.setHorizontalSpacing(18)
        local_layout.setVerticalSpacing(10)
        local_title = QLabel("ترجیحات این دستگاه")
        local_title.setObjectName("PageTitle")
        local_layout.addRow(local_title)
        self.theme = QComboBox()
        self.theme.addItem("روشن", "light")
        self.theme.addItem("تاریک", "dark")
        self.theme.setCurrentIndex(1 if window.mode == "dark" else 0)
        self.theme.currentIndexChanged.connect(lambda _i: window.change_theme(self.theme.currentData()))
        local_layout.addRow("تم برنامه", self.theme)
        layout.addWidget(local)

        info = QLabel(
            "نکتهٔ امنیتی: سرور راه‌دور باید از HTTPS استفاده کند. برای اجرای کلاینت، "
            "سرور باید جداگانه اجرا شده باشد؛ کلاینت دسکتاپ دیگر سرور محلی ایجاد نمی‌کند."
        )
        info.setObjectName("PageSubtitle")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self._set_design_values(DEFAULT_DESIGN)

    def set_user(self, user):
        self.current_user = user or {}
        is_admin = bool(self.current_user.get("is_admin"))
        self.save_appearance_button.setEnabled(is_admin)
        self.reset_appearance_button.setEnabled(is_admin)
        self.appearance_status.setText(
            "مدیر می‌تواند تنظیمات مشترک ظاهر را تغییر دهد."
            if is_admin else "تنظیمات مشترک فقط برای مدیر قابل ویرایش است؛ کاربران دیگر آن را دریافت می‌کنند."
        )

    def _design_values(self):
        return {
            "currency_unit": self.currency_unit.currentData() or "toman",
            "font_family": self.font_family.currentText().strip() or DEFAULT_DESIGN["font_family"],
            "font_size": self.font_size.value(),
            "heading_scale": self.heading_scale.value(),
            "density": self.density.currentData() or "comfortable",
            "corner_radius": self.corner_radius.value(),
            "control_height": self.control_height.value(),
            "control_padding": self.control_padding.value(),
            "horizontal_padding": self.horizontal_padding.value(),
            "section_spacing": self.section_spacing.value(),
        }

    def _set_design_values(self, values):
        values = dict(DEFAULT_DESIGN, **(values if isinstance(values, dict) else {}))
        self._loading = True
        currency_index = self.currency_unit.findData(values.get("currency_unit", "toman"))
        self.currency_unit.setCurrentIndex(max(0, currency_index))
        self.font_family.setCurrentText(str(values.get("font_family", "Vazirmatn")))
        for control, key in (
            (self.font_size, "font_size"), (self.heading_scale, "heading_scale"),
            (self.corner_radius, "corner_radius"), (self.control_height, "control_height"),
            (self.control_padding, "control_padding"), (self.horizontal_padding, "horizontal_padding"),
            (self.section_spacing, "section_spacing"),
        ):
            control.setValue(values.get(key, DEFAULT_DESIGN[key]))
        index = self.density.findData(values.get("density", "comfortable"))
        self.density.setCurrentIndex(max(0, index))
        self._loading = False

    def refresh(self):
        if self.window.api is not None:
            self.url.setText(self.window.api.base_url)
        self.refresh_appearance()

    def refresh_appearance(self):
        api = self.window.api
        if api is None:
            self.appearance_status.setText("برای بارگذاری تنظیمات، ابتدا به سرور وصل شوید.")
            return
        self.window.run_api(
            api.get_appearance_settings,
            self._appearance_loaded,
            failure=lambda error: self.appearance_status.setText("بارگذاری تنظیمات ناموفق بود: {}".format(error)),
            busy=self.reload_appearance_button,
        )

    def _appearance_loaded(self, values):
        self._set_design_values(values)
        set_currency_unit(values.get("currency_unit", "toman"))
        set_design_config(values)
        self.window._apply_theme()
        self.appearance_status.setText("تنظیمات مشترک ظاهر از دیتابیس سرور دریافت شد.")

    def save_appearance(self):
        if not self.current_user or not self.current_user.get("is_admin"):
            self.appearance_status.setText("برای تغییر تنظیمات مشترک، ورود با حساب مدیر لازم است.")
            return
        if self.window.api is None:
            self.appearance_status.setText("اتصال به سرور برقرار نیست.")
            return
        values = self._design_values()
        self.window.run_api(
            lambda: self.window.api.save_appearance_settings(**values),
            self._appearance_saved,
            failure=lambda error: self.appearance_status.setText("ذخیره‌سازی ناموفق بود: {}".format(error)),
            busy=self.save_appearance_button,
        )

    def _appearance_saved(self, values):
        self._set_design_values(values)
        set_currency_unit(values.get("currency_unit", "toman"))
        set_design_config(values)
        self.window._apply_theme()
        self.appearance_status.setText("تنظیمات ظاهری در دیتابیس مشترک سرور ذخیره شد.")
        self.window.set_status("تنظیمات ظاهری مشترک ذخیره شد.")

    def reset_appearance(self):
        self._set_design_values(DEFAULT_DESIGN)
        set_currency_unit("toman")
        set_design_config(DEFAULT_DESIGN)
        self.window._apply_theme()
        self.appearance_status.setText("مقادیر پیش‌فرض انتخاب شدند؛ برای اعمال به سایر کلاینت‌ها ذخیره کنید.")

    def reconnect(self):
        self.window.connect_to_api(self.url.text().strip())
