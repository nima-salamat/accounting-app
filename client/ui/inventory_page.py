"""Product-linked inventory with server paging, low-stock filters and movement history."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHeaderView, QTextEdit,
)

from client.ui.permissions import can_access


REASON_LABELS = {
    "opening": "موجودی اولیه",
    "purchase": "ورود خرید",
    "correction": "اصلاح شمارش",
    "return": "مرجوعی",
    "damage": "ضایعات",
    "sale": "فروش",
    "sale_edit_restore": "برگشت اثر ویرایش فاکتور",
    "sale_edit_issue": "مصرف موجودی در ویرایش فاکتور",
}


class StockAdjustmentDialog(QDialog):
    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle("ورود / خروج / اصلاح موجودی")
        self.setMinimumWidth(430)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        heading = QLabel("ثبت گردش موجودی")
        heading.setObjectName("PageTitle")
        subtitle = QLabel("{} · موجودی فعلی: {}".format(
            product.get("name", "—"), product.get("stock_quantity", 0)
        ))
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.delta = QDoubleSpinBox()
        self.delta.setRange(-1000000000, 1000000000)
        self.delta.setDecimals(4)
        self.delta.setSingleStep(1)
        self.delta.setValue(1)
        self.delta.setToolTip("عدد مثبت برای ورود موجودی و عدد منفی برای خروج")
        self.reason = QComboBox()
        for key in ("opening", "purchase", "correction", "return", "damage"):
            self.reason.addItem(REASON_LABELS[key], key)
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("شماره رسید خرید، دلیل اصلاح یا توضیحات تکمیلی…")
        self.notes.setFixedHeight(82)
        form.addRow("تغییر مقدار (+ / −)", self.delta)
        form.addRow("علت", self.reason)
        form.addRow("یادداشت", self.notes)
        layout.addLayout(form)
        warning = QLabel("موجودی نهایی نباید منفی شود. تغییرات همراه با کاربر و زمان در گردش انبار ثبت می‌شوند.")
        warning.setObjectName("PageSubtitle")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ثبت گردش")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("PrimaryButton")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        if abs(self.delta.value()) < 1e-9:
            QMessageBox.warning(self, "مقدار نامعتبر", "مقدار تغییر نمی‌تواند صفر باشد.")
            return
        if float(self.product.get("stock_quantity") or 0) + self.delta.value() < 0:
            QMessageBox.warning(self, "موجودی ناکافی", "این تغییر موجودی را منفی می‌کند.")
            return
        self.accept()

    def values(self):
        return {
            "quantity_change": self.delta.value(),
            "reason": self.reason.currentData(),
            "notes": self.notes.toPlainText().strip() or None,
        }


class InventoryPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.inventory = []
        self.movements = []
        self.stock_page = 1
        self.movement_page = 1
        self.page_size = 25
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("مدیریت موجودی")
        title.setObjectName("PageTitle")
        subtitle = QLabel("موجودی هر کالا، حد سفارش، هشدار کمبود و سابقهٔ ورود و خروج؛ همهٔ تغییرها در سرور ثبت می‌شوند.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles, 1)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button)
        root.addLayout(heading)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        stock_tab = QFrame()
        stock_layout = QVBoxLayout(stock_tab)
        stock_layout.setContentsMargins(8, 10, 8, 8)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("جست‌وجوی نام کالا…")
        self.search.returnPressed.connect(self.search_inventory)
        self.low_stock = QCheckBox("فقط کالاهای زیر حد سفارش")
        self.search_button = QPushButton("جست‌وجو")
        self.search_button.clicked.connect(self.search_inventory)
        self.adjust_button = QPushButton("ورود / خروج موجودی")
        self.adjust_button.setObjectName("PrimaryButton")
        self.adjust_button.clicked.connect(self.adjust_stock)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.low_stock)
        filters.addWidget(self.search_button)
        filters.addWidget(self.adjust_button)
        stock_layout.addLayout(filters)
        self.stock_table = QTableWidget(0, 6)
        self.stock_table.setHorizontalHeaderLabels(
            ["شناسه", "کالا", "رهگیری", "موجودی فعلی", "حد سفارش", "قیمت فروش"]
        )
        self.stock_table.setColumnHidden(0, True)
        self._configure_table(self.stock_table)
        stock_layout.addWidget(self.stock_table, 1)
        self.stock_pager = self._create_pager(stock_layout, "stock")
        self.tabs.addTab(stock_tab, "موجودی کالا")

        movement_tab = QFrame()
        movement_layout = QVBoxLayout(movement_tab)
        movement_layout.setContentsMargins(8, 10, 8, 8)
        note = QLabel("گردش‌ها شامل ورود/خروج دستی و مصرف خودکار هنگام فروش هستند؛ سوابق برای حسابرسی نگهداری می‌شوند.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        movement_layout.addWidget(note)
        self.movement_table = QTableWidget(0, 7)
        self.movement_table.setHorizontalHeaderLabels(
            ["شناسه", "تاریخ", "کالا", "تغییر", "موجودی قبل", "موجودی بعد", "علت / کاربر"]
        )
        self.movement_table.setColumnHidden(0, True)
        self._configure_table(self.movement_table)
        movement_layout.addWidget(self.movement_table, 1)
        self.movement_pager = self._create_pager(movement_layout, "movement")
        self.tabs.addTab(movement_tab, "گردش موجودی")

    @staticmethod
    def _configure_table(table):
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _create_pager(self, layout, kind):
        bar = QHBoxLayout()
        bar.addWidget(QLabel("تعداد در صفحه"))
        size_combo = QComboBox()
        for size in (25, 50, 100):
            size_combo.addItem(str(size), size)
        size_combo.currentIndexChanged.connect(lambda _i: self._set_page_size(size_combo))
        label = QLabel("صفحه ۱ از ۱")
        label.setObjectName("PageSubtitle")
        previous = QPushButton("صفحهٔ قبل")
        next_button = QPushButton("صفحهٔ بعد")
        previous.clicked.connect(lambda: self._move_page(kind, -1))
        next_button.clicked.connect(lambda: self._move_page(kind, 1))
        bar.addWidget(size_combo)
        bar.addWidget(label)
        bar.addStretch(1)
        bar.addWidget(previous)
        bar.addWidget(next_button)
        layout.addLayout(bar)
        if kind == "stock":
            self.stock_page_label, self.stock_previous, self.stock_next = label, previous, next_button
        else:
            self.movement_page_label, self.movement_previous, self.movement_next = label, previous, next_button
        return bar

    def set_permissions(self, user):
        self.adjust_button.setVisible(can_access(user, "warehouse", "create"))
        self.refresh_button.setVisible(can_access(user, "warehouse", "read"))

    def refresh(self):
        if not self.window.api:
            return
        self.window.run_api(
            lambda: self.window.api.list_inventory(
                q=self.search.text().strip() or None,
                low_stock_only=self.low_stock.isChecked(),
                page=self.stock_page, page_size=self.page_size,
            ),
            self._populate_inventory,
            busy=self.refresh_button,
        )
        self.window.run_api(
            lambda: self.window.api.list_stock_movements(
                page=self.movement_page, page_size=self.page_size
            ),
            self._populate_movements,
        )

    def search_inventory(self):
        self.stock_page = 1
        self.refresh()

    def _populate_inventory(self, records):
        self.inventory = list(records or [])
        self.stock_table.setRowCount(0)
        for row, record in enumerate(self.inventory):
            self.stock_table.insertRow(row)
            stock = float(record.get("stock_quantity") or 0)
            threshold = float(record.get("reorder_level") or 0)
            values = [
                record.get("id"), record.get("name", "—"),
                "فعال" if record.get("track_stock") else "خاموش",
                "{:,.4f}".format(stock).rstrip("0").rstrip("."),
                "{:,.4f}".format(threshold).rstrip("0").rstrip("."),
                "{:,.2f}".format(float(record.get("sell_price") or 0)),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record)
                self.stock_table.setItem(row, col, item)
            if record.get("track_stock") and stock <= threshold:
                for col in range(1, self.stock_table.columnCount()):
                    cell = self.stock_table.item(row, col)
                    if cell:
                        cell.setToolTip("موجودی به حد سفارش رسیده یا از آن کمتر است.")
        pages = max(1, (len(self.inventory) + self.page_size - 1) // self.page_size)
        self.stock_page_label.setText("صفحه {} از {} · {} کالا".format(self.stock_page, pages, len(self.inventory)))
        self.stock_previous.setEnabled(self.stock_page > 1)
        self.stock_next.setEnabled(len(self.inventory) >= self.page_size)

    def _populate_movements(self, records):
        self.movements = list(records or [])
        self.movement_table.setRowCount(0)
        for row, item in enumerate(self.movements):
            self.movement_table.insertRow(row)
            delta = float(item.get("quantity_change") or 0)
            reason = REASON_LABELS.get(item.get("reason"), item.get("reason", "—"))
            label = "{} · {}".format(reason, item.get("username", "—"))
            values = [
                item.get("id"), item.get("created_at", "—"),
                item.get("product_name", "—"), "{:+,.4f}".format(delta).rstrip("0").rstrip("."),
                "{:,.4f}".format(float(item.get("stock_before") or 0)).rstrip("0").rstrip("."),
                "{:,.4f}".format(float(item.get("stock_after") or 0)).rstrip("0").rstrip("."),
                label,
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item)
                self.movement_table.setItem(row, col, cell)
        self.movement_page_label.setText("صفحه {} · {} گردش".format(self.movement_page, len(self.movements)))
        self.movement_previous.setEnabled(self.movement_page > 1)
        self.movement_next.setEnabled(len(self.movements) >= self.page_size)

    def _set_page_size(self, combo):
        self.page_size = int(combo.currentData() or 25)
        self.stock_page = self.movement_page = 1
        self.refresh()

    def _move_page(self, kind, direction):
        if kind == "stock":
            self.stock_page = max(1, self.stock_page + direction)
        else:
            self.movement_page = max(1, self.movement_page + direction)
        self.refresh()

    def _selected_product(self):
        row = self.stock_table.currentRow()
        item = self.stock_table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def adjust_stock(self):
        product = self._selected_product()
        if not product:
            self.window.show_error("ابتدا یک کالا را از جدول موجودی انتخاب کنید.")
            return
        if not product.get("track_stock"):
            QMessageBox.warning(
                self, "رهگیری موجودی خاموش",
                "ابتدا در بخش «محصولات» گزینهٔ رهگیری موجودی را برای این کالا فعال کنید.",
            )
            return
        dialog = StockAdjustmentDialog(product, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.window.run_api(
            lambda: self.window.api.adjust_inventory(
                product["id"], values["quantity_change"],
                reason=values["reason"], notes=values["notes"],
            ),
            self._adjusted,
            busy=self.adjust_button,
        )

    def _adjusted(self, movement):
        self.window.set_status(
            "موجودی «{}» به {} تغییر کرد.".format(
                movement.get("product_name", "کالا"), movement.get("stock_after", "—")
            )
        )
        self.refresh()
