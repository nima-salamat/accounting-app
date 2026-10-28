"""Reusable password input with an inline visibility toggle."""
from PySide6.QtWidgets import QLineEdit, QToolButton, QStyle
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtCore import QSize, Qt


class PasswordLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)
        self._eye_btn = QToolButton(self)
        self._eye_btn.setCursor(Qt.PointingHandCursor)
        self._eye_btn.setCheckable(True)
        self._eye_btn.setFixedSize(20, 20)
        self._eye_btn.setStyleSheet("border: none; padding: 0; background: transparent;")
        self._eye_btn.toggled.connect(self._on_eye_toggled)
        self._update_icon(False)
        self._update_position()
        self.textChanged.connect(self._update_position)
        self.resizeEvent = self._on_resize

    def _on_resize(self, event):
        self._update_position()
        super().resizeEvent(event)

    def _update_position(self):
        fw = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        x = self.rect().right() - fw - self._eye_btn.width() - 2
        y = (self.rect().bottom() - self._eye_btn.height()) // 2
        self._eye_btn.move(x, y)
        self.setStyleSheet(f"QLineEdit {{ padding-right: {self._eye_btn.width()+4}px; }}")

    def _on_eye_toggled(self, checked):
        self.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self._update_icon(checked)

    def _update_icon(self, visible: bool):
        size = 16
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        c = Qt.black
        p.setPen(c)
        p.drawEllipse(2, 5, 12, 6)
        if visible:
            p.setBrush(c)
            p.drawEllipse(6, 7, 4, 2)
        p.end()
        self._eye_btn.setIcon(QIcon(pm))
        self._eye_btn.setIconSize(QSize(size, size))
