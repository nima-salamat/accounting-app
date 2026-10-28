"""Administrator UI for configuring schemas and editing custom field values."""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from accounting_app.services.schema_registry import (
    BUILTIN_ENTITIES, FIELD_TYPES, delete_custom_record, get_entity_fields,
    get_entity_values, list_entities, list_entity_records, register_field,
    save_entity_values,
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


class CustomSchemaManagement(QWidget):
    """Edit extra fields on existing rows and manage records in custom entities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self._field_widgets = {}
        self._creating = False
        self._current_fields = []
        self._entities = []

        root = QVBoxLayout(self)
        heading = QLabel("مدل‌ها و فیلدهای سفارشی")
        heading.setStyleSheet("font-size: 20px; font-weight: 700;")
        description = QLabel(
            "فیلدهای تکمیلی کنار مدل‌های اصلی ذخیره می‌شوند؛ ساختار و داده‌های حسابداری موجود دست‌نخورده می‌مانند."
        )
        description.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(description)

        toolbar = QHBoxLayout()
        self.entity_combo = QComboBox()
        self.entity_combo.setMinimumWidth(220)
        self.add_field_button = QPushButton("افزودن فیلد یا مدل")
        self.add_field_button.clicked.connect(self._add_field)
        toolbar.addWidget(QLabel("مدل:"))
        toolbar.addWidget(self.entity_combo, 1)
        toolbar.addWidget(self.add_field_button)
        root.addLayout(toolbar)

        record_bar = QHBoxLayout()
        record_bar.addWidget(QLabel("رکورد:"))
        self.record_combo = QComboBox()
        self.record_combo.setMinimumWidth(320)
        record_bar.addWidget(self.record_combo, 1)
        self.new_record_button = QPushButton("رکورد جدید")
        self.delete_record_button = QPushButton("حذف رکورد سفارشی")
        record_bar.addWidget(self.new_record_button)
        record_bar.addWidget(self.delete_record_button)
        root.addLayout(record_bar)

        self.form_host = QWidget()
        self.fields_layout = QFormLayout(self.form_host)
        self.fields_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.fields_layout.setContentsMargins(8, 10, 8, 10)
        root.addWidget(self.form_host, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.save_button = QPushButton("ذخیره فیلدها")
        self.save_button.setMinimumHeight(38)
        buttons.addWidget(self.save_button)
        root.addLayout(buttons)

        self.entity_combo.currentIndexChanged.connect(self._entity_changed)
        self.record_combo.currentIndexChanged.connect(self._record_changed)
        self.new_record_button.clicked.connect(self._new_record)
        self.delete_record_button.clicked.connect(self._delete_record)
        self.save_button.clicked.connect(self._save_values)
        self._reload_entities()

    def _selected_entity(self):
        return self.entity_combo.currentData() or self.entity_combo.currentText()

    def _is_custom_entity(self):
        key = self._selected_entity()
        return key not in BUILTIN_ENTITIES

    def _reload_entities(self, selected_key=None):
        self._entities = list_entities()
        self.entity_combo.blockSignals(True)
        self.entity_combo.clear()
        selected_index = 0
        for index, entity in enumerate(self._entities):
            self.entity_combo.addItem(entity["label"], entity["key"])
            if entity["key"] == selected_key:
                selected_index = index
        if self._entities:
            self.entity_combo.setCurrentIndex(selected_index)
        self.entity_combo.blockSignals(False)
        self._entity_changed()

    def _entity_changed(self, *_args):
        custom = self._is_custom_entity()
        self.new_record_button.setEnabled(custom)
        self.delete_record_button.setEnabled(custom)
        self._reload_records()
        self._rebuild_fields()

    def _reload_records(self, selected_record_id=None):
        key = self._selected_entity()
        self.record_combo.blockSignals(True)
        self.record_combo.clear()
        try:
            records = list_entity_records(key)
        except Exception as exc:
            records = []
            QMessageBox.warning(self, "خواندن رکوردها", str(exc))
        for record_id, label in records:
            self.record_combo.addItem(label, record_id)
        if selected_record_id:
            index = self.record_combo.findData(selected_record_id)
            self.record_combo.setCurrentIndex(index)
        elif self.record_combo.count():
            self.record_combo.setCurrentIndex(0)
        else:
            self.record_combo.setCurrentIndex(-1)
        self.record_combo.blockSignals(False)
        self._creating = self._is_custom_entity() and self.record_combo.currentIndex() < 0

    def _record_changed(self, *_args):
        self._creating = self._is_custom_entity() and self.record_combo.currentIndex() < 0
        self._rebuild_fields()

    def _new_record(self):
        if not self._is_custom_entity():
            return
        self.record_combo.setCurrentIndex(-1)
        self._creating = True
        self._rebuild_fields()

    def _clear_form(self):
        while self.fields_layout.rowCount():
            self.fields_layout.removeRow(0)
        self._field_widgets = {}

    def _rebuild_fields(self):
        self._clear_form()
        if not self._selected_entity():
            return
        try:
            self._current_fields = get_entity_fields(self._selected_entity())
        except Exception as exc:
            self.fields_layout.addRow(QLabel("خطا در خواندن فیلدها: {}".format(exc)))
            return
        record_id = self.record_combo.currentData()
        values = {}
        if record_id and not self._creating:
            try:
                values = get_entity_values(self._selected_entity(), record_id)
            except Exception as exc:
                self.fields_layout.addRow(QLabel("خطا در خواندن مقادیر: {}".format(exc)))

        if not self._current_fields:
            self.fields_layout.addRow(QLabel(
                "برای این مدل فیلد سفارشی تعریف نشده است. از «افزودن فیلد یا مدل» استفاده کنید."
            ))
            self.save_button.setEnabled(False)
            return

        for definition in self._current_fields:
            label = definition.label + (" *" if definition.is_required else "")
            kind = definition.field_type
            if kind == "boolean":
                widget = QComboBox()
                widget.addItem("— انتخاب نشده —", None)
                widget.addItem("بله", True)
                widget.addItem("خیر", False)
                if values.get(definition.field_key) is not None:
                    widget.setCurrentIndex(1 if values[definition.field_key] else 2)
            else:
                widget = QLineEdit()
                if kind == "date":
                    widget.setPlaceholderText("YYYY-MM-DD")
                elif kind == "integer":
                    widget.setPlaceholderText("عدد صحیح")
                elif kind == "decimal":
                    widget.setPlaceholderText("عدد اعشاری")
                value = values.get(definition.field_key)
                if value is not None:
                    widget.setText(str(value))
            self._field_widgets[definition.field_key] = (widget, kind)
            self.fields_layout.addRow(label, widget)
        self.save_button.setEnabled(bool(self._current_fields))

    def _add_field(self):
        dialog = AddSchemaFieldDialog(self._entities, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        payload = dialog.values()
        try:
            register_field(
                payload["model_key"], payload["field_key"], payload["field_label"],
                payload["field_type"], payload["is_required"], payload["model_label"],
            )
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "تعریف ساختار", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "تعریف ساختار", "ذخیرهٔ ساختار ناموفق بود: {}".format(exc))
            return
        self._reload_entities(payload["model_key"])
        QMessageBox.information(self, "ساختار ذخیره شد", "فیلد جدید ثبت شد؛ داده‌های قبلی تغییر نکردند.")

    def _read_widget_value(self, widget, kind):
        if kind == "boolean":
            return widget.currentData()
        return widget.text()

    def _save_values(self):
        entity_type = self._selected_entity()
        record_id = self.record_combo.currentData()
        if not self._is_custom_entity() and not record_id:
            QMessageBox.warning(self, "انتخاب رکورد", "برای افزودن فیلد به مدل اصلی، ابتدا یک رکورد موجود انتخاب کنید.")
            return
        values = {
            key: self._read_widget_value(widget, kind)
            for key, (widget, kind) in self._field_widgets.items()
        }
        try:
            saved_id = save_entity_values(
                entity_type, None if self._creating else record_id, values
            )
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "ذخیرهٔ داده", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "ذخیرهٔ داده", "ذخیره‌سازی ناموفق بود: {}".format(exc))
            return
        if self._is_custom_entity():
            self._reload_records(saved_id)
        else:
            self._reload_records(record_id)
        QMessageBox.information(self, "ذخیره شد", "مقادیر فیلدهای تکمیلی ذخیره شدند.")

    def _delete_record(self):
        entity_type = self._selected_entity()
        record_id = self.record_combo.currentData()
        if not self._is_custom_entity() or not record_id:
            return
        answer = QMessageBox.question(
            self, "حذف رکورد",
            "این رکورد از مدل سفارشی حذف شود؟ این عملیات قابل بازگشت نیست.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            delete_custom_record(entity_type, record_id)
        except Exception as exc:
            QMessageBox.warning(self, "حذف رکورد", str(exc))
            return
        self._reload_records()
        self._rebuild_fields()
