"""Global search dialog that dispatches queries only to authorized API resources."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView,
)

from client.ui.permissions import can_access
from client.ui.currency import format_currency


class GlobalSearchDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.results = []
        self.query_text = ""
        self.setWindowTitle("جست‌وجوی سریع")
        self.resize(900, 560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        title = QLabel("جست‌وجوی سراسری")
        title.setObjectName("PageTitle")
        subtitle = QLabel("کالا، دسته‌بندی، انبار، چک و سند حسابداری را از یک نقطه پیدا کنید. میانبر: Ctrl+K")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("حداقل دو نویسه وارد کنید…")
        self.query.setMinimumHeight(42)
        self.query.returnPressed.connect(self.search)
        self.search_button = QPushButton("جست‌وجو")
        self.search_button.setObjectName("PrimaryButton")
        self.search_button.clicked.connect(self.search)
        row.addWidget(self.query, 1)
        row.addWidget(self.search_button)
        root.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["نوع", "عنوان", "جزئیات", "شناسه"])
        self.table.setColumnHidden(3, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda _item: self.open_selected())
        root.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.status = QLabel("برای جست‌وجو حداقل دو نویسه وارد کنید.")
        self.status.setObjectName("PageSubtitle")
        footer.addWidget(self.status, 1)
        self.open_button = QPushButton("باز کردن بخش")
        self.open_button.clicked.connect(self.open_selected)
        close_button = QPushButton("بستن")
        close_button.clicked.connect(self.reject)
        footer.addWidget(self.open_button)
        footer.addWidget(close_button)
        root.addLayout(footer)
        self.query.setFocus()

    def _search(self):
        query = self.query.text().strip()
        if len(query) < 2:
            return {"query": query, "results": []}
        api = self.window.api
        user = self.window.current_user
        results = []

        def add(kind, title, description, page, record_id=None):
            results.append({
                "kind": kind,
                "title": str(title or "—"),
                "description": str(description or ""),
                "page": page,
                "id": str(record_id or ""),
            })

        if can_access(user, "products", "read"):
            page = api.list_products_page(q=query, page=1, page_size=12)
            for item in page.get("items", []):
                add("کالا", item.get("name"), "فروش {}".format(format_currency(item.get("sell_price"))), "products", item.get("id"))
        if can_access(user, "categories", "read"):
            page = api.list_categories_page(q=query, page=1, page_size=8)
            for item in page.get("items", []):
                add("دسته‌بندی", item.get("name"), "گروه کالا", "categories", item.get("id"))
        if can_access(user, "warehouse", "read"):
            page = api.list_warehouses_page(q=query, page=1, page_size=8)
            for item in page.get("items", []):
                add("انبار", item.get("name"), "مقدار {}".format(item.get("amount", "—")), "warehouse", item.get("id"))
        if can_access(user, "checks_in", "read"):
            page = api.list_checks_page("in", q=query, page=1, page_size=6)
            for item in page.get("items", []):
                add("چک دریافتی", item.get("check_id"), item.get("name"), "checks_in", item.get("id"))
        if can_access(user, "checks_out", "read"):
            page = api.list_checks_page("out", q=query, page=1, page_size=6)
            for item in page.get("items", []):
                add("چک پرداختی", item.get("check_id"), item.get("name"), "checks_out", item.get("id"))
        if can_access(user, "journals", "read"):
            page = api.list_journals_page(q=query, page=1, page_size=8)
            for item in page.get("items", []):
                add("سند حسابداری", item.get("entry_number"), item.get("description"), "accounting", item.get("id"))
        if can_access(user, "receipts", "read"):
            page = api.list_receipts_page(page=1, page_size=50)
            for item in page.get("items", []):
                receipt_id = str(item.get("id", ""))
                day_id = str(item.get("day_receipt_id", ""))
                if query.lower() in receipt_id.lower() or query in day_id:
                    add(
                        "فاکتور",
                        "رسید روزانهٔ {}".format(day_id),
                        "مبلغ {}".format(format_currency(item.get("total_price"))),
                        "receipts",
                        receipt_id,
                    )
        return {"query": query, "results": results}

    def search(self):
        self.query_text = self.query.text().strip()
        if len(self.query_text) < 2:
            self.status.setText("عبارت جست‌وجو باید حداقل دو نویسه داشته باشد.")
            return
        self.window.run_api(self._search, self.populate, busy=self.search_button)

    def populate(self, payload):
        self.results = list(payload.get("results") or [])
        self.table.setRowCount(0)
        for row, item in enumerate(self.results):
            self.table.insertRow(row)
            values = [item["kind"], item["title"], item["description"], item["id"]]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value or "—"))
                if col == 3:
                    cell.setData(Qt.ItemDataRole.UserRole, item)
                self.table.setItem(row, col, cell)
        self.status.setText("{} نتیجه برای «{}»".format(len(self.results), payload.get("query", "")))

    def open_selected(self):
        row = self.table.currentRow()
        cell = self.table.item(row, 3) if row >= 0 else None
        item = cell.data(Qt.ItemDataRole.UserRole) if cell else None
        if not item:
            QMessageBox.information(self, "انتخاب نتیجه", "ابتدا یک نتیجه را انتخاب کنید.")
            return
        self.window.navigate(item["page"])
        page = self.window._pages.get(item["page"])
        query_input = getattr(page, "search_input", None) or getattr(page, "search", None)
        if isinstance(query_input, QLineEdit) and item["page"] not in ("accounting", "receipts"):
            query_input.setText(self.query_text)
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
        self.accept()
