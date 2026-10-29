"""Exact-sized preview, PDF and printer output for positioned invoice elements."""
from PySide6.QtCore import QRectF, QSizeF, QMarginsF, Qt, QTimer
from PySide6.QtGui import QColor, QPageSize, QPageLayout, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QGraphicsItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)

from client.ui.invoice_render import draw_invoice_page, page_dimensions, prepare_invoice_pages
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
        width, height = page_dimensions(template)
        page_size = QPageSize(
            QSizeF(width, height), QPageSize.Unit.Millimeter,
            "Receipt {} x {} mm".format(round(width), round(height)),
            QPageSize.SizeMatchPolicy.ExactMatch,
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


class InteractiveInvoiceView(QGraphicsView):
    """Invoice canvas with mouse-wheel zoom and click-drag panning."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setBackgroundBrush(QColor("#E9EDF4"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setRenderHints(self.renderHints())

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            event.ignore()
            return
        scale_now = max(0.001, self.transform().m11())
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        target = max(0.2, min(12.0, scale_now * factor))
        self.scale(target / scale_now, target / scale_now)
        event.accept()


class InvoicePreviewWidget(QFrame):
    """Reusable inline invoice preview with page navigation, zoom and mouse panning."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InvoicePreviewWorkspace")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.pages = []
        self.current_page_index = 0
        self.template = {}
        self.receipt = {}
        self.scene = QGraphicsScene(self)
        self.preview = InteractiveInvoiceView(self.scene, self)
        self.preview.setObjectName("InvoicePrintPreview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(self.preview, 1)

        self.page_info = QLabel("برای پیش‌نمایش، یک فاکتور را انتخاب کنید.")
        self.page_info.setObjectName("PageSubtitle")
        self.page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_info.setWordWrap(True)
        layout.addWidget(self.page_info)

        actions = QHBoxLayout()
        self.previous_page_button = QPushButton("صفحهٔ قبل")
        self.previous_page_button.clicked.connect(lambda: self._show_page(self.current_page_index - 1))
        self.next_page_button = QPushButton("صفحهٔ بعد")
        self.next_page_button.clicked.connect(lambda: self._show_page(self.current_page_index + 1))
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setToolTip("کوچک‌نمایی")
        self.zoom_out_button.clicked.connect(lambda: self._zoom(1.0 / 1.2))
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setToolTip("بزرگ‌نمایی")
        self.zoom_in_button.clicked.connect(lambda: self._zoom(1.2))
        self.fit_width_button = QPushButton("برازش برگه")
        self.fit_width_button.setToolTip(
            "برگهٔ ثابت را کامل در قاب جا می‌دهد؛ برای رسید حرارتی، عرض را مبنا می‌گیرد."
        )
        self.fit_width_button.clicked.connect(self.fit_width)
        actions.addWidget(self.previous_page_button)
        actions.addWidget(self.next_page_button)
        actions.addStretch(1)
        actions.addWidget(self.zoom_out_button)
        actions.addWidget(self.zoom_in_button)
        actions.addWidget(self.fit_width_button)
        layout.addLayout(actions)
        self._page_item = None

    def set_invoice(self, receipt, template=None):
        self.receipt = dict(receipt or {})
        self.pages = prepare_invoice_pages(self.receipt, template)
        if not self.pages:
            self.pages = [(self.receipt, dict(template or {}))]
        self.current_page_index = 0
        self._show_page(0)

    def clear_invoice(self):
        self.receipt = {}
        self.pages = []
        self.current_page_index = 0
        if self._page_item is not None:
            self.scene.removeItem(self._page_item)
            self._page_item = None
        self.scene.setSceneRect(QRectF())
        self.page_info.setText("برای پیش‌نمایش، یک فاکتور را انتخاب کنید.")
        self.previous_page_button.setEnabled(False)
        self.next_page_button.setEnabled(False)
        self.preview.resetTransform()

    def _show_page(self, index):
        if not self.pages:
            return
        self.current_page_index = max(0, min(len(self.pages) - 1, int(index)))
        receipt, self.template = self.pages[self.current_page_index]
        if self._page_item is not None:
            self.scene.removeItem(self._page_item)
        self._page_item = _InvoicePageItem(receipt, self.template)
        self.scene.addItem(self._page_item)
        self.scene.setSceneRect(self._page_item.boundingRect())
        width, height = page_dimensions(self.template)
        paper = self.template.get("paper_size", "A4")
        if paper in ("receipt", "receipt80", "receipt58"):
            description = "رسید حرارتی"
        else:
            orientation = "افقی" if self.template.get("orientation") == "landscape" else "عمودی"
            description = "{} · {}".format(paper, orientation)
        if len(self.pages) > 1:
            description += " · صفحهٔ {} از {}".format(self.current_page_index + 1, len(self.pages))
        self.page_info.setText("{} · {:.0f} × {:.0f} میلی‌متر".format(description, width, height))
        self.previous_page_button.setEnabled(self.current_page_index > 0)
        self.next_page_button.setEnabled(self.current_page_index < len(self.pages) - 1)
        QTimer.singleShot(0, self.fit_width)

    def _zoom(self, factor):
        scale_now = max(0.001, self.preview.transform().m11())
        target = max(0.2, min(12.0, scale_now * factor))
        self.preview.scale(target / scale_now, target / scale_now)

    def fit_width(self):
        if self._page_item is None:
            return
        viewport = self.preview.viewport().size()
        viewport_width = max(1, viewport.width() - 8)
        viewport_height = max(1, viewport.height() - 8)
        bounds = self._page_item.boundingRect()
        page_width = max(1.0, bounds.width())
        page_height = max(1.0, bounds.height())
        width_scale = viewport_width / page_width
        paper = str(self.template.get("paper_size") or "A4")
        if paper in ("receipt", "receipt80", "receipt58"):
            # Thermal rolls can be very tall; fill their usable width and scroll vertically.
            scale = width_scale
        else:
            # Fixed sheets should initially fit completely in the side preview, avoiding
            # the over-zoomed look of opening a second, full-screen preview dialog.
            height_scale = viewport_height / page_height
            scale = min(width_scale, height_scale)
        self.preview.resetTransform()
        self.preview.scale(scale, scale)
        self.preview.horizontalScrollBar().setValue(0)
        self.preview.verticalScrollBar().setValue(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._page_item is not None:
            QTimer.singleShot(0, self.fit_width)


class InvoiceDialog(QDialog):
    def __init__(self, receipt, template=None, parent=None):
        super().__init__(parent)
        self.receipt = receipt or {}
        self.pages = prepare_invoice_pages(self.receipt, template)
        if not self.pages:
            self.pages = [(self.receipt, dict(template or {}))]
        self.current_page_index = 0
        self.template = dict(self.pages[0][1])
        self.setWindowTitle("پیش‌نمایش فاکتور · چاپ و PDF")
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1480, max(800, int(available.width() * 0.94))),
                min(1180, max(600, int(available.height() * 0.92))),
            )
        else:
            self.resize(1200, 900)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.scene = QGraphicsScene(self)
        page_receipt, page_template = self.pages[0]
        self.page_item = _InvoicePageItem(page_receipt, page_template)
        self.scene.addItem(self.page_item)
        self.scene.setSceneRect(self.page_item.boundingRect())
        self.preview = InteractiveInvoiceView(self.scene, self)
        self.preview.setObjectName("InvoicePrintPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.preview, 1)

        self.page_info = QPushButton(self._page_info_text())
        self.page_info.setEnabled(False)
        layout.addWidget(self.page_info)
        actions = QHBoxLayout()
        self.previous_page_button = QPushButton("صفحهٔ قبل")
        self.next_page_button = QPushButton("صفحهٔ بعد")
        self.previous_page_button.clicked.connect(lambda: self._show_page(self.current_page_index - 1))
        self.next_page_button.clicked.connect(lambda: self._show_page(self.current_page_index + 1))
        self.fit_width_button = QPushButton("برازش عرض صفحه")
        self.fit_width_button.setToolTip("بزرگ‌نمایی برگه تا عرض فضای پیش‌نمایش")
        self.fit_width_button.clicked.connect(self._fit_page)
        self.pdf_button = QPushButton("ذخیره به PDF")
        self.print_button = QPushButton("چاپ فاکتور")
        self.close_button = QPushButton("بستن")
        self.close_button.clicked.connect(self.accept)
        self.pdf_button.clicked.connect(self.save_pdf)
        self.print_button.clicked.connect(self.print_invoice)
        actions.addWidget(self.previous_page_button)
        actions.addWidget(self.next_page_button)
        actions.addWidget(self.fit_width_button)
        actions.addStretch(1)
        actions.addWidget(self.pdf_button)
        actions.addWidget(self.print_button)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)
        self._show_page(0)
        QTimer.singleShot(0, self._fit_page)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_page)

    def _page_info_text(self):
        page_template = self.pages[self.current_page_index][1]
        width, height = page_dimensions(page_template)
        paper = page_template.get("paper_size", "A4")
        if paper in ("receipt", "receipt80", "receipt58"):
            info = "رول پیوسته · {:.0f} × {:.0f} میلی‌متر".format(width, height)
        else:
            orientation = "افقی" if page_template.get("orientation") == "landscape" else "عمودی"
            info = "{} · {} · {:.0f} × {:.0f} میلی‌متر".format(paper, orientation, width, height)
        if len(self.pages) > 1:
            info += " · صفحهٔ {} از {}".format(self.current_page_index + 1, len(self.pages))
        return info

    def _show_page(self, index):
        self.current_page_index = max(0, min(len(self.pages) - 1, int(index)))
        page_receipt, page_template = self.pages[self.current_page_index]
        old_item = self.page_item
        self.scene.removeItem(old_item)
        self.page_item = _InvoicePageItem(page_receipt, page_template)
        self.scene.addItem(self.page_item)
        self.scene.setSceneRect(self.page_item.boundingRect())
        self.template = dict(page_template)
        self.page_info.setText(self._page_info_text())
        self.previous_page_button.setEnabled(self.current_page_index > 0)
        self.next_page_button.setEnabled(self.current_page_index < len(self.pages) - 1)
        self._fit_page()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_page()

    def _fit_page(self):
        """Fit paper to the available width, not the height of a wide preview window."""
        if not hasattr(self, "page_item"):
            return
        viewport_width = max(1, self.preview.viewport().width() - 8)
        page_width = max(1.0, self.page_item.boundingRect().width())
        scale = viewport_width / page_width
        self.preview.resetTransform()
        self.preview.scale(scale, scale)
        self.preview.horizontalScrollBar().setValue(0)
        self.preview.verticalScrollBar().setValue(0)

    def _paint_invoice(self, printer):
        pages = prepare_invoice_pages(self.receipt, self.template)
        if not pages:
            pages = [(self.receipt, self.template)]
        configure_invoice_printer(printer, pages[0][1])
        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError("شروع چاپگر یا خروجی PDF ناموفق بود.")
        try:
            scale = float(printer.resolution()) / 25.4
            painter.scale(scale, scale)
            for page_index, (page_receipt, page_template) in enumerate(pages):
                if page_index:
                    if not printer.newPage():
                        raise RuntimeError("ایجاد صفحهٔ بعدی در چاپگر یا PDF ناموفق بود.")
                    painter.resetTransform()
                    painter.scale(scale, scale)
                width, height = page_dimensions(page_template)
                draw_invoice_page(painter, QRectF(0, 0, width, height), page_receipt, page_template)
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
        configure_invoice_printer(printer, self.pages[0][1])
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
    pages = prepare_invoice_pages(receipt or {}, template)
    if not pages:
        pages = [(receipt or {}, dict(template or {}))]
    configure_invoice_printer(printer, pages[0][1])
    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.warning(parent, "خطا در چاپ", "چاپگر قابل شروع نیست.")
        return False
    try:
        scale = float(printer.resolution()) / 25.4
        painter.scale(scale, scale)
        for page_index, (page_receipt, page_template) in enumerate(pages):
            if page_index:
                if not printer.newPage():
                    raise RuntimeError("ایجاد صفحهٔ بعدی در چاپگر ناموفق بود.")
                painter.resetTransform()
                painter.scale(scale, scale)
            width, height = page_dimensions(page_template)
            draw_invoice_page(painter, QRectF(0, 0, width, height), page_receipt, page_template)
    except Exception as exc:
        QMessageBox.warning(parent, "خطا در چاپ", str(exc))
        return False
    finally:
        painter.end()
    return True
