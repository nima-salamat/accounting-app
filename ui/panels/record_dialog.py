"""Record editor dialog and field widgets for the generic CRUD table."""
import os
import shutil
import uuid
from decimal import Decimal

from peewee import BooleanField, DateField, DateTimeField, DecimalField, FloatField, ForeignKeyField, Model
from PySide2.QtWidgets import (
    QLineEdit, QVBoxLayout, QHBoxLayout, QDialog, QLabel, QCheckBox,
    QFileDialog, QComboBox, QPushButton, QMessageBox,
)
from PySide2.QtGui import QImage, QPixmap, QDoubleValidator
from PySide2.QtCore import Qt

from ui.panels.date_utils import from_jalali, to_jalali
from ui.panels.image_widgets import ImageLineEdit, _normalize_path, download_image


class RecordDialog(QDialog):
    def __init__(self, fields, model, image_fields=None, labels=None, initial=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("رکورد")
        self.fields = fields
        self.image_fields = image_fields or []
        self.labels = labels or {}
        self.initial = initial or {}
        self.data = {}
        self.image_data = {}

        layout = QVBoxLayout(self)
        self.widgets = {}
        for name, field in fields.items():
            lbl = QLabel(self.labels.get(name, name))
            widget = self._make_widget(name, field)
            self.widgets[name] = widget
            row = QHBoxLayout()
            row.addWidget(lbl)
            row.addWidget(widget)
            layout.addLayout(row)

        btn_ok = QPushButton("تأیید")
        btn_ok.clicked.connect(self.accept_data)
        layout.addWidget(btn_ok)

    def _make_widget(self, name, field):
        val = self.initial.get(name)
        if hasattr(field, "choices") and field.choices:
            w = QComboBox()
            for choice in field.choices:
                if isinstance(choice, (list, tuple)) and len(choice) == 2:
                    w.addItem(str(choice[1]), choice[0])
                else:
                    w.addItem(str(choice), choice)
            if val is not None:
                idx = w.findData(val)
                if idx >= 0:
                    w.setCurrentIndex(idx)
            return w

        if isinstance(field, ForeignKeyField):
            w = QComboBox()
            w.addItem("—", None)
            for obj in field.rel_model.select():
                w.addItem(str(obj), obj)
            if val is not None:
                for i in range(w.count()):
                    data = w.itemData(i)
                    if data and ((isinstance(val, Model) and data.get_id() == val.get_id()) or data == val):
                        w.setCurrentIndex(i)
                        break
            return w

        if isinstance(field, BooleanField):
            w = QCheckBox()
            w.setChecked(bool(val))
            return w

        if isinstance(field, DateField):
            w = QLineEdit()
            w.setPlaceholderText("YYYY-MM-DD (شمسی)")
            if val:
                w.setText(to_jalali(val))
            return w

        if isinstance(field, DateTimeField):
            w = QLineEdit()
            w.setPlaceholderText("YYYY-MM-DD HH:MM:SS (شمسی)")
            if val:
                w.setText(to_jalali(val))
            return w

        if isinstance(field, (DecimalField, FloatField)):
            w = QLineEdit()
            w.setValidator(QDoubleValidator())
            if val is not None:
                w.setText(str(val))
            return w

        if name in self.image_fields:
            w = ImageLineEdit()
            w.setReadOnly(True)
            if val:
                w.setText(str(val))
            btn = QPushButton("جستجو…")
            btn.setMaximumWidth(30)
            btn.clicked.connect(lambda: self._select_image(w))
            thumbnail = QLabel()
            thumbnail.setFixedSize(100, 100)
            thumbnail.setAlignment(Qt.AlignCenter)
            container = QWidget()
            row = QHBoxLayout(container)
            row.addWidget(w)
            row.addWidget(btn)
            row.addWidget(thumbnail)
            self.image_data[name] = None
            if val:
                img = QImage(str(val))
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img).scaled(100, 100, Qt.KeepAspectRatio)
                    thumbnail.setPixmap(pixmap)
            return container

        w = QLineEdit()
        if val:
            w.setText(str(val))
        return w

    def _select_image(self, le):
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب تصویر")
        if path:
            le.setText(path)
            img = QImage(path)
            if not img.isNull():
                le.image_data = img
                self.set_thumbnail(le, img)

    def set_thumbnail(self, le, img):
        container = le.parent()
        if container is not None:
            thumbnail = container.layout().itemAt(2).widget()
            pixmap = QPixmap.fromImage(img).scaled(100, 100, Qt.KeepAspectRatio)
            thumbnail.setPixmap(pixmap)

    def accept_data(self):
        for name, field in self.fields.items():
            w = self.widgets[name]
            try:
                if hasattr(field, "choices") and field.choices:
                    self.data[name] = w.currentData()
                    continue
                if isinstance(field, ForeignKeyField):
                    self.data[name] = w.currentData()
                elif isinstance(field, BooleanField):
                    self.data[name] = w.isChecked()
                elif isinstance(field, DateField):
                    jalali_str = w.text().strip()
                    self.data[name] = from_jalali(jalali_str) if jalali_str else None
                elif isinstance(field, DateTimeField):
                    jalali_str = w.text().strip()
                    self.data[name] = from_jalali(jalali_str, is_datetime=True) if jalali_str else None
                elif isinstance(field, (DecimalField, FloatField)):
                    txt = w.text().strip()
                    self.data[name] = Decimal(txt) if isinstance(field, DecimalField) else float(txt) if txt else None
                elif name in self.image_fields:
                    container = w
                    le = container.layout().itemAt(0).widget()
                    if le.image_data:
                        fname = f"{uuid.uuid4()}.png"
                        dst = os.path.join("images", fname)
                        os.makedirs("images", exist_ok=True)
                        if le.image_data.save(dst, "PNG"):
                            self.data[name] = dst
                        else:
                            QMessageBox.warning(self, "خطا در ذخیره", f"نمی‌توان تصویر را در:\n{dst} ذخیره کرد")
                            self.data[name] = None
                    else:
                        path = le.text().strip()
                        if path:
                            if path.startswith("file:///"):
                                path = _normalize_path(path)
                            if os.path.isfile(path):
                                ext = os.path.splitext(path)[1]
                                dst = os.path.join("images", f"{uuid.uuid4()}{ext}")
                                os.makedirs("images", exist_ok=True)
                                shutil.copy(path, dst)
                                self.data[name] = dst
                            elif path.startswith("http://") or path.startswith("https://"):
                                try:
                                    img = QImage()
                                    img.loadFromData(download_image(path))
                                    if not img.isNull():
                                        fname = f"{uuid.uuid4()}.png"
                                        dst = os.path.join("images", fname)
                                        os.makedirs("images", exist_ok=True)
                                        img.save(dst, "PNG")
                                        self.data[name] = dst
                                    else:
                                        self.data[name] = None
                                except Exception as e:
                                    QMessageBox.warning(self, "خطا", f"خطا در دانلود تصویر: {e}")
                                    self.data[name] = None
                            else:
                                self.data[name] = path
                        else:
                            self.data[name] = None
                else:
                    self.data[name] = w.text().strip()
            except Exception as e:
                QMessageBox.critical(self, "ورودی نامعتبر", f"خطا در '{name}': {e}")
                return
        self.accept()
