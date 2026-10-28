"""Persian first-run installer for the administrator and extensible data schema."""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWizard, QWizardPage, QWidget,
)

from accounting_app.services.installer import complete_initial_setup
from accounting_app.services.schema_registry import BUILTIN_ENTITIES, FIELD_TYPES


class AdministratorPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("ساخت مدیر برنامه")
        self.setSubTitle("حساب مدیر را ایجاد کنید. هیچ رمز پیش‌فرضی ساخته نمی‌شود.")
        layout = QFormLayout(self)
        self.username = QLineEdit()
        self.username.setPlaceholderText("حداقل ۴ نویسه")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("حداقل ۴ نویسه")
        self.confirmation = QLineEdit()
        self.confirmation.setEchoMode(QLineEdit.Password)
        self.confirmation.setPlaceholderText("رمز عبور را دوباره وارد کنید")
        layout.addRow("نام کاربری مدیر:", self.username)
        layout.addRow("رمز عبور:", self.password)
        layout.addRow("تکرار رمز عبور:", self.confirmation)
        self.registerField("admin_username*", self.username)
        self.registerField("admin_password*", self.password)
        self.registerField("admin_confirmation*", self.confirmation)

    def validatePage(self):
        if len(self.username.text().strip()) < 4:
            QMessageBox.warning(self, "اطلاعات ناقص", "نام کاربری باید حداقل ۴ نویسه داشته باشد.")
            return False
        if len(self.password.text()) < 4:
            QMessageBox.warning(self, "اطلاعات ناقص", "رمز عبور باید حداقل ۴ نویسه داشته باشد.")
            return False
        if self.password.text() != self.confirmation.text():
            QMessageBox.warning(self, "تطبیق رمز", "تکرار رمز عبور با رمز عبور یکسان نیست.")
            return False
        return True


class SchemaPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("ساختار داده‌ها")
        self.setSubTitle(
            "برای افزودن فیلد، یک ردیف اضافه کنید. مدل‌های شناخته‌شده را انتخاب کنید؛ "
            "برای ساخت مدل جدید، یک کلید انگلیسی و عنوان فارسی وارد کنید."
        )
        root = QVBoxLayout(self)
        help_label = QLabel(
            "کلیدها باید انگلیسی و با حروف کوچک باشند؛ مثال: products، contacts، "
            "serial_number. فیلدهای اضافی در لایهٔ جدا ذخیره می‌شوند و جدول‌های قبلی تغییر مخرب نمی‌کنند."
        )
        help_label.setWordWrap(True)
        root.addWidget(help_label)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "کلید مدل", "عنوان مدل سفارشی", "کلید فیلد", "عنوان فیلد", "نوع داده", "الزامی"
        ])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setMinimumHeight(330)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("افزودن فیلد")
        self.remove_button = QPushButton("حذف ردیف انتخاب‌شده")
        self.add_button.clicked.connect(self.add_row)
        self.remove_button.clicked.connect(self.remove_row)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        root.addLayout(buttons)
        self.add_row()

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        model_key = QComboBox()
        model_key.setEditable(True)
        model_key.addItems(list(BUILTIN_ENTITIES.keys()))
        model_key.setCurrentIndex(-1)
        model_key.setEditText("")
        model_label = QTableWidgetItem("")
        field_key = QTableWidgetItem("")
        field_label = QTableWidgetItem("")
        field_type = QComboBox()
        field_type.addItems(FIELD_TYPES)
        required = QCheckBox()
        required.setToolTip("ثبت مقدار در این فیلد اجباری باشد")
        self.table.setCellWidget(row, 0, model_key)
        self.table.setItem(row, 1, model_label)
        self.table.setItem(row, 2, field_key)
        self.table.setItem(row, 3, field_label)
        self.table.setCellWidget(row, 4, field_type)
        self.table.setCellWidget(row, 5, required)

    def remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def schema_rows(self):
        rows = []
        for row in range(self.table.rowCount()):
            model_widget = self.table.cellWidget(row, 0)
            type_widget = self.table.cellWidget(row, 4)
            required_widget = self.table.cellWidget(row, 5)
            model_key = model_widget.currentText().strip() if model_widget else ""
            model_label_item = self.table.item(row, 1)
            field_key_item = self.table.item(row, 2)
            field_label_item = self.table.item(row, 3)
            model_label = model_label_item.text().strip() if model_label_item else ""
            field_key = field_key_item.text().strip() if field_key_item else ""
            field_label = field_label_item.text().strip() if field_label_item else ""
            if not any((model_key, model_label, field_key, field_label)):
                continue
            rows.append({
                "model_key": model_key,
                "model_label": model_label,
                "field_key": field_key,
                "field_label": field_label,
                "field_type": type_widget.currentText() if type_widget else "text",
                "is_required": required_widget.isChecked() if required_widget else False,
            })
        return rows


class InitialSetupWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.installation_complete = False
        self.setWindowTitle("نصب اولیهٔ برنامه حسابداری")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(1050, 680)
        self.setWizardStyle(QWizard.ModernStyle)
        self.admin_page = AdministratorPage(self)
        self.schema_page = SchemaPage(self)
        self.addPage(self.admin_page)
        self.addPage(self.schema_page)
        self.setButtonText(QWizard.FinishButton, "ایجاد پایگاه داده و شروع")
        self.setButtonText(QWizard.NextButton, "بعدی")
        self.setButtonText(QWizard.BackButton, "بازگشت")
        self.setButtonText(QWizard.CancelButton, "انصراف")
        self.setStyleSheet("""
            QWizard, QWizardPage { background: #f7f8fc; color: #202638; font-size: 13px; }
            QLabel { color: #202638; }
            QLineEdit, QComboBox, QTableWidget {
                background: white; color: #202638; border: 1px solid #cbd2e1;
                border-radius: 6px; padding: 7px;
            }
            QPushButton {
                background: #4559c7; color: white; border: 0; border-radius: 7px;
                padding: 9px 16px; min-width: 90px;
            }
            QPushButton:hover { background: #3446a8; }
        """)

    def accept(self):
        try:
            complete_initial_setup(
                self.admin_page.username.text(),
                self.admin_page.password.text(),
                self.admin_page.confirmation.text(),
                self.schema_page.schema_rows(),
            )
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "نصب انجام نشد", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(
                self, "خطا در نصب",
                "نصب انجام نشد و تغییرات پایگاه داده بازگردانی شد. جزئیات: {}".format(exc),
            )
            return
        self.installation_complete = True
        super().accept()
