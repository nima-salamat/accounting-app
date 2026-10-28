"""Reusable, validated record editor built from API field specifications."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)


class ImageFilePicker(QWidget):
    """Optional local image selection; the selected file is uploaded separately to the server."""
    def __init__(self, current_server_image=None, parent=None):
        super().__init__(parent)
        self.path = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(
            "تصویر فعلی: {}".format(current_server_image)
            if current_server_image else "بدون تصویر (اختیاری)"
        )
        self.label.setWordWrap(True)
        self.button = QPushButton("انتخاب عکس…")
        self.button.clicked.connect(self.pick)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.button)

    def pick(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "انتخاب عکس محصول", "",
            "تصاویر (*.png *.jpg *.jpeg *.webp *.gif)",
        )
        if path:
            self.path = path
            self.label.setText(path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])


class RecordDialog(QDialog):
    def __init__(self, title, fields, record=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(470)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.fields = fields
        self.record = dict(record or {})
        self.inputs = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        layout.addWidget(heading)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        for spec in fields:
            key = spec["key"]
            kind = spec.get("kind", "text")
            value = self.record.get(key, spec.get("default"))
            if kind == "image":
                widget = ImageFilePicker(self.record.get("image_path"), self)
            elif kind == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(value))
            elif kind == "select":
                widget = QComboBox()
                for label, option in spec.get("choices", []):
                    widget.addItem(label, option)
                index = widget.findData(value)
                if index >= 0:
                    widget.setCurrentIndex(index)
            else:
                widget = QLineEdit()
                if kind == "password":
                    widget.setEchoMode(QLineEdit.EchoMode.Password)
                elif kind == "number":
                    widget.setValidator(QDoubleValidator(0.0, 1e15, 4, widget))
                elif kind == "integer":
                    widget.setValidator(QDoubleValidator(0, 1e9, 0, widget))
                if kind != "password" and value is not None:
                    widget.setText(str(value))
                widget.setPlaceholderText(spec.get("placeholder", ""))
            self.inputs[key] = widget
            label = QLabel(spec["label"] + ("  *" if spec.get("required") else ""))
            label.setMinimumWidth(145)
            form.addRow(label, widget)
        layout.addLayout(form)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #D64045;")
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        try:
            self.values()
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()

    def values(self):
        output = {}
        for spec in self.fields:
            key, kind = spec["key"], spec.get("kind", "text")
            widget = self.inputs[key]
            if kind == "image":
                if widget.path:
                    output[key] = widget.path
                continue
            if kind == "bool":
                output[key] = widget.isChecked()
                continue
            if kind == "select":
                output[key] = widget.currentData()
                continue
            raw = widget.text().strip()
            if kind == "password" and not raw:
                if spec.get("required") and not self.record:
                    raise ValueError("برای ساخت حساب، رمز عبور الزامی است.")
                continue
            if not raw:
                if spec.get("required"):
                    raise ValueError("وارد کردن «{}» الزامی است.".format(spec["label"]))
                if spec.get("nullable") or key in self.record:
                    output[key] = None
                continue
            if kind == "integer":
                try:
                    number = int(raw)
                except ValueError as exc:
                    raise ValueError("«{}» باید عدد صحیح باشد.".format(spec["label"])) from exc
                if number < 0:
                    raise ValueError("«{}» نمی‌تواند منفی باشد.".format(spec["label"]))
                output[key] = number
            elif kind == "number":
                try:
                    number = float(raw)
                except ValueError as exc:
                    raise ValueError("«{}» باید عدد باشد.".format(spec["label"])) from exc
                if number < 0:
                    raise ValueError("«{}» نمی‌تواند منفی باشد.".format(spec["label"]))
                output[key] = raw
            else:
                output[key] = raw
        return output
