"""Configurable local POS peripherals.

Printer selection uses Qt's installed system printers. Most USB barcode scanners act
as keyboard-wedge devices and therefore need no vendor driver in this app.
TCP checks only establish socket reachability; payment authorization is vendor-specific.
"""
import socket

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QVBoxLayout,
)


def device_settings():
    settings = QSettings("AccountingApp", "PointOfSale")
    return {
        "printer_name": settings.value("devices/printer_name", "", type=str),
        "auto_print": settings.value("devices/auto_print", False, type=bool),
        "paper_width": settings.value("devices/paper_width", "80mm", type=str),
        "terminal_mode": settings.value("devices/terminal_mode", "manual", type=str),
        "terminal_host": settings.value("devices/terminal_host", "127.0.0.1", type=str),
        "terminal_port": settings.value("devices/terminal_port", 0, type=int),
        "barcode_mode": settings.value("devices/barcode_mode", "keyboard", type=str),
    }


class DeviceSettingsDialog(QDialog):
    """Touch-friendly device setup for the cashier/register application."""

    def __init__(self, parent=None, kiosk=False):
        super().__init__(parent)
        self.kiosk = kiosk
        self.setWindowTitle("تنظیمات دستگاه‌های صندوق")
        self.setMinimumSize(620, 520)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)
        heading = QLabel("اتصال و تنظیم دستگاه‌های جانبی")
        heading.setObjectName("PageTitle")
        subtitle = QLabel(
            "چاپگر رسید، اسکنر بارکد و کارت‌خوان در این قسمت پیکربندی می‌شوند. "
            "پشتیبانی از تأیید پرداخت واقعی به مدل کارت‌خوان و API شرکت ارائه‌دهنده بستگی دارد."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._printer_tab(), "چاپگر رسید")
        self.tabs.addTab(self._terminal_tab(), "کارت‌خوان")
        self.tabs.addTab(self._scanner_tab(), "اسکنر بارکد")

        self.status = QLabel()
        self.status.setObjectName("PageSubtitle")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ذخیره تنظیمات")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._load_values()

    def _printer_tab(self):
        page = QFrame()
        page.setObjectName("Card")
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(14)
        self.printer = QComboBox()
        self.printer.addItem("چاپگر پیش‌فرض سیستم", "")
        for item in QPrinterInfo.availablePrinters():
            self.printer.addItem(item.printerName(), item.printerName())
        self.paper = QComboBox()
        self.paper.addItem("رسید ۸۰ میلی‌متری", "80mm")
        self.paper.addItem("رسید ۵۸ میلی‌متری", "58mm")
        self.paper.addItem("A4", "A4")
        self.auto_print_button = QComboBox()
        self.auto_print_button.addItem("پس از فروش، خودکار چاپ نکن", False)
        self.auto_print_button.addItem("پس از فروش، خودکار چاپ کن", True)
        self.test_printer_button = QPushButton("چاپ برگهٔ آزمایشی")
        self.test_printer_button.clicked.connect(self.print_test)
        self.refresh_printers_button = QPushButton("بازخوانی چاپگرها")
        self.refresh_printers_button.clicked.connect(self.refresh_printers)
        row = QHBoxLayout()
        row.addWidget(self.refresh_printers_button)
        row.addWidget(self.test_printer_button)
        form.addRow("چاپگر", self.printer)
        form.addRow("اندازه رسید", self.paper)
        form.addRow("چاپ خودکار", self.auto_print_button)
        form.addRow("", row)
        note = QLabel(
            "چاپگر باید در تنظیمات سیستم‌عامل نصب شده باشد. این برنامه از صف چاپ سیستم استفاده می‌کند؛ "
            "برای ESC/POS خام یا چاپگر شبکه‌ای خاص ممکن است درایور یا آداپتور سازنده لازم باشد."
        )
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        form.addRow("", note)
        return page

    def _terminal_tab(self):
        page = QFrame()
        page.setObjectName("Card")
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(14)
        self.terminal_mode = QComboBox()
        self.terminal_mode.addItem("پرداخت دستی / بدون اتصال نرم‌افزاری", "manual")
        self.terminal_mode.addItem("کارت‌خوان دارای درگاه TCP اختصاصی", "tcp")
        self.terminal_host = QLineEdit("127.0.0.1")
        self.terminal_host.setPlaceholderText("IP یا نام میزبان دستگاه / واسط")
        self.terminal_port = QLineEdit()
        self.terminal_port.setPlaceholderText("مثلاً 9100")
        self.test_terminal_button = QPushButton("آزمون اتصال")
        self.test_terminal_button.clicked.connect(self.test_terminal)
        form.addRow("روش پرداخت", self.terminal_mode)
        form.addRow("میزبان", self.terminal_host)
        form.addRow("پورت", self.terminal_port)
        form.addRow("", self.test_terminal_button)
        warning = QLabel(
            "نکتهٔ امنیتی: آزمون TCP فقط باز بودن مسیر شبکه را بررسی می‌کند؛ "
            "به معنای تأیید یا دریافت وجه نیست. برای ارسال مبلغ و دریافت نتیجهٔ تراکنش، "
            "آداپتور رسمی مدل کارت‌خوان و مشخصات شرکت پرداخت باید پیاده‌سازی و جداگانه آزمایش شود. "
            "شماره کارت یا PIN در این برنامه ذخیره نمی‌شود."
        )
        warning.setObjectName("StatusPill")
        warning.setWordWrap(True)
        form.addRow("", warning)
        return page

    def _scanner_tab(self):
        page = QFrame()
        page.setObjectName("Card")
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(14)
        self.barcode_mode = QComboBox()
        self.barcode_mode.addItem("اسکنر USB به‌صورت صفحه‌کلید (پیشنهادی)", "keyboard")
        self.barcode_mode.addItem("فعلاً بدون اسکنر", "none")
        self.scanner_test_input = QLineEdit()
        self.scanner_test_input.setPlaceholderText("بارکد را اسکن کنید یا تایپ کنید…")
        self.scanner_test_input.setMinimumHeight(44)
        form.addRow("نوع اتصال", self.barcode_mode)
        form.addRow("آزمون اسکن", self.scanner_test_input)
        note = QLabel(
            "اغلب اسکنرهای USB در حالت HID مانند صفحه‌کلید عمل می‌کنند: کرسر را در فیلد اسکن قرار دهید "
            "و در صورت نیاز، پایان‌دهندهٔ Enter را در خود اسکنر فعال کنید."
        )
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        form.addRow("", note)
        return page

    def refresh_printers(self):
        current = self.printer.currentData()
        self.printer.clear()
        self.printer.addItem("چاپگر پیش‌فرض سیستم", "")
        for item in QPrinterInfo.availablePrinters():
            self.printer.addItem(item.printerName(), item.printerName())
        index = self.printer.findData(current)
        self.printer.setCurrentIndex(index if index >= 0 else 0)
        self.status.setText("فهرست چاپگرهای نصب‌شده بازخوانی شد.")

    def _load_values(self):
        values = device_settings()
        index = self.printer.findData(values["printer_name"])
        self.printer.setCurrentIndex(index if index >= 0 else 0)
        index = self.paper.findData(values["paper_width"])
        self.paper.setCurrentIndex(index if index >= 0 else 0)
        index = self.auto_print_button.findData(values["auto_print"])
        self.auto_print_button.setCurrentIndex(index if index >= 0 else 0)
        index = self.terminal_mode.findData(values["terminal_mode"])
        self.terminal_mode.setCurrentIndex(index if index >= 0 else 0)
        self.terminal_host.setText(values["terminal_host"])
        port = values["terminal_port"]
        self.terminal_port.setText(str(port) if port else "")
        index = self.barcode_mode.findData(values["barcode_mode"])
        self.barcode_mode.setCurrentIndex(index if index >= 0 else 0)

    def _save(self):
        mode = self.terminal_mode.currentData()
        host = self.terminal_host.text().strip()
        port_text = self.terminal_port.text().strip()
        port = 0
        if mode == "tcp":
            if not host:
                self.status.setText("برای آزمون اتصال، میزبان را وارد کنید.")
                self.tabs.setCurrentIndex(1)
                return
            try:
                port = int(port_text)
                if not 1 <= port <= 65535:
                    raise ValueError
            except ValueError:
                self.status.setText("پورت باید عددی بین ۱ تا ۶۵۵۳۵ باشد.")
                self.tabs.setCurrentIndex(1)
                return
        settings = QSettings("AccountingApp", "PointOfSale")
        settings.setValue("devices/printer_name", self.printer.currentData() or "")
        settings.setValue("devices/auto_print", bool(self.auto_print_button.currentData()))
        settings.setValue("devices/paper_width", self.paper.currentData() or "80mm")
        settings.setValue("devices/terminal_mode", mode)
        settings.setValue("devices/terminal_host", host or "127.0.0.1")
        settings.setValue("devices/terminal_port", port)
        settings.setValue("devices/barcode_mode", self.barcode_mode.currentData() or "keyboard")
        settings.sync()
        if settings.status() != QSettings.Status.NoError:
            self.status.setText("ذخیره تنظیمات در سیستم‌عامل ناموفق بود.")
            return
        self.status.setText("تنظیمات دستگاه‌ها ذخیره شد.")
        self.accept()

    def test_terminal(self):
        if self.terminal_mode.currentData() != "tcp":
            QMessageBox.information(
                self, "روش پرداخت دستی",
                "در حالت فعلی، دریافت وجه و تأیید پرداخت در صندوق به‌صورت دستی ثبت می‌شود.",
            )
            return
        host = self.terminal_host.text().strip()
        try:
            port = int(self.terminal_port.text().strip())
            if not host or not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "آدرس نامعتبر", "میزبان و پورت معتبر وارد کنید.")
            return
        try:
            with socket.create_connection((host, port), timeout=1.5):
                QMessageBox.information(
                    self, "اتصال برقرار است",
                    "اتصال شبکه به {}:{} برقرار شد. این نتیجه تراکنش پرداخت را تأیید نمی‌کند.".format(host, port),
                )
        except OSError as exc:
            QMessageBox.warning(
                self, "اتصال برقرار نشد",
                "ارتباط با دستگاه/واسط ناموفق بود: {}".format(exc),
            )

    def print_test(self):
        name = self.printer.currentData()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if name:
            printer.setPrinterName(name)
            if not printer.isValid():
                QMessageBox.warning(self, "چاپگر در دسترس نیست", "چاپگر انتخاب‌شده در سیستم در دسترس نیست.")
                return
        document = QTextDocument()
        document.setHtml(
            "<html lang='fa' dir='rtl'><body style='font-family:Segoe UI,sans-serif'>"
            "<h2>آزمون چاپ Accounting App</h2><p>اگر این متن را می‌بینید، صف چاپ کار می‌کند.</p>"
            "<p>چاپگر: {}</p></body></html>".format(name or "پیش‌فرض سیستم")
        )
        document.print_(printer)
        self.status.setText("برگهٔ آزمایشی به صف چاپ ارسال شد.")
