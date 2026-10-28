"""Dialog for adding an extension field or defining a new custom entity."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
)

class AddSchemaFieldDialog(QDialog):
    def __init__(self, entities, parent=None):
        super().__init__(parent)
        self.setWindowTitle("افزودن فیلد یا مدل")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.entity_key = QComboBox()
        self.entity_key.setEditable(True)
        for entity in entities:
            self.entity_key.addItem(entity["key"], entity["key"])
        self.entity_key.setEditText("")
        self.model_label = QLineEdit()
        self.model_label.setPlaceholderText("برای مدل جدید؛ مثال: مخاطبان")
        self.field_key = QLineEdit()
        self.field_key.setPlaceholderText("مثال: customer_code")
        self.field_label = QLineEdit()
        self.field_label.setPlaceholderText("عنوانی که در برنامه دیده می‌شود")
        self.field_type = QComboBox()
        self.field_type.addItems(FIELD_TYPES)
        self.required = QCheckBox("پر کردن این فیلد اجباری باشد")
        form.addRow("کلید مدل:", self.entity_key)
        form.addRow("عنوان مدل:", self.model_label)
        form.addRow("کلید فیلد:", self.field_key)
        form.addRow("عنوان فیلد:", self.field_label)
        form.addRow("نوع داده:", self.field_type)
        form.addRow("", self.required)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)

    def values(self):
        return {
            "model_key": self.entity_key.currentText().strip(),
            "model_label": self.model_label.text().strip(),
            "field_key": self.field_key.text().strip(),
            "field_label": self.field_label.text().strip(),
            "field_type": self.field_type.currentText(),
            "is_required": self.required.isChecked(),
        }
