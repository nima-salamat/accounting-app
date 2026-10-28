"""Exact-sized preview, PDF and printer output for positioned invoice elements."""
from PySide6.QtCore import QRectF, QSizeF, QMarginsF, Qt
from PySide6.QtGui import QColor, QPageSize, QPageLayout, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QGraphicsItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout,
)

from client.ui.invoice_render import draw_invoice_page, page_dimensions
from client.ui.device_settings import device_settings


def configure_invoice_printer(printer, template=None):
    """Use the actual paper size/orientation; layout positions are drawn in millimetres."""
    template = template or {}
    paper = str(template.get("paper_size") or "A4")
    paper_key = "receipt80" if paper == "receipt" else paper
    standard = {
        "A4": QPageSize.PageSizeId.A4,
        "A5": QPageSize.PageSizeId.A5,
        "A6": QPageSize.PageSizeId.A6,
    }
    if paper_key in standard:
        page_size = QPageSize(standard[paper_key])
    else:
        width, height = (80, 220) if paper_key == "receipt80" else (58, 180)
        page_size = QPageSize(
            QSizeF(width, height), QPageSize.Unit.Millimeter,
            "Receipt {} mm".format(width), QPageSize.SizeMatchPolicy.ExactMatch,
        )
    orientation = (
        QPageLayout.Orientation.Landscape
        if template.get("orientation") == "landscape" and paper_key not in ("receipt80", "receipt58")
        else QPageLayout.Orientation.Portrait
    )
    # All positions are measured from the physical sheet origin; margins are a canvas guide,
    # not an additional printer offset that would otherwise shift every saved element.
    layout = QPageLayout(
        page_size, orientation, QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter,
    )
    layout.setMode(QPageLayout.Mode.FullPageMode)
    printer.setPageLayout(layout)


class _InvoicePageItem(QGraphicsItem):
    def __init__(self, receipt, template):
        super().__init__()
        self.receipt = receipt or {}
        self.template = dict(template or {})
        self.width_mm, self.height_mm = page_dimensions(self.template)
        self.setZValue(-10)

    def boundingRect(self):
        return QRectF(0, 0, self.width_mm, self.height_mm)

    def paint(self, painter, option, widget=None):
        draw_invoice_page(
            painter, QRectF(0, 0, self.width_mm, self.height_mm),
            self.receipt, self.template, editor=False,
        )


class InvoiceDialog(QDialog):
    def __init__(self, receipt, template=None, parent=None):
        super().__init__(parent)
        self.receipt = receipt or {}
        self.template = dict(template or {})
        self.setWindowTitle("پیش‌نمایش فاکتور · چاپ و PDF")
        self.resize(1000, 820)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.scene = QGraphicsScene(self)
        self.page_item = _InvoicePageItem(self.receipt, self.template)
        self.scene.addItem(self.page_item)
        self.scene.setSceneRect(self.page_item.boundingRect())
        self.preview = QGraphicsView(self.scene, self)
        self.preview.setObjectName("InvoicePrintPreview")
        self.preview.setBackgroundBrush(QColor("#E9EDF4"))
        self.preview.setFrameShape(self.preview.Shape.NoFrame)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setRenderHints(self.preview.renderHints())
        layout.addWidget(self.preview, 1)

        self.page_info = QPushButton(self._page_info_text())
        self.page_info.setEnabled(False)
        layout.addWidget(self.page_info)
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
        self._fit_page()

    def _page_info_text(self):
        width, height = page_dimensions(self.template)
        paper = self.template.get("paper_size", "A4")
        orientation = "افقی" if self.template.get("orientation") == "landscape" else "عمودی"
        return "{} · {} · {:.0f} × {:.0f} mm".format(paper, orientation, width, height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_page()

    def _fit_page(self):
        if hasattr(self, "page_item"):
            self.preview.fitInView(self.page_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _paint_invoice(self, printer):
        configure_invoice_printer(printer, self.template)
        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError("شروع چاپگر یا خروجی PDF ناموفق بود.")
        try:
            scale = float(printer.resolution()) / 25.4
            painter.scale(scale, scale)
            width, height = page_dimensions(self.template)
            draw_invoice_page(painter, QRectF(0, 0, width, height), self.receipt, self.template)
        finally:
            painter.end()

    def save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیرهٔ فاکتور",
            "invoice-{}.pdf".format(self.receipt.get("day_receipt_id") or "sale"),
            "PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        try:
            self._paint_invoice(printer)
        except Exception as exc:
            QMessageBox.warning(self, "خطا در خروجی PDF", str(exc))
            return
        QMessageBox.information(self, "فاکتور ذخیره شد", "PDF با اندازه و جهت انتخاب‌شده ذخیره شد:\n{}".format(path))

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
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        try:
            self._paint_invoice(printer)
        except Exception as exc:
            QMessageBox.warning(self, "خطا در چاپ", str(exc))


def auto_print_invoice(receipt, template=None, parent=None):
    """Print directly from the same millimetre layout used by the editor preview."""
    settings = device_settings()
    if not settings.get("auto_print"):
        return False
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    name = settings.get("printer_name")
    if name:
        printer.setPrinterName(name)
        if not printer.isValid():
            QMessageBox.warning(parent, "چاپگر در دسترس نیست", "چاپ خودکار فعال است، اما چاپگر تنظیم‌شده پیدا نشد.")
            return False
    configure_invoice_printer(printer, template)
    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.warning(parent, "خطا در چاپ", "چاپگر قابل شروع نیست.")
        return False
    try:
        painter.scale(float(printer.resolution()) / 25.4, float(printer.resolution()) / 25.4)
        width, height = page_dimensions(template)
        draw_invoice_page(painter, QRectF(0, 0, width, height), receipt, template)
    finally:
        painter.end()
    return True
