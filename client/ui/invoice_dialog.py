"""Preview, print and PDF export for a saved sales receipt."""
from PySide6.QtCore import Qt, QSizeF, QMarginsF
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPageSize, QPageLayout
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QMessageBox, QPushButton,
    QTextBrowser, QVBoxLayout,
)

from client.ui.invoice_render import render_invoice_html
from client.ui.device_settings import device_settings
from PySide6.QtGui import QTextDocument


def configure_invoice_printer(printer, template=None):
    """Apply the same paper dimensions, orientation and margins used by the HTML preview."""
    template = template or {}
    paper = str(template.get("paper_size") or "A4")
    standard = {
        "A4": QPageSize.PageSizeId.A4,
        "A5": QPageSize.PageSizeId.A5,
        "A6": QPageSize.PageSizeId.A6,
    }
    if paper in standard:
        page_size = QPageSize(standard[paper])
    else:
        width, height = (80, 220) if paper == "receipt80" else (58, 180)
        page_size = QPageSize(
            QSizeF(width, height),
            QPageSize.Unit.Millimeter,
            "Receipt {} mm".format(width),
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
    orientation = (
        QPageLayout.Orientation.Landscape
        if template.get("orientation") == "landscape" and paper not in ("receipt80", "receipt58")
        else QPageLayout.Orientation.Portrait
    )
    try:
        margin = max(3.0, min(30.0, float(template.get("margin_mm", 12))))
    except (TypeError, ValueError):
        margin = 12.0
    layout = QPageLayout(
        page_size,
        orientation,
        QMarginsF(margin, margin, margin, margin),
        QPageLayout.Unit.Millimeter,
    )
    printer.setPageLayout(layout)


class InvoiceDialog(QDialog):
    def __init__(self, receipt, template=None, parent=None):
        super().__init__(parent)
        self.receipt = receipt or {}
        self.template = template or {}
        self.setWindowTitle("فاکتور فروش")
        self.resize(900, 780)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.preview = QTextBrowser(self)
        self.preview.setOpenExternalLinks(False)
        self.preview.setHtml(render_invoice_html(self.receipt, self.template))
        layout.addWidget(self.preview, 1)
        actions = QHBoxLayout()
        self.pdf_button = QPushButton("ذخیره به PDF")
        self.print_button = QPushButton("چاپ فاکتور")
        self.close_button = QPushButton("بستن")
        self.close_button.clicked.connect(self.accept)
        self.pdf_button.clicked.connect(self.save_pdf)
        self.print_button.clicked.connect(self.print_invoice)
        actions.addWidget(self.pdf_button)
        actions.addWidget(self.print_button)
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

    def save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیرهٔ فاکتور", "invoice-{}.pdf".format(
                self.receipt.get("day_receipt_id") or "sale"
            ), "PDF (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        configure_invoice_printer(printer, self.template)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        self.preview.document().print_(printer)
        QMessageBox.information(self, "فاکتور ذخیره شد", "فایل PDF ذخیره شد:\n{}".format(path))

    def print_invoice(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        settings = device_settings()
        printer_name = settings.get("printer_name")
        if printer_name:
            printer.setPrinterName(printer_name)
            if not printer.isValid():
                QMessageBox.warning(self, "چاپگر در دسترس نیست", "چاپگر انتخاب‌شده در تنظیمات صندوق در دسترس نیست.")
                return
        configure_invoice_printer(printer, self.template)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("چاپ فاکتور")
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.preview.document().print_(printer)



def auto_print_invoice(receipt, template=None, parent=None):
    """Send the invoice to the configured OS print queue when automatic printing is enabled."""
    settings = device_settings()
    if not settings.get("auto_print"):
        return False
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    configure_invoice_printer(printer, template)
    name = settings.get("printer_name")
    if name:
        printer.setPrinterName(name)
        if not printer.isValid():
            QMessageBox.warning(parent, "چاپگر در دسترس نیست", "چاپ خودکار فعال است، اما چاپگر تنظیم‌شده پیدا نشد.")
            return False
    document = QTextDocument()
    document.setHtml(render_invoice_html(receipt, template))
    document.print_(printer)
    return True
