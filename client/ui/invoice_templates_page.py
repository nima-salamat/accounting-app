"""Client editor for the shared, server-persisted invoice template."""
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSplitter, QTextBrowser, QTextEdit, QVBoxLayout,
)

from client.ui.invoice_render import DEFAULT_TEMPLATE, render_invoice_html
from client.ui.permissions import can_access


class InvoiceTemplatesPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        heading = QVBoxLayout()
        title = QLabel("طراحی قالب فاکتور")
        title.setObjectName("PageTitle")
        subtitle = QLabel("قالب مشترک برای برنامهٔ حسابداری و صندوق فروش؛ اطلاعات در سرور ذخیره می‌شود.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        root.addLayout(heading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        form_card = QFrame()
        form_card.setObjectName("Card")
        form = QFormLayout(form_card)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)

        self.company_name = QLineEdit()
        self.company_name.setPlaceholderText("مثلاً فروشگاه مرکزی")
        self.legal_id = QLineEdit()
        self.legal_id.setPlaceholderText("شناسهٔ ثبت یا شناسهٔ مالیاتی (اختیاری)")
        self.address = QTextEdit()
        self.address.setPlaceholderText("نشانی چاپ‌شده روی فاکتور")
        self.address.setFixedHeight(82)
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("تلفن تماس")
        self.footer = QTextEdit()
        self.footer.setPlaceholderText("متن پایین فاکتور")
        self.footer.setFixedHeight(78)
        self.paper_size = QComboBox()
        self.paper_size.addItem("A4", "A4")
        self.paper_size.addItem("رسید باریک", "receipt")
        self.accent_color = QLineEdit()
        self.accent_color.setPlaceholderText("#3157A4")
        form.addRow("نام کسب‌وکار", self.company_name)
        form.addRow("شناسه", self.legal_id)
        form.addRow("نشانی", self.address)
        form.addRow("تلفن", self.phone)
        form.addRow("متن پایانی", self.footer)
        form.addRow("اندازهٔ کاغذ", self.paper_size)
        form.addRow("رنگ اصلی (#RRGGBB)", self.accent_color)

        self.save_button = QPushButton("ذخیرهٔ قالب در سرور")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_template)
        form.addRow("", self.save_button)
        splitter.addWidget(form_card)

        preview_card = QFrame()
        preview_card.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_title = QLabel("پیش‌نمایش زنده")
        preview_title.setObjectName("PageTitle")
        preview_layout.addWidget(preview_title)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        preview_layout.addWidget(self.preview, 1)
        splitter.addWidget(preview_card)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        for field in (self.company_name, self.legal_id, self.phone, self.accent_color):
            field.textChanged.connect(self.update_preview)
        self.address.textChanged.connect(self.update_preview)
        self.footer.textChanged.connect(self.update_preview)
        self.paper_size.currentIndexChanged.connect(self.update_preview)
        self._load_template(dict(DEFAULT_TEMPLATE))
        self.set_permissions(window.current_user)

    def set_permissions(self, user):
        self.save_button.setVisible(can_access(user, "invoices", "update"))

    def refresh(self):
        if self.window.api:
            self.window.run_api(
                self.window.api.get_invoice_template,
                self._load_template,
                failure=lambda error: self.window.show_error(error),
            )

    def _load_template(self, values):
        values = dict(DEFAULT_TEMPLATE, **(values or {}))
        self.company_name.setText(str(values.get("company_name", "")))
        self.legal_id.setText(str(values.get("legal_id", "")))
        self.address.setPlainText(str(values.get("address", "")))
        self.phone.setText(str(values.get("phone", "")))
        self.footer.setPlainText(str(values.get("footer", "")))
        idx = self.paper_size.findData(values.get("paper_size", "A4"))
        self.paper_size.setCurrentIndex(max(0, idx))
        self.accent_color.setText(str(values.get("accent_color", "#3157A4")))
        self.update_preview()

    def _values(self):
        return {
            "company_name": self.company_name.text().strip(),
            "legal_id": self.legal_id.text().strip(),
            "address": self.address.toPlainText().strip(),
            "phone": self.phone.text().strip(),
            "footer": self.footer.toPlainText().strip(),
            "paper_size": self.paper_size.currentData(),
            "accent_color": self.accent_color.text().strip(),
        }

    def update_preview(self, *_args):
        sample = {
            "id": "preview",
            "day_receipt_id": "۱۰۰۱",
            "created_at": "2026-10-28T12:00:00",
            "payed": True,
            "total_price": 1285000,
            "items": [
                {"product_name": "نمونه کالا", "quantity": 2, "sell_price": 450000},
                {"product_name": "کالای دوم", "quantity": 1, "sell_price": 385000},
            ],
        }
        self.preview.setHtml(render_invoice_html(sample, self._values()))

    def save_template(self):
        values = self._values()
        if not values["company_name"]:
            self.window.show_error("نام کسب‌وکار نباید خالی باشد.")
            return
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", values["accent_color"]):
            self.window.show_error("رنگ باید با قالبی مانند #3157A4 وارد شود.")
            return
        if not self.window.api:
            self.window.show_error("اتصال سرور برقرار نیست.")
            return
        self.window.run_api(
            lambda: self.window.api.save_invoice_template(**values),
            self._saved,
            busy=self.save_button,
        )

    def _saved(self, values):
        self._load_template(values)
        self.window.set_status("قالب فاکتور روی سرور ذخیره شد.")
        QMessageBox.information(self, "ذخیره شد", "قالب برای کلاینت حسابداری و صندوق فروش به‌روزرسانی شد.")
