"""Image controls, previews, bounded downloads and safe path utilities."""
import os
from urllib.parse import urlparse, unquote

import requests
from accounting_app.services.file_safety import is_managed_image_path
from PySide2.QtWidgets import (
    QLineEdit, QApplication, QMessageBox, QGraphicsScene, QGraphicsView,
    QGraphicsPixmapItem, QToolButton, QStyle, QPushButton, QHBoxLayout,
    QVBoxLayout, QLabel, QDialog,
)
from PySide2.QtCore import Qt, QMimeData
from PySide2.QtGui import QKeySequence, QImage, QPixmap, QDragEnterEvent, QDropEvent



def download_image(url, max_bytes=15 * 1024 * 1024):
    """Download an image with finite timeouts and a response-size limit."""
    chunks = []
    total = 0
    with requests.get(url, timeout=(3.05, 10), stream=True) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("حجم تصویر از حد مجاز ۱۵ مگابایت بیشتر است.")
            chunks.append(chunk)
    return b"".join(chunks)


def _normalize_path(path_or_url: str) -> str:
    if path_or_url.startswith("file:///"):
        p = urlparse(path_or_url)
        local = unquote(p.path)
        if os.name == "nt" and local.startswith('/'):
            local = local[1:]
        return local
    return path_or_url

# Image input management class
class ImageLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.image_data = None

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Paste):
            cb = QApplication.clipboard()
            md = cb.mimeData()
            if md.hasImage():
                self._set_image(md.imageData())
                return
            elif md.hasText():
                self._handle_text(md.text())
                return
        super().keyPressEvent(e)

    def insertFromMimeData(self, source: QMimeData):
        if source.hasImage():
            self._set_image(source.imageData())
        elif source.hasUrls():
            u = source.urls()[0]
            local = u.toLocalFile() or u.toString()
            self._handle_url(local)
        elif source.hasText():
            self._handle_text(source.text())
        else:
            super().insertFromMimeData(source)

    def dragEnterEvent(self, e: QDragEnterEvent):
        md = e.mimeData()
        if md.hasImage() or md.hasUrls() or md.hasText():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dropEvent(self, e: QDropEvent):
        md = e.mimeData()
        if md.hasImage():
            self._set_image(md.imageData())
            e.acceptProposedAction()
        elif md.hasUrls():
            u = md.urls()[0]
            local = u.toLocalFile() or u.toString()
            self._handle_url(local)
            e.acceptProposedAction()
        elif md.hasText():
            self._handle_text(md.text())
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    def _handle_url(self, url):
        if url.startswith("file:///"):
            path = _normalize_path(url)
            img = QImage(path)
            if not img.isNull():
                self._set_image(img)
            else:
                self.setText(url)
        elif url.startswith("http://") or url.startswith("https://"):
            try:
                img = QImage()
                img.loadFromData(download_image(url))
                if not img.isNull():
                    self._set_image(img)
                else:
                    self.setText(url)
            except Exception as e:
                QMessageBox.warning(self, "خطا", f"خطا در بارگذاری تصویر از URL: {e}")
                self.setText(url)
        else:
            self.setText(url)

    def _handle_text(self, text):
        if text.startswith("file:///") or text.startswith("http://") or text.startswith("https://"):
            self._handle_url(text)
        else:
            self.setText(text)

    def _set_image(self, img: QImage):
        self.image_data = img
        self.setText("[تصویر]")
        parent = self.parent()
        while parent is not None:
            set_thumbnail = getattr(parent, "set_thumbnail", None)
            if callable(set_thumbnail):
                set_thumbnail(self, img)
                break
            parent = parent.parent()

# Image preview dialog class
class PreviewDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("پیش‌نمایش تصویر")
        self.setModal(True)
        self._zoom = 1.0

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "خطا در نمایش", f"نمی‌توان تصویر را بارگذاری کرد:\n{image_path}")
            self.reject()
            return

        self.scene = QGraphicsScene(self)
        self.item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.item)

        self.view = QGraphicsView(self.scene)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)

        btn_zoom_in = QToolButton()
        btn_zoom_in.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
        btn_zoom_in.clicked.connect(self.zoom_in)

        btn_zoom_out = QToolButton()
        btn_zoom_out.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        btn_zoom_out.clicked.connect(self.zoom_out)

        btn_close = QPushButton("بستن")
        btn_close.clicked.connect(self.close)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_zoom_in)
        btn_layout.addWidget(btn_zoom_out)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.view)
        main_layout.addLayout(btn_layout)
        self.resize(800, 600)

    def zoom_in(self):
        self._zoom *= 1.25
        self._apply_zoom()

    def zoom_out(self):
        self._zoom /= 1.25
        self._apply_zoom()

    def _apply_zoom(self):
        self.view.resetTransform()
        self.view.scale(self._zoom, self._zoom)

# Data entry dialog class
