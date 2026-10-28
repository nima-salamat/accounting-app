"""Physical inventory count workflow: prepare, count, review variance, then apply once."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView, QTextEdit,
)

from client.ui.permissions import can_access


class NewStocktakeDialog(QDialog):
    def __init__(self, products, parent=None):
        super().__init__(parent)
        self.products = list(products or [])
        self.setWindowTitle("شروع شمارش فیزیکی موجودی")
        self.resize(780, 620)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        title = QLabel("برگهٔ جدید شمارش انبار")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "فقط کالاهایی که رهگیری موجودی آن‌ها فعال است قابل انتخاب‌اند. "
            "ساخت برگه، موجودی را تغییر نمی‌دهد؛ تغییر فقط پس از بازبینی و «اعمال شمارش» انجام می‌شود."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("مثلاً شمارش انبار اصلی — اکتبر")
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("یادداشت یا محدودهٔ شمارش (اختیاری)")
        self.notes.setFixedHeight(60)
        form.addRow("عنوان شمارش", self.name)
        form.addRow("یادداشت", self.notes)
        root.addLayout(form)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["انتخاب", "کالا", "موجودی سیستمی", "حد سفارش"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)
        self.checks = []
        for row, product in enumerate(self.products):
            if not product.get("track_stock"):
                continue
            self.table.insertRow(self.table.rowCount())
            actual_row = self.table.rowCount() - 1
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox.setToolTip("این کالا در برگهٔ شمارش قرار می‌گیرد.")
            self.checks.append((product, checkbox))
            self.table.setCellWidget(actual_row, 0, checkbox)
            values = [
                product.get("name", "—"),
                "{:,.4f}".format(float(product.get("stock_quantity") or 0)).rstrip("0").rstrip("."),
                "{:,.4f}".format(float(product.get("reorder_level") or 0)).rstrip("0").rstrip("."),
            ]
            for col, value in enumerate(values, 1):
                self.table.setItem(actual_row, col, QTableWidgetItem(str(value)))
        footer = QHBoxLayout()
        self.select_all = QCheckBox("انتخاب همهٔ کالاهای رهگیری‌شده")
        self.select_all.setChecked(True)
        self.select_all.toggled.connect(self._toggle_all)
        footer.addWidget(self.select_all)
        footer.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ساخت برگهٔ پیش‌نویس")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        root.addLayout(footer)

    def _toggle_all(self, checked):
        for _product, checkbox in self.checks:
            checkbox.setChecked(checked)

    def _validate(self):
        if len(self.name.text().strip()) < 2:
            QMessageBox.warning(self, "عنوان الزامی", "عنوان شمارش را وارد کنید.")
            return
        if not self.selected_product_ids():
            QMessageBox.warning(self, "کالایی انتخاب نشده", "حداقل یک کالای رهگیری‌شده انتخاب کنید.")
            return
        self.accept()

    def selected_product_ids(self):
        return [product["id"] for product, checkbox in self.checks if checkbox.isChecked()]

    def values(self):
        return {
            "name": self.name.text().strip(),
            "notes": self.notes.toPlainText().strip() or None,
            "product_ids": self.selected_product_ids(),
        }


class StocktakeCountDialog(QDialog):
    def __init__(self, stocktake, parent=None):
        super().__init__(parent)
        self.stocktake = stocktake
        self.setWindowTitle("شمارش فیزیکی · {}".format(stocktake.get("name", "")))
        self.resize(880, 620)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        title = QLabel(stocktake.get("name", "شمارش موجودی"))
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "موجودی فیزیکی را وارد کنید. اختلاف‌ها در جدول نشان داده می‌شوند؛ "
            "تا زمان اعمال برگه، موجودی کالا تغییر نمی‌کند."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["کالا", "موجودی زمان شروع", "شمارش فیزیکی", "اختلاف", "شناسه"])
        self.table.setColumnHidden(4, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)
        self.inputs = []
        for row, item in enumerate(stocktake.get("lines") or []):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(item.get("product_name", "—"))))
            self.table.setItem(row, 1, QTableWidgetItem(
                "{:,.4f}".format(float(item.get("expected_quantity") or 0)).rstrip("0").rstrip(".")
            ))
            spinner = QDoubleSpinBox()
            spinner.setRange(0, 999999999999.9999)
            spinner.setDecimals(4)
            spinner.setSingleStep(1)
            spinner.setMinimumHeight(38)
            spinner.setValue(float(item.get("counted_quantity") or 0))
            spinner.valueChanged.connect(lambda _value, index=row: self._update_difference(index))
            self.table.setCellWidget(row, 2, spinner)
            diff = QLabel("—")
            diff.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 3, diff)
            self.table.setItem(row, 4, QTableWidgetItem(str(item.get("id"))))
            self.inputs.append((item, spinner, diff))
            self._update_difference(row)

        self.note = QLabel(
            "هنگام اعمال، هر اختلاف موجودی به گردش مستقل با نام شمارش و کارمند ثبت می‌شود. "
            "پس از اعمال، برگه قفل می‌شود و دوباره قابل اعمال نیست."
        )
        self.note.setObjectName("StatusPill")
        self.note.setWordWrap(True)
        root.addWidget(self.note)
        footer = QHBoxLayout()
        self.save_button = QPushButton("ذخیره شمارش")
        self.save_button.clicked.connect(self._save)
        self.apply_button = QPushButton("اعمال شمارش نهایی")
        self.apply_button.setObjectName("PrimaryButton")
        self.apply_button.clicked.connect(self._apply)
        close_button = QPushButton("بستن")
        close_button.clicked.connect(self.reject)
        footer.addWidget(self.save_button)
        footer.addWidget(self.apply_button)
        footer.addStretch(1)
        footer.addWidget(close_button)
        root.addLayout(footer)
        if stocktake.get("status") != "draft":
            for _item, spinner, _label in self.inputs:
                spinner.setEnabled(False)
            self.save_button.setEnabled(False)
            self.apply_button.setEnabled(False)

    def _update_difference(self, index):
        if index >= len(self.inputs):
            return
        item, spinner, label = self.inputs[index]
        expected = float(item.get("expected_quantity") or 0)
        difference = round(spinner.value() - expected, 4)
        label.setText("{:+,.4f}".format(difference).rstrip("0").rstrip("."))
        label.setStyleSheet("color:#17846D;" if abs(difference) < 1e-9 else "color:#C74455;font-weight:800;")

    def values(self):
        return [
            {"line_id": item["id"], "counted_quantity": spinner.value()}
            for item, spinner, _label in self.inputs
        ]

    def _save(self):
        self.done(QDialog.DialogCode.Accepted)

    def _apply(self):
        answer = QMessageBox.question(
            self, "اعمال شمارش موجودی",
            "تأیید می‌کنید موجودی سیستم برای همهٔ ردیف‌های این برگه به مقدار شمارش‌شده تغییر کند؟ این عمل قابل برگشت مستقیم نیست.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.done(2)


class StocktakesPage(QFrame):
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
        root.setSpacing(14)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("شمارش فیزیکی / انبارگردانی")
        title.setObjectName("PageTitle")
        subtitle = QLabel("برگهٔ پیش‌نویس، ثبت تعداد واقعی، بررسی اختلاف و اعمال یک‌باره به موجودی.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        self.create_button = QPushButton("شروع انبارگردانی +")
        self.create_button.setObjectName("PrimaryButton")
        self.create_button.clicked.connect(self.create_stocktake)
        self.count_button = QPushButton("ادامهٔ شمارش")
        self.count_button.clicked.connect(self.open_stocktake)
        header.addWidget(self.refresh_button)
        header.addWidget(self.create_button)
        header.addWidget(self.count_button)
        root.addLayout(header)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["شناسه", "عنوان", "وضعیت", "ایجادکننده", "تاریخ"])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda _item: self.open_stocktake())
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
        self.refresh_button.setVisible(can_access(user, "warehouse", "read"))
        self.count_button.setVisible(can_access(user, "warehouse", "read"))
        self.create_button.setVisible(can_access(user, "warehouse", "create"))

    def refresh(self):
        if self.window.api and can_access(self.window.current_user, "warehouse", "read"):
            self.window.run_api(
                lambda: self.window.api.list_stocktakes_page(page=self.page, page_size=self.page_size),
                self.populate, busy=self.refresh_button,
            )

    def populate(self, payload):
        self.items = list(payload.get("items") or [])
        self.page = int(payload.get("page", self.page))
        self.page_size = int(payload.get("page_size", self.page_size))
        self.total = int(payload.get("total", len(self.items)))
        self.table.setRowCount(0)
        for row, item in enumerate(self.items):
            self.table.insertRow(row)
            status = {"draft": "پیش‌نویس", "applied": "اعمال‌شده", "cancelled": "لغوشده"}.get(item.get("status"), item.get("status"))
            values = [item.get("id"), item.get("name"), status, item.get("created_by_name"), item.get("created_at")]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value or "—"))
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row, col, cell)
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page_label.setText("صفحه {} از {} · {} برگه".format(self.page, pages, self.total))
        self.previous_button.setEnabled(self.page > 1)
        self.next_button.setEnabled(self.page < pages)

    def _selected(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _move(self, delta):
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        if 1 <= self.page + delta <= pages:
            self.page += delta
            self.refresh()

    def create_stocktake(self):
        self.window.run_api(self._load_products, self._open_create_dialog)

    def _load_products(self):
        products, page = [], 1
        while True:
            data = self.window.api.list_inventory(page=page, page_size=200)
            batch = list(data.get("items") or [])
            products.extend(batch)
            if not batch or len(products) >= int(data.get("total", len(products))):
                break
            page += 1
        return [item for item in products if item.get("track_stock")]

    def _open_create_dialog(self, products):
        dialog = NewStocktakeDialog(products, self)
        if dialog.exec() != NewStocktakeDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.window.run_api(
            lambda: self.window.api.create_stocktake(
                values["name"], values["product_ids"], notes=values["notes"]
            ),
            lambda _result: self.refresh(),
            busy=self.create_button,
        )

    def open_stocktake(self):
        item = self._selected()
        if not item:
            self.window.show_error("ابتدا یک برگهٔ انبارگردانی را انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_stocktake(item["id"]),
            self._open_count_dialog,
        )

    def _open_count_dialog(self, stocktake):
        dialog = StocktakeCountDialog(stocktake, self)
        result = dialog.exec()
        if result not in (QDialog.DialogCode.Accepted, 2):
            return
        counts = dialog.values()
        apply_now = result == 2
        self.window.run_api(
            lambda: self._save_and_maybe_apply(stocktake["id"], counts, apply_now),
            self._count_saved,
            busy=self.count_button,
        )

    def _save_and_maybe_apply(self, stocktake_id, counts, apply_now):
        for line in counts:
            self.window.api.update_stocktake_count(
                stocktake_id, line["line_id"], line["counted_quantity"]
            )
        if apply_now:
            return self.window.api.apply_stocktake(stocktake_id)
        return self.window.api.get_stocktake(stocktake_id)

    def _count_saved(self, stocktake):
        self.window.set_status(
            "شمارش موجودی ذخیره شد." if stocktake.get("status") == "draft" else "انبارگردانی اعمال و موجودی به‌روزرسانی شد."
        )
        self.refresh()
