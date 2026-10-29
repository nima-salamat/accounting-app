"""Dedicated, user-friendly invoice numbering settings page."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout,
)

from accounting_app.services.invoice_numbering import (
    DEFAULT_INVOICE_NUMBER_FORMAT,
    DEFAULT_INVOICE_NUMBER_PADDING,
    format_invoice_number,
    validate_invoice_number_format,
)
from client.ui.invoice_render import DEFAULT_TEMPLATE
from client.ui.invoice_templates_page import (
    NUMBERING_DATE_FORMATS,
    NUMBERING_SEPARATORS,
    NUMBERING_STYLES,
    SAMPLE_RECEIPT,
    _compose_invoice_number_format,
)
from client.ui.permissions import can_access


class InvoiceNumberingPage(QFrame):
    """Configure receipt identifiers without opening or changing the print designer."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self._loading = False
        self._template_cache = deepcopy(DEFAULT_TEMPLATE)
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(14)

        heading = QHBoxLayout()
        title_group = QVBoxLayout()
        self.title_label = QLabel("شماره‌گذاری فاکتور")
        self.title_label.setObjectName("PageTitle")
        subtitle = QLabel(
            "قالب شماره‌ها و شمارنده‌ها را مستقل از طراحی و چیدمان برگه تنظیم کنید."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        title_group.addWidget(self.title_label)
        title_group.addWidget(subtitle)
        heading.addLayout(title_group, 1)

        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.setToolTip("خواندن تنظیمات فعلی شماره‌گذاری از سرور")
        self.refresh_button.clicked.connect(self.refresh)
        self.save_button = QPushButton("ذخیرهٔ شماره‌گذاری")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save)
        heading.addWidget(self.refresh_button)
        heading.addWidget(self.save_button)
        root.addLayout(heading)

        card = QFrame(self)
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)
        card_title = QLabel("روش ساخت شماره")
        card_title.setObjectName("PageTitle")
        card_layout.addWidget(card_title)
        intro = QLabel(
            "برای روش‌های معمول فقط گزینه‌ها را انتخاب کنید؛ نیازی به نوشتن JSON یا کد نیست."
        )
        intro.setObjectName("PageSubtitle")
        intro.setWordWrap(True)
        card_layout.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        self.invoice_number_style = QComboBox()
        for key, label in NUMBERING_STYLES:
            self.invoice_number_style.addItem(label, key)

        self.invoice_number_prefix = QLineEdit()
        self.invoice_number_prefix.setMaxLength(24)
        self.invoice_number_prefix.setPlaceholderText("مثلاً INV یا فروش")
        self.invoice_number_prefix.setToolTip(
            "پیشوند دلخواه؛ لازم نیست آکولاد یا کد وارد کنید."
        )

        self.invoice_number_date_format = QComboBox()
        for key, label, _tokens in NUMBERING_DATE_FORMATS:
            self.invoice_number_date_format.addItem(label, key)

        self.invoice_number_separator = QComboBox()
        for key, label in NUMBERING_SEPARATORS:
            self.invoice_number_separator.addItem(label, key)

        self.invoice_number_padding = QSpinBox()
        self.invoice_number_padding.setRange(1, 12)
        self.invoice_number_padding.setSuffix(" رقم")

        self.invoice_number_custom_format = QLineEdit()
        self.invoice_number_custom_format.setMaxLength(120)
        self.invoice_number_custom_format.setPlaceholderText("مثلاً INV-{DATE}-{NUM}")
        self.invoice_number_custom_format.setToolTip(
            "فقط برای حالت پیشرفته است؛ برای روش‌های معمول نیازی به این الگو نیست."
        )

        self.invoice_number_example = QLabel()
        self.invoice_number_example.setObjectName("StatusPill")
        self.invoice_number_example.setWordWrap(True)
        self.invoice_number_example.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.custom_format_label = QLabel("الگوی سفارشی")
        self.custom_format_label.setObjectName("PageSubtitle")

        form.addRow("روش شماره‌گذاری", self.invoice_number_style)
        form.addRow("پیشوند دلخواه", self.invoice_number_prefix)
        form.addRow("قالب تاریخ", self.invoice_number_date_format)
        form.addRow("جداکننده", self.invoice_number_separator)
        form.addRow("تعداد رقم شمارنده", self.invoice_number_padding)
        form.addRow(self.custom_format_label, self.invoice_number_custom_format)
        form.addRow("پیش‌نمایش شماره", self.invoice_number_example)
        card_layout.addLayout(form)

        help_text = QLabel(
            "نمونه: روش «تاریخ + شمارهٔ همان روز» با ۵ رقم، شماره‌ای مانند "
            "2026-10-30-00001 می‌سازد. تعداد رقم حداقل است و پس از ۹۹۹۹۹، "
            "شماره به ۱۰۰۰۰۰ تبدیل می‌شود. تغییر این تنظیمات شمارهٔ فاکتورهای "
            "قبلاً صادرشده را عوض نمی‌کند."
        )
        help_text.setObjectName("PageSubtitle")
        help_text.setWordWrap(True)
        card_layout.addWidget(help_text)
        root.addWidget(card, 0)
        root.addStretch(1)

        self.invoice_number_style.currentIndexChanged.connect(self._builder_changed)
        self.invoice_number_prefix.textChanged.connect(self._builder_changed)
        self.invoice_number_date_format.currentIndexChanged.connect(self._builder_changed)
        self.invoice_number_separator.currentIndexChanged.connect(self._builder_changed)
        self.invoice_number_custom_format.textChanged.connect(self._builder_changed)
        self.invoice_number_padding.valueChanged.connect(self._builder_changed)

        self._load_template(DEFAULT_TEMPLATE)
        self.set_permissions(getattr(window, "current_user", None))

    def set_permissions(self, user):
        can_read = can_access(user, "invoices", "read")
        can_update = can_access(user, "invoices", "update")
        self.refresh_button.setEnabled(can_read or can_update)
        self.save_button.setEnabled(can_update)
        for control in (
            self.invoice_number_style,
            self.invoice_number_prefix,
            self.invoice_number_date_format,
            self.invoice_number_separator,
            self.invoice_number_padding,
            self.invoice_number_custom_format,
        ):
            control.setEnabled(can_update)

    def refresh(self):
        user = getattr(self.window, "current_user", None)
        if self.window.api is None or not (
            can_access(user, "invoices", "read")
            or can_access(user, "invoices", "update")
        ):
            return
        api = self.window.api
        self.window.run_api(
            lambda: api.get_invoice_template(kind="invoice"),
            self._load_template,
            failure=lambda error: self.window.show_error(error),
            busy=self.refresh_button,
        )

    def _build_invoice_number_format(self):
        separator = (
            self.invoice_number_separator.currentData()
            if self.invoice_number_separator.currentIndex() >= 0 else "-"
        )
        return _compose_invoice_number_format(
            self.invoice_number_style.currentData() or "date_daily",
            self.invoice_number_prefix.text(),
            self.invoice_number_date_format.currentData() or "iso",
            separator,
            self.invoice_number_custom_format.text(),
        )

    def _restore_invoice_number_builder(self, number_format):
        """Restore common saved patterns and keep unknown legacy patterns editable."""
        stored = str(number_format or DEFAULT_INVOICE_NUMBER_FORMAT).strip()
        normalized = stored.replace("{DATE}", "{YYYY}-{MM}-{DD}")
        prefix_head = normalized.split("{", 1)[0]
        prefix_guess = prefix_head.rstrip("-/._ ")
        prefixes = ["", prefix_guess] if prefix_guess else [""]
        match = None
        for style, _label in NUMBERING_STYLES:
            if style == "custom":
                continue
            for date_style, _date_label, _date_tokens in NUMBERING_DATE_FORMATS:
                for separator, _separator_label in NUMBERING_SEPARATORS:
                    for prefix in prefixes:
                        if _compose_invoice_number_format(
                            style, prefix, date_style, separator, ""
                        ) == normalized:
                            match = (style, prefix, date_style, separator)
                            break
                    if match:
                        break
                if match:
                    break
            if match:
                break

        if match:
            style, prefix, date_style, separator = match
            self.invoice_number_style.setCurrentIndex(
                self.invoice_number_style.findData(style)
            )
            self.invoice_number_prefix.setText(prefix)
            self.invoice_number_date_format.setCurrentIndex(
                max(0, self.invoice_number_date_format.findData(date_style))
            )
            self.invoice_number_separator.setCurrentIndex(
                max(0, self.invoice_number_separator.findData(separator))
            )
            self.invoice_number_custom_format.clear()
        else:
            self.invoice_number_style.setCurrentIndex(
                max(0, self.invoice_number_style.findData("custom"))
            )
            self.invoice_number_custom_format.setText(stored)
        self._update_builder_visibility()

    def _update_builder_visibility(self):
        style = self.invoice_number_style.currentData() or "date_daily"
        self.invoice_number_prefix.setEnabled(style.startswith("prefix_"))
        self.invoice_number_date_format.setEnabled(style in {
            "date_daily", "date_global", "prefix_date_daily", "prefix_date_global"
        })
        self.invoice_number_separator.setEnabled(style not in {"global", "custom"})
        is_custom = style == "custom"
        self.custom_format_label.setVisible(is_custom)
        self.invoice_number_custom_format.setVisible(is_custom)

    def _builder_changed(self, *_args):
        if self._loading:
            return
        self._update_builder_visibility()
        self._update_preview()

    def _load_template(self, values):
        self._loading = True
        try:
            self._template_cache = dict(DEFAULT_TEMPLATE, **(values or {}))
            self._restore_invoice_number_builder(
                self._template_cache.get(
                    "invoice_number_format", DEFAULT_INVOICE_NUMBER_FORMAT
                )
            )
            try:
                padding = int(self._template_cache.get(
                    "invoice_number_padding", DEFAULT_INVOICE_NUMBER_PADDING
                ))
            except (TypeError, ValueError):
                padding = DEFAULT_INVOICE_NUMBER_PADDING
            self.invoice_number_padding.setValue(max(1, min(12, padding)))
        finally:
            self._loading = False
        self._update_preview()

    def _update_preview(self):
        if not hasattr(self, "invoice_number_example"):
            return
        try:
            example = format_invoice_number(
                SAMPLE_RECEIPT,
                self._build_invoice_number_format(),
                self.invoice_number_padding.value(),
            )
            self.invoice_number_example.setText(
                example.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
            )
        except ValueError as error:
            self.invoice_number_example.setText(
                "تنظیم شماره‌گذاری نیاز به اصلاح دارد: {}".format(error)
            )
        finally:
            self._update_builder_visibility()

    def save(self):
        user = getattr(self.window, "current_user", None)
        if not can_access(user, "invoices", "update"):
            return
        if self.window.api is None:
            self.window.show_error("اتصال سرور برقرار نیست.")
            return
        try:
            validate_invoice_number_format(self._build_invoice_number_format())
        except ValueError as error:
            self.window.show_error(error)
            return

        api = self.window.api
        self.window.run_api(
            lambda: api.get_invoice_template(kind="invoice"),
            self._save_over_latest_template,
            failure=lambda error: self.window.show_error(error),
            busy=self.save_button,
        )

    def _save_over_latest_template(self, latest_template):
        try:
            number_format = validate_invoice_number_format(
                self._build_invoice_number_format()
            )
        except ValueError as error:
            self.window.show_error(error)
            return
        try:
            padding = int(self.invoice_number_padding.value())
        except (TypeError, ValueError):
            padding = DEFAULT_INVOICE_NUMBER_PADDING
        values = dict(DEFAULT_TEMPLATE, **(latest_template or {}))
        values["invoice_number_format"] = number_format
        values["invoice_number_padding"] = max(1, min(12, padding))
        api = self.window.api
        if api is None:
            self.window.show_error("اتصال سرور برقرار نیست.")
            return
        self.window.run_api(
            lambda: api.save_invoice_template(kind="invoice", **values),
            self._saved,
            failure=lambda error: self.window.show_error(error),
            busy=self.save_button,
        )

    def _saved(self, values):
        self._load_template(values)
        designer = getattr(self.window, "invoice_templates_page", None)
        if designer is not None:
            designer.sync_invoice_numbering(
                values.get("invoice_number_format", DEFAULT_INVOICE_NUMBER_FORMAT),
                values.get("invoice_number_padding", DEFAULT_INVOICE_NUMBER_PADDING),
            )
        setter = getattr(self.window, "set_status", None)
        if callable(setter):
            setter("تنظیمات شماره‌گذاری فاکتور ذخیره شد.")
