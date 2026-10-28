"""Preview, print and PDF export for a saved sales receipt."""
from PySide6.QtCore import Qt
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QMessageBox, QPushButton,
    QTextBrowser, QVBoxLayout,
)

from client.ui.invoice_render import render_invoice_html


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
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        self.preview.document().print_(printer)
        QMessageBox.information(self, "فاکتور ذخیره شد", "فایل PDF ذخیره شد:\n{}".format(path))

    def print_invoice(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("چاپ فاکتور")
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.preview.document().print_(printer)
