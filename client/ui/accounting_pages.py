"""Modular accountant workspaces: journals, fiscal periods, accounting reports and staff audit."""
import json

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QHeaderView, QWidget,
)

from client.ui.permissions import can_access
from client.ui.currency import (
    currency_label, format_currency, format_display_amount, to_base_amount,
)


ACCOUNT_TYPE_LABELS = {
    "asset": "دارایی",
    "liability": "بدهی",
    "equity": "حقوق مالکانه",
    "income": "درآمد",
    "expense": "هزینه",
}


class JournalLineEditor(QFrame):
    def __init__(self, accounts, on_change, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        self.account = QComboBox()
        self.account.setMinimumWidth(200)
        for account in accounts:
            self.account.addItem(
                "{} · {}".format(account["code"], account["name"]), account["id"]
            )
        self.description = QLineEdit()
        self.description.setPlaceholderText("شرح ردیف")
        self.debit = QDoubleSpinBox()
        self.credit = QDoubleSpinBox()
        for control in (self.debit, self.credit):
            control.setRange(0, 999999999999.99)
            control.setDecimals(2)
            control.setSingleStep(10)
            control.setMinimumWidth(130)
            control.setSuffix(" " + currency_label())
        self.debit.setPrefix("بدهکار ")
        self.credit.setPrefix("بستانکار ")
        self.remove_button = QPushButton("حذف")
        self.remove_button.setObjectName("DangerButton")
        layout.addWidget(self.account, 2)
        layout.addWidget(self.description, 2)
        layout.addWidget(self.debit, 1)
        layout.addWidget(self.credit, 1)
        layout.addWidget(self.remove_button)
        self.debit.valueChanged.connect(on_change)
        self.credit.valueChanged.connect(on_change)


class ManualJournalDialog(QDialog):
    def __init__(self, accounts, parent=None):
        super().__init__(parent)
        self.accounts = accounts
        self.lines = []
        self.setWindowTitle("ثبت سند حسابداری دستی")
        self.resize(1050, 700)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        title = QLabel("سند روزنامهٔ دوطرفه")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "سند فقط وقتی ثبت می‌شود که حداقل دو ردیف داشته باشد و جمع بدهکار دقیقاً با بستانکار برابر باشد."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        form_card = QFrame()
        form_card.setObjectName("Card")
        form = QFormLayout(form_card)
        form.setContentsMargins(15, 12, 15, 12)
        self.entry_date = QDateEdit(QDate.currentDate())
        self.entry_date.setCalendarPopup(True)
        self.entry_date.setDisplayFormat("yyyy-MM-dd")
        self.description = QLineEdit()
        self.description.setPlaceholderText("مثلاً پرداخت اجارهٔ دفتر")
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("شمارهٔ سند کاغذی یا مرجع (اختیاری)")
        form.addRow("تاریخ سند", self.entry_date)
        form.addRow("شرح سند", self.description)
        form.addRow("مرجع", self.reference)
        root.addWidget(form_card)

        header = QHBoxLayout()
        for text in ("حساب", "شرح ردیف", "بدهکار", "بستانکار"):
            label = QLabel(text)
            label.setObjectName("MetricLabel")
            header.addWidget(label, 1)
        header.addWidget(QLabel(""))
        root.addLayout(header)
        self.line_host = QWidget()
        self.line_layout = QVBoxLayout(self.line_host)
        self.line_layout.setContentsMargins(0, 0, 0, 0)
        self.line_layout.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.line_host)
        root.addWidget(scroll, 1)

        action_row = QHBoxLayout()
        self.add_line_button = QPushButton("افزودن ردیف +")
        self.add_line_button.clicked.connect(self.add_line)
        self.totals = QLabel()
        self.totals.setObjectName("MetricValue")
        action_row.addWidget(self.add_line_button)
        action_row.addStretch(1)
        action_row.addWidget(self.totals)
        root.addLayout(action_row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ثبت قطعی سند")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.add_line()
        self.add_line()
        self._update_totals()

    def add_line(self):
        row = JournalLineEditor(self.accounts, self._update_totals, self)
        row.remove_button.clicked.connect(lambda _checked=False, item=row: self.remove_line(item))
        self.lines.append(row)
        self.line_layout.addWidget(row)
        self._update_totals()

    def remove_line(self, row):
        if len(self.lines) <= 2:
            QMessageBox.information(self, "حداقل ردیف", "سند باید دست‌کم دو ردیف داشته باشد.")
            return
        if row in self.lines:
            self.lines.remove(row)
            row.setParent(None)
            row.deleteLater()
        self._update_totals()

    def _totals(self):
        debit = round(sum(row.debit.value() for row in self.lines), 2)
        credit = round(sum(row.credit.value() for row in self.lines), 2)
        return debit, credit

    def _update_totals(self, *_args):
        debit, credit = self._totals()
        difference = round(debit - credit, 2)
        self.totals.setText(
            "بدهکار {}   |   بستانکار {}   |   اختلاف {}".format(
                format_display_amount(debit), format_display_amount(credit),
                format_display_amount(difference, signed=True),
            )
        )
        self.totals.setStyleSheet("color:#17846D;" if difference == 0 and debit > 0 else "color:#C74455;")

    def _validate(self):
        if not self.description.text().strip():
            QMessageBox.warning(self, "شرح الزامی", "شرح سند را وارد کنید.")
            return
        for index, row in enumerate(self.lines, 1):
            debit, credit = row.debit.value(), row.credit.value()
            if (debit > 0) == (credit > 0):
                QMessageBox.warning(
                    self, "ردیف نامعتبر",
                    "ردیف {} باید فقط مبلغ بدهکار یا فقط مبلغ بستانکار مثبت داشته باشد.".format(index),
                )
                return
        debit, credit = self._totals()
        if debit <= 0 or debit != credit:
            QMessageBox.warning(self, "سند نامتوازن", "جمع بدهکار و بستانکار باید برابر و مثبت باشند.")
            return
        self.accept()

    def values(self):
        return {
            "entry_date": self.entry_date.date().toString("yyyy-MM-dd"),
            "description": self.description.text().strip(),
            "reference": self.reference.text().strip() or None,
            "lines": [
                {
                    "account_id": row.account.currentData(),
                    "description": row.description.text().strip(),
                    "debit": float(to_base_amount(row.debit.value())),
                    "credit": float(to_base_amount(row.credit.value())),
                }
                for row in self.lines
            ],
        }


class JournalsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.items = []
        self.page = 1
        self.page_size = 25
        self.total = 0
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("اسناد حسابداری")
        title.setObjectName("PageTitle")
        subtitle = QLabel("ثبت دستی سند دوطرفه، جست‌وجوی شماره و مرجع، و مشاهدهٔ ردیف‌های قطعی.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("جست‌وجوی شماره، شرح یا مرجع…")
        self.search.returnPressed.connect(self.refresh)
        self.refresh_button = QPushButton("جست‌وجو / بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.create_button = QPushButton("سند دستی +")
        self.create_button.setObjectName("PrimaryButton")
        self.create_button.clicked.connect(self.create_entry)
        self.detail_button = QPushButton("نمایش ردیف‌ها")
        self.detail_button.clicked.connect(self.show_detail)
        header.addWidget(self.search, 2)
        header.addWidget(self.refresh_button)
        header.addWidget(self.create_button)
        header.addWidget(self.detail_button)
        root.addLayout(header)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["شناسه", "شماره سند", "تاریخ", "شرح", "مرجع", "بدهکار", "بستانکار"])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda _item: self.show_detail())
        root.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.page_label = QLabel("صفحه ۱ از ۱")
        self.page_label.setObjectName("PageSubtitle")
        self.previous_button = QPushButton("صفحهٔ قبل")
        self.next_button = QPushButton("صفحهٔ بعد")
        self.previous_button.clicked.connect(lambda: self._move(-1))
        self.next_button.clicked.connect(lambda: self._move(1))
        pager.addWidget(self.page_label)
        pager.addStretch(1)
        pager.addWidget(self.previous_button)
        pager.addWidget(self.next_button)
        root.addLayout(pager)

    def set_permissions(self, user):
        self.refresh_button.setVisible(can_access(user, "journals", "read"))
        self.detail_button.setVisible(can_access(user, "journals", "read"))
        self.create_button.setVisible(can_access(user, "journals", "create"))

    def refresh(self):
        if not self.window.api or not can_access(self.window.current_user, "journals", "read"):
            return
        self.window.run_api(
            lambda: self.window.api.list_journals_page(
                q=self.search.text().strip() or None, page=self.page, page_size=self.page_size
            ),
            self.populate,
            busy=self.refresh_button,
        )

    def populate(self, data):
        self.items = list(data.get("items") or [])
        self.page = int(data.get("page", self.page))
        self.page_size = int(data.get("page_size", self.page_size))
        self.total = int(data.get("total", len(self.items)))
        self.table.setRowCount(0)
        for row, item in enumerate(self.items):
            self.table.insertRow(row)
            values = [
                item.get("id"), item.get("entry_number"), item.get("entry_date"),
                item.get("description"), item.get("reference") or "—",
                format_currency(item.get("debit_total")),
                format_currency(item.get("credit_total")),
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value or "—"))
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row, col, cell)
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page_label.setText("صفحه {} از {} · {} سند".format(self.page, pages, self.total))
        self.previous_button.setEnabled(self.page > 1)
        self.next_button.setEnabled(self.page < pages)

    def _move(self, delta):
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        if 1 <= self.page + delta <= pages:
            self.page += delta
            self.refresh()

    def _selected(self):
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def create_entry(self):
        if not can_access(self.window.current_user, "journals", "create"):
            self.window.show_error("مجوز ثبت سند حسابداری ندارید.")
            return
        self.window.run_api(self.window.api.list_accounts, self._open_journal_dialog)

    def _open_journal_dialog(self, accounts):
        dialog = ManualJournalDialog(accounts, self)
        if dialog.exec() != ManualJournalDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.window.run_api(
            lambda: self.window.api.create_journal(
                values["entry_date"], values["description"], values["lines"], values["reference"]
            ),
            self._created,
            busy=self.create_button,
        )

    def _created(self, result):
        self.window.set_status("سند {} با توازن کامل ثبت شد.".format(result.get("entry_number", "")))
        self.refresh()
        reports = getattr(self.window, "accounting_reports_page", None)
        if reports is not None:
            reports.refresh()

    def show_detail(self):
        item = self._selected()
        if not item:
            self.window.show_error("ابتدا یک سند حسابداری را انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_journal(item["id"]),
            self._show_detail,
        )

    def _show_detail(self, item):
        lines = [
            "سند: {}".format(item.get("entry_number")),
            "تاریخ: {}".format(item.get("entry_date")),
            "شرح: {}".format(item.get("description")),
            "",
        ]
        for line in item.get("lines") or []:
            lines.append(
                "{} · {} · بدهکار {} · بستانکار {}".format(
                    line.get("account_code"), line.get("account_name"),
                    format_currency(line.get("debit")), format_currency(line.get("credit")),
                )
            )
        lines.append("")
        lines.append("جمع بدهکار: {}".format(format_currency(item.get("debit_total"))))
        lines.append("جمع بستانکار: {}".format(format_currency(item.get("credit_total"))))
        QMessageBox.information(self, "جزئیات سند", "\n".join(lines))


class CreateFiscalYearDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ایجاد سال مالی")
        self.setMinimumWidth(480)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("مثلاً سال مالی ۱۴۰۵")
        self.start_date = QDateEdit(QDate(QDate.currentDate().year(), 1, 1))
        self.end_date = QDateEdit(QDate(QDate.currentDate().year(), 12, 31))
        for picker in (self.start_date, self.end_date):
            picker.setCalendarPopup(True)
            picker.setDisplayFormat("yyyy-MM-dd")
        form.addRow("نام سال مالی", self.name)
        form.addRow("تاریخ شروع", self.start_date)
        form.addRow("تاریخ پایان", self.end_date)
        root.addLayout(form)
        footer = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        footer.button(QDialogButtonBox.StandardButton.Save).setText("ایجاد سال مالی")
        footer.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        footer.accepted.connect(self._validate)
        footer.rejected.connect(self.reject)
        root.addWidget(footer)

    def _validate(self):
        if len(self.name.text().strip()) < 2:
            QMessageBox.warning(self, "نام نامعتبر", "نام سال مالی را وارد کنید.")
            return
        if self.start_date.date() > self.end_date.date():
            QMessageBox.warning(self, "بازه نامعتبر", "شروع سال مالی باید قبل از پایان آن باشد.")
            return
        self.accept()

    def values(self):
        return {
            "name": self.name.text().strip(),
            "start_date": self.start_date.date().toString("yyyy-MM-dd"),
            "end_date": self.end_date.date().toString("yyyy-MM-dd"),
        }


class FiscalYearsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.items = []
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("مدیریت سال مالی")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "بستن سال مالی، ثبت زمان و مسئول بستن را نگه می‌دارد و ثبت‌های جدید در دورهٔ بسته را متوقف می‌کند. "
            "بازگشایی فقط با دلیل ثبت‌شده مجاز است."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.create_button = QPushButton("ایجاد سال مالی +")
        self.create_button.setObjectName("PrimaryButton")
        self.create_button.clicked.connect(self.create_year)
        self.close_button = QPushButton("بستن سال")
        self.close_button.clicked.connect(self.close_year)
        self.reopen_button = QPushButton("بازگشایی")
        self.reopen_button.clicked.connect(self.reopen_year)
        header.addWidget(self.refresh_button)
        header.addWidget(self.create_button)
        header.addWidget(self.close_button)
        header.addWidget(self.reopen_button)
        root.addLayout(header)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["شناسه", "نام", "شروع", "پایان", "وضعیت", "بسته‌شده توسط"])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

    def set_permissions(self, user):
        self.refresh_button.setVisible(can_access(user, "fiscal_years", "read"))
        self.create_button.setVisible(can_access(user, "fiscal_years", "create"))
        self.close_button.setVisible(can_access(user, "fiscal_years", "update"))
        self.reopen_button.setVisible(can_access(user, "fiscal_years", "update"))

    def refresh(self):
        if self.window.api and can_access(self.window.current_user, "fiscal_years", "read"):
            self.window.run_api(self.window.api.list_fiscal_years, self.populate, busy=self.refresh_button)

    def populate(self, data):
        self.items = list(data or [])
        self.table.setRowCount(0)
        for row, item in enumerate(self.items):
            self.table.insertRow(row)
            status = "بسته" if item.get("status") == "closed" else "باز"
            values = [
                item.get("id"), item.get("name"), item.get("start_date"), item.get("end_date"),
                status, item.get("closed_by_name") or "—",
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value or "—"))
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row, col, cell)

    def _selected(self):
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def create_year(self):
        dialog = CreateFiscalYearDialog(self)
        if dialog.exec() != CreateFiscalYearDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.window.run_api(
            lambda: self.window.api.create_fiscal_year(**values),
            lambda _r: self.refresh(),
            busy=self.create_button,
        )

    def close_year(self):
        item = self._selected()
        if not item:
            self.window.show_error("یک سال مالی را انتخاب کنید.")
            return
        if item.get("status") == "closed":
            self.window.show_error("این سال مالی از قبل بسته است.")
            return
        answer = QMessageBox.question(
            self, "بستن سال مالی",
            "با بستن «{}»، ثبت‌های این بازه متوقف می‌شوند. پیش از ادامه، مانده‌ها، رسیدهای پرداخت‌نشده و اسناد را بررسی کرده‌اید؟".format(item.get("name")),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.window.run_api(
            lambda: self.window.api.close_fiscal_year(item["id"]),
            self._closed,
            busy=self.close_button,
        )

    def _closed(self, result):
        checklist = result.get("checklist") or {}
        if checklist.get("warning"):
            QMessageBox.warning(self, "سال مالی بسته شد — نیاز به بررسی", checklist["warning"])
        else:
            QMessageBox.information(self, "سال مالی بسته شد", "سال مالی با موفقیت قفل شد.")
        self.refresh()

    def reopen_year(self):
        item = self._selected()
        if not item:
            self.window.show_error("یک سال مالی را انتخاب کنید.")
            return
        if item.get("status") != "closed":
            self.window.show_error("این سال مالی بسته نیست.")
            return
        reason, ok = QInputDialog.getText(self, "بازگشایی سال مالی", "دلیل دقیق بازگشایی (حداقل ۱۰ نویسه):")
        if not ok:
            return
        if len(reason.strip()) < 10:
            self.window.show_error("دلیل بازگشایی باید حداقل ۱۰ نویسه باشد.")
            return
        self.window.run_api(
            lambda: self.window.api.reopen_fiscal_year(item["id"], reason.strip()),
            lambda _r: self.refresh(),
            busy=self.reopen_button,
        )


class AccountingReportsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("گزارش‌های حسابداری")
        title.setObjectName("PageTitle")
        subtitle = QLabel("تراز آزمایشی، سود و زیان و نمای پایهٔ ترازنامه از اسناد ثبت‌شدهٔ دفتر کل.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.refresh_button = QPushButton("محاسبه مجدد")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        root.addLayout(header)
        self.metric_row = QHBoxLayout()
        self.metrics = {}
        for key, label in (
            ("income", "درآمد ثبت‌شده"), ("expenses", "هزینه ثبت‌شده"),
            ("net_profit", "سود / زیان"), ("assets", "دارایی خالص"),
        ):
            card = QFrame()
            card.setObjectName("Card")
            layout = QVBoxLayout(card)
            name = QLabel(label)
            name.setObjectName("MetricLabel")
            value = QLabel("—")
            value.setObjectName("MetricValue")
            layout.addWidget(name)
            layout.addWidget(value)
            self.metrics[key] = value
            self.metric_row.addWidget(card, 1)
        root.addLayout(self.metric_row)
        self.balance_label = QLabel("تراز آزمایشی: —")
        self.balance_label.setObjectName("StatusPill")
        root.addWidget(self.balance_label)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["کد حساب", "نام حساب", "نوع", "بدهکار", "بستانکار", "مانده (بدهکار − بستانکار)"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

    def set_permissions(self, user):
        self.refresh_button.setVisible(can_access(user, "reports", "read"))

    def refresh(self):
        if self.window.api and can_access(self.window.current_user, "reports", "read"):
            self.window.run_api(self.window.api.accounting_summary, self.populate, busy=self.refresh_button)

    def populate(self, result):
        profit = result.get("profit_and_loss") or {}
        balance_sheet = result.get("balance_sheet") or {}
        for key in ("income", "expenses", "net_profit"):
            self.metrics[key].setText(format_currency(profit.get(key)))
        self.metrics["assets"].setText(format_currency(balance_sheet.get("assets")))
        totals = result.get("trial_balance") or {}
        self.balance_label.setText(
            "تراز آزمایشی: بدهکار {} · بستانکار {} · {}".format(
                format_currency(totals.get("debit_total")),
                format_currency(totals.get("credit_total")),
                "متوازن" if totals.get("balanced") else "نامتوازن",
            )
        )
        self.table.setRowCount(0)
        for row, item in enumerate(result.get("accounts") or []):
            self.table.insertRow(row)
            values = [
                item.get("code"), item.get("name"),
                ACCOUNT_TYPE_LABELS.get(item.get("account_type"), item.get("account_type")),
                format_currency(item.get("debit")),
                format_currency(item.get("credit")),
                format_currency(item.get("net")),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))


class AuditPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.items = []
        self.page = 1
        self.page_size = 50
        self.total = 0
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("سوابق فعالیت کارکنان")
        title.setObjectName("PageTitle")
        subtitle = QLabel("ثبت‌های فروش، تغییر موجودی، مرجوعی، اسناد حسابداری و تغییر وضعیت سال مالی.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("کاربر، عملیات یا شناسه سند…")
        self.search.returnPressed.connect(self.refresh)
        self.refresh_button = QPushButton("جست‌وجو / بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.detail_button = QPushButton("جزئیات رویداد")
        self.detail_button.clicked.connect(self.show_detail)
        header.addWidget(self.search, 2)
        header.addWidget(self.refresh_button)
        header.addWidget(self.detail_button)
        root.addLayout(header)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["شناسه", "زمان", "کاربر", "عملیات", "منبع", "شناسهٔ هدف"])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda _item: self.show_detail())
        root.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.page_label = QLabel("صفحه ۱ از ۱")
        self.page_label.setObjectName("PageSubtitle")
        self.previous_button = QPushButton("صفحهٔ قبل")
        self.next_button = QPushButton("صفحهٔ بعد")
        self.previous_button.clicked.connect(lambda: self._move(-1))
        self.next_button.clicked.connect(lambda: self._move(1))
        pager.addWidget(self.page_label)
        pager.addStretch(1)
        pager.addWidget(self.previous_button)
        pager.addWidget(self.next_button)
        root.addLayout(pager)

    def set_permissions(self, user):
        self.refresh_button.setVisible(can_access(user, "audit", "read"))
        self.detail_button.setVisible(can_access(user, "audit", "read"))

    def refresh(self):
        if self.window.api and can_access(self.window.current_user, "audit", "read"):
            self.window.run_api(
                lambda: self.window.api.list_audit_events_page(
                    q=self.search.text().strip() or None, page=self.page, page_size=self.page_size
                ),
                self.populate,
                busy=self.refresh_button,
            )

    def populate(self, payload):
        self.items = list(payload.get("items") or [])
        self.page = int(payload.get("page", self.page))
        self.page_size = int(payload.get("page_size", self.page_size))
        self.total = int(payload.get("total", len(self.items)))
        self.table.setRowCount(0)
        for row, item in enumerate(self.items):
            self.table.insertRow(row)
            values = [
                item.get("id"), item.get("created_at"), item.get("actor_name"),
                item.get("action"), item.get("resource"), item.get("target_id") or "—",
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value or "—"))
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row, col, cell)
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page_label.setText("صفحه {} از {} · {} رویداد".format(self.page, pages, self.total))
        self.previous_button.setEnabled(self.page > 1)
        self.next_button.setEnabled(self.page < pages)

    def _move(self, delta):
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        if 1 <= self.page + delta <= pages:
            self.page += delta
            self.refresh()

    def show_detail(self):
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        item = cell.data(Qt.ItemDataRole.UserRole) if cell else None
        if not item:
            self.window.show_error("ابتدا یک رویداد را انتخاب کنید.")
            return
        QMessageBox.information(
            self, "جزئیات ممیزی",
            json.dumps(item.get("details") or {}, ensure_ascii=False, indent=2),
        )
