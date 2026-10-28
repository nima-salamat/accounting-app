"""API-only resource pages for products, categories, checks, inventory, users, and receipts."""
import csv
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView, QLineEdit, QComboBox,
)
from client.ui.forms import RecordDialog
from client.ui.permissions import can_access
from client.ui.invoice_dialog import InvoiceDialog


def display_value(key, value):
    if key in ("payed", "is_admin", "is_active", "requires_session_activation", "custom_product", "track_stock"):
        return ("فعال" if value else "غیرفعال") if key == "is_active" else ("بله" if value else "خیر")
    if key == "status":
        return {"pending": "در انتظار تأیید", "active": "فعال",
                "revoked": "لغوشده", "expired": "منقضی"}.get(value, value or "—")
    if key in ("buy_price", "sell_price", "price", "amount", "total_price", "revenue"):
        try:
            return "{:,.2f}".format(float(value or 0)).rstrip("0").rstrip(".")
        except (ValueError, TypeError):
            pass
    return "—" if value is None or value == "" else str(value)


class ApiTablePage(QFrame):
    """Reusable record table. Data access always crosses AccountingApiClient."""
    def __init__(self, window, title, subtitle, columns, load_fn, fields=(),
                 create_fn=None, update_fn=None, delete_fn=None, searchable=True):
        super().__init__()
        self.window, self.title, self.columns = window, title, columns
        self.load_fn, self.fields = load_fn, list(fields)
        self.create_fn, self.update_fn, self.delete_fn = create_fn, update_fn, delete_fn
        self.searchable = searchable
        self.records = []
        self.current_page = 1
        self.page_size = 25
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        texts = QVBoxLayout()
        h = QLabel(title); h.setObjectName("PageTitle")
        sub = QLabel(subtitle); sub.setObjectName("PageSubtitle"); sub.setWordWrap(True)
        texts.addWidget(h); texts.addWidget(sub)
        header.addLayout(texts, 1)
        self.count_label = QLabel("—"); self.count_label.setObjectName("StatusPill")
        header.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        tools = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جست‌وجو...")
        self.search_input.returnPressed.connect(self.refresh)
        self.search_button = QPushButton("جست‌وجو"); self.search_button.clicked.connect(self.refresh)
        self.refresh_button = QPushButton("↻ بازخوانی"); self.refresh_button.clicked.connect(self.refresh)
        self.create_button = QPushButton("＋ افزودن"); self.create_button.setObjectName("PrimaryButton")
        self.create_button.clicked.connect(self.create_record)
        self.edit_button = QPushButton("ویرایش"); self.edit_button.clicked.connect(self.edit_record)
        self.delete_button = QPushButton("حذف"); self.delete_button.setObjectName("DangerButton")
        self.delete_button.clicked.connect(self.delete_record)
        self.export_button = QPushButton("خروجی CSV"); self.export_button.clicked.connect(self.export_csv)
        if searchable:
            tools.addWidget(self.search_input, 1); tools.addWidget(self.search_button)
        tools.addWidget(self.refresh_button); tools.addWidget(self.create_button)
        tools.addWidget(self.edit_button); tools.addWidget(self.delete_button); tools.addWidget(self.export_button)
        layout.addLayout(tools)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([label for _key, label in columns])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda _item: self.edit_record())
        layout.addWidget(self.table, 1)
        pager = QHBoxLayout()
        pager.addWidget(QLabel("تعداد در صفحه"))
        self.page_size_combo = QComboBox()
        for size in (25, 50, 100):
            self.page_size_combo.addItem(str(size), size)
        self.page_size_combo.currentIndexChanged.connect(self._page_size_changed)
        pager.addWidget(self.page_size_combo)
        self.page_label = QLabel("صفحه ۱ از ۱")
        self.page_label.setObjectName("PageSubtitle")
        pager.addWidget(self.page_label)
        pager.addStretch(1)
        self.previous_page_button = QPushButton("صفحهٔ قبل")
        self.next_page_button = QPushButton("صفحهٔ بعد")
        self.previous_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        pager.addWidget(self.previous_page_button)
        pager.addWidget(self.next_page_button)
        layout.addLayout(pager)
        self.set_admin(False)

    def set_admin(self, is_admin):
        self.create_button.setVisible(bool(is_admin) and self.create_fn is not None)
        self.edit_button.setVisible(bool(is_admin) and self.update_fn is not None)
        self.delete_button.setVisible(bool(is_admin) and self.delete_fn is not None)

    def set_permissions(self, user, resource):
        self.create_button.setVisible(can_access(user, resource, "create") and self.create_fn is not None)
        self.edit_button.setVisible(can_access(user, resource, "update") and self.update_fn is not None)
        self.delete_button.setVisible(can_access(user, resource, "delete") and self.delete_fn is not None)

    def refresh(self):
        if not self.window.api:
            return
        self.current_page = 1
        query = self.search_input.text().strip() if self.searchable else ""
        self.window.run_api(lambda: self.load_fn(self.window.api, query), self.populate, busy=self.refresh_button)

    def populate(self, records):
        self.records = list(records or [])
        self.current_page = 1
        self._render_page()

    def _render_page(self):
        total = len(self.records)
        pages = max(1, (total + self.page_size - 1) // self.page_size)
        self.current_page = max(1, min(self.current_page, pages))
        start = (self.current_page - 1) * self.page_size
        visible = self.records[start:start + self.page_size]
        self.table.setRowCount(0)
        for row, record in enumerate(visible):
            self.table.insertRow(row)
            for col, (key, _label) in enumerate(self.columns):
                item = QTableWidgetItem(display_value(key, record.get(key)))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record)
                self.table.setItem(row, col, item)
        if total:
            end = min(start + len(visible), total)
            self.count_label.setText("{} رکورد · {} تا {}".format(total, start + 1, end))
        else:
            self.count_label.setText("بدون رکورد")
        self.page_label.setText("صفحه {} از {}".format(self.current_page, pages))
        self.previous_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < pages)

    def _page_size_changed(self, *_args):
        if hasattr(self, "page_size_combo"):
            self.page_size = int(self.page_size_combo.currentData() or 25)
            self.current_page = 1
            self._render_page()

    def previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_page()

    def next_page(self):
        pages = max(1, (len(self.records) + self.page_size - 1) // self.page_size)
        if self.current_page < pages:
            self.current_page += 1
            self._render_page()

    def selected_record(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def create_record(self):
        if not self.create_fn:
            return
        dialog = RecordDialog("افزودن " + self.title, self.fields, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            payload = dialog.values()
        except ValueError as exc:
            self.window.show_error(exc); return
        self.window.run_api(
            lambda: self.create_fn(self.window.api, payload),
            lambda _result: self._mutation_done(self.title + " ساخته شد."),
            busy=self.create_button,
        )

    def edit_record(self):
        if not self.update_fn:
            return
        record = self.selected_record()
        if not record:
            self.window.show_error("ابتدا یک رکورد را انتخاب کنید."); return
        dialog = RecordDialog("ویرایش " + self.title, self.fields, record, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            payload = dialog.values()
        except ValueError as exc:
            self.window.show_error(exc); return
        self.window.run_api(
            lambda: self.update_fn(self.window.api, record["id"], payload),
            lambda _result: self._mutation_done(self.title + " به‌روزرسانی شد."),
            busy=self.edit_button,
        )

    def delete_record(self):
        if not self.delete_fn:
            return
        record = self.selected_record()
        if not record:
            self.window.show_error("ابتدا یک رکورد را انتخاب کنید."); return
        label = record.get("name") or record.get("username") or record.get("check_id") or record.get("id")
        answer = QMessageBox.question(
            self, "تأیید حذف", "«{}» حذف شود؟ این عملیات قابل بازگشت نیست.".format(label),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.window.run_api(
            lambda: self.delete_fn(self.window.api, record["id"]),
            lambda _result: self._mutation_done(self.title + " حذف شد."),
            busy=self.delete_button,
        )

    def _mutation_done(self, message):
        self.window.set_status(message)
        self.refresh()
        self.window.refresh_dashboard_data()

    def export_csv(self):
        if not self.records:
            self.window.show_error("داده‌ای برای خروجی وجود ندارد."); return
        path, _ = QFileDialog.getSaveFileName(self, "ذخیرهٔ CSV", "export.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.DictWriter(stream, fieldnames=[key for key, _ in self.columns], extrasaction="ignore")
                writer.writeheader(); writer.writerows(self.records)
        except OSError as exc:
            self.window.show_error(exc); return
        self.window.set_status("خروجی ذخیره شد: " + path)


class ProductsPage(ApiTablePage):
    def __init__(self, window):
        fields = [
            {"key": "name", "label": "نام محصول", "required": True},
            {"key": "buy_price", "label": "قیمت خرید", "kind": "number", "required": True},
            {"key": "sell_price", "label": "قیمت فروش", "kind": "number", "required": True},
            {"key": "category_id", "label": "شناسهٔ دسته‌بندی (اختیاری)", "nullable": True},
            {"key": "custom_product", "label": "محصول سفارشی", "kind": "bool"},
            {"key": "track_stock", "label": "رهگیری موجودی", "kind": "bool"},
            {"key": "reorder_level", "label": "حد سفارش", "kind": "number", "default": 0, "required": True},
            {"key": "image_path", "label": "مسیر تصویر در سرور", "nullable": True},
        ]
        super().__init__(window, "محصولات", "نام، قیمت‌ها و دسته‌بندی کالاها.",
            [("id","شناسه"),("name","نام محصول"),("buy_price","قیمت خرید"),
             ("sell_price","قیمت فروش"),("track_stock","رهگیری"),("stock_quantity","موجودی"),
             ("reorder_level","حد سفارش"),("category_id","دسته‌بندی")],
            lambda api,q: api.list_products(q=q or None,page_size=200), fields,
            lambda api,p: api.create_product(**p),
            lambda api,rid,p: api.update_product(rid,**p),
            lambda api,rid: api.delete_product(rid))


class CategoriesPage(ApiTablePage):
    def __init__(self, window):
        super().__init__(window, "دسته‌بندی‌ها", "گروه‌بندی کالاها برای یافتن و تحلیل بهتر.",
            [("id","شناسه"),("name","نام دسته‌بندی")],
            lambda api,q: api.list_categories(q=q or None,page_size=200),
            [{"key":"name","label":"نام دسته‌بندی","required":True}],
            lambda api,p: api.create_category(**p),
            lambda api,rid,p: api.update_category(rid,**p),
            lambda api,rid: api.delete_category(rid))


class WarehousePage(ApiTablePage):
    def __init__(self, window):
        fields = [
            {"key":"name","label":"نام","required":True},
            {"key":"price","label":"قیمت واحد","kind":"number","required":True},
            {"key":"amount","label":"مقدار","kind":"number","required":True},
            {"key":"unit","label":"واحد","kind":"select","required":True,"choices":[
                ("عدد","pcs"),("کیلوگرم","kg"),("متر","m"),("لیتر","l")]},
        ]
        super().__init__(window,"انبار","مقدار و ارزش اقلام انبار.",
            [("id","شناسه"),("name","نام"),("price","قیمت"),("amount","مقدار"),("unit","واحد")],
            lambda api,_q: api.list_warehouses(), fields,
            lambda api,p: api.create_warehouse(**p),
            lambda api,rid,p: api.update_warehouse(rid,**p),
            lambda api,rid: api.delete_warehouse(rid), searchable=False)


class ChecksPage(ApiTablePage):
    def __init__(self, window, direction="in"):
        self.direction = direction
        title = "چک‌های دریافتی" if direction == "in" else "چک‌های پرداختی"
        fields = [
            {"key":"name","label":"طرف حساب","required":True},
            {"key":"check_id","label":"شماره چک","required":True},
            {"key":"price","label":"مبلغ","kind":"number","required":True},
            {"key":"date","label":"تاریخ","required":True},
            {"key":"payed","label":"پرداخت‌شده","kind":"bool"},
        ]
        super().__init__(window,title,"اطلاعات و وضعیت چک‌ها.",
            [("id","شناسه"),("name","طرف حساب"),("check_id","شماره چک"),
             ("price","مبلغ"),("date","تاریخ"),("payed","پرداخت")],
            lambda api,q: api.list_checks(direction,q=q or None,page_size=200), fields,
            lambda api,p: api.create_check(direction,**p),
            lambda api,rid,p: api.update_check(direction,rid,**p),
            lambda api,rid: api.delete_check(direction,rid))


class UsersPage(ApiTablePage):
    def __init__(self, window):
        fields = [
            {"key":"username","label":"نام کاربری","required":True},
            {"key":"password","label":"رمز عبور","kind":"password","required":True,
             "placeholder":"برای ویرایش، خالی بماند"},
            {"key":"is_admin","label":"مدیر سیستم","kind":"bool"},
            {"key":"is_active","label":"حساب فعال","kind":"bool","default":True},
            {"key":"requires_session_activation","label":"تأیید مدیر برای ورود هر دستگاه","kind":"bool","default":True},
            {"key":"buttons","label":"مجوزهای پنل","nullable":True},
        ]
        super().__init__(window,"کاربران و دسترسی‌ها",
            "حساب‌ها را فعال یا غیرفعال کنید و تعیین کنید نشست دستگاه‌های جدید به تأیید مدیر نیاز دارند یا خیر.",
            [("id","شناسه"),("username","نام کاربری"),("is_admin","مدیر"),
             ("is_active","حساب فعال"),("requires_session_activation","تأیید دستگاه"),("buttons","مجوزها")],
            lambda api,_q: api.list_users(), fields,
            lambda api,p: api.create_user(**p),
            lambda api,rid,p: api.update_user(rid,**p),
            lambda api,rid: api.delete_user(rid), searchable=False)


class ReceiptsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window, self.records = window, []
        self.current_page, self.page_size = 1, 25
        self.setObjectName("Card")
        layout = QVBoxLayout(self); layout.setContentsMargins(18,18,18,18); layout.setSpacing(12)
        header = QHBoxLayout(); text = QVBoxLayout()
        h = QLabel("رسیدها"); h.setObjectName("PageTitle")
        sub = QLabel("جزئیات و عملیات حذف در سرور با توجه به مالکیت و سطح دسترسی کنترل می‌شوند.")
        sub.setObjectName("PageSubtitle"); sub.setWordWrap(True)
        text.addWidget(h); text.addWidget(sub); header.addLayout(text,1)
        self.refresh_button = QPushButton("↻ بازخوانی"); self.refresh_button.clicked.connect(self.refresh)
        self.detail_button = QPushButton("جزئیات"); self.detail_button.clicked.connect(self.details)
        self.invoice_button = QPushButton("نمایش فاکتور"); self.invoice_button.clicked.connect(self.show_invoice)
        self.delete_button = QPushButton("حذف رسید"); self.delete_button.setObjectName("DangerButton")
        self.delete_button.clicked.connect(self.delete_receipt)
        self.export_button = QPushButton("خروجی CSV"); self.export_button.clicked.connect(self.export_csv)
        for button in (self.refresh_button,self.detail_button,self.invoice_button,self.delete_button,self.export_button): header.addWidget(button)
        layout.addLayout(header)
        self.table = QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(["شناسه","شماره روزانه","مبلغ کل","پرداخت","زمان"])
        self.table.setColumnHidden(0,True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True); self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda _item:self.details())
        layout.addWidget(self.table,1)
        pager = QHBoxLayout()
        pager.addWidget(QLabel("تعداد در صفحه"))
        self.page_size_combo = QComboBox()
        for size in (25, 50, 100):
            self.page_size_combo.addItem(str(size), size)
        self.page_size_combo.currentIndexChanged.connect(self._page_size_changed)
        pager.addWidget(self.page_size_combo)
        self.page_label = QLabel("صفحه ۱ از ۱")
        self.page_label.setObjectName("PageSubtitle")
        pager.addWidget(self.page_label)
        pager.addStretch(1)
        self.previous_page_button = QPushButton("صفحهٔ قبل")
        self.next_page_button = QPushButton("صفحهٔ بعد")
        self.previous_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        pager.addWidget(self.previous_page_button)
        pager.addWidget(self.next_page_button)
        layout.addLayout(pager)

    def refresh(self):
        if self.window.api: self.window.run_api(lambda: self.window.api.list_receipts(page_size=100), self.populate)

    def populate(self, records):
        self.records = list(records or [])
        self.current_page = 1
        self._render_page()

    def _render_page(self):
        total = len(self.records)
        pages = max(1, (total + self.page_size - 1) // self.page_size)
        self.current_page = min(max(1, self.current_page), pages)
        start = (self.current_page - 1) * self.page_size
        visible = self.records[start:start + self.page_size]
        self.table.setRowCount(0)
        for row, record in enumerate(visible):
            self.table.insertRow(row)
            values=[record["id"],record["day_receipt_id"],display_value("total_price",record["total_price"]),
                    "پرداخت‌شده" if record["payed"] else "پرداخت‌نشده",record["created_at"]]
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                if col==0:item.setData(Qt.ItemDataRole.UserRole,record)
                self.table.setItem(row,col,item)
        self.page_label.setText("صفحه {} از {} · {} رسید".format(self.current_page, pages, total))
        self.previous_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < pages)
        user = self.window.current_user
        self.delete_button.setVisible(can_access(user, "receipts", "delete"))
        self.invoice_button.setVisible(can_access(user, "invoices", "read"))

    def _page_size_changed(self, *_args):
        self.page_size = int(self.page_size_combo.currentData() or 25)
        self.current_page = 1
        self._render_page()

    def previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_page()

    def next_page(self):
        pages = max(1, (len(self.records) + self.page_size - 1) // self.page_size)
        if self.current_page < pages:
            self.current_page += 1
            self._render_page()

    def selected(self):
        row=self.table.currentRow()
        item=self.table.item(row,0) if row>=0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def details(self):
        record=self.selected()
        if not record:self.window.show_error("ابتدا یک رسید را انتخاب کنید.");return
        self.window.run_api(lambda:self.window.api.get_receipt(record["id"]),self.show_details)

    def show_details(self, receipt):
        lines=["شماره روزانه: {}".format(receipt["day_receipt_id"]),
               "مبلغ کل: {}".format(receipt["total_price"]),
               "پرداخت: {}".format("بله" if receipt["payed"] else "خیر"),"","اقلام:"]
        lines += ["{} × {} | خرید {} | فروش {}".format(item.get("product_name") or "محصول حذف‌شده",
                  item["quantity"],item["buy_price"],item["sell_price"]) for item in receipt.get("items",[])]
        QMessageBox.information(self,"جزئیات رسید","\n".join(lines))

    def show_invoice(self):
        record = self.selected()
        if not record:
            self.window.show_error("ابتدا یک رسید را انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_receipt(record["id"]),
            self._load_invoice_template,
        )

    def _load_invoice_template(self, receipt):
        self.window.run_api(
            self.window.api.get_invoice_template,
            lambda template: InvoiceDialog(receipt, template, self).exec(),
        )

    def delete_receipt(self):
        record=self.selected()
        if not record:self.window.show_error("ابتدا یک رسید را انتخاب کنید.");return
        answer=QMessageBox.question(self,"حذف رسید","رسید {} حذف شود؟".format(record["day_receipt_id"]),
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.window.run_api(lambda:self.window.api.delete_receipt(record["id"]),lambda _r:self._deleted(),busy=self.delete_button)

    def _deleted(self):
        self.window.set_status("رسید حذف شد.");self.refresh();self.window.refresh_dashboard_data()

    def export_csv(self):
        if not self.records:self.window.show_error("داده‌ای برای خروجی وجود ندارد.");return
        path,_=QFileDialog.getSaveFileName(self,"ذخیره رسیدها","receipts.csv","CSV (*.csv)")
        if not path:return
        try:
            with open(path,"w",newline="",encoding="utf-8-sig") as stream:
                writer=csv.DictWriter(stream,fieldnames=["id","day_receipt_id","total_price","payed","user_id","created_at"],extrasaction="ignore")
                writer.writeheader();writer.writerows(self.records)
        except OSError as exc:self.window.show_error(exc);return
        self.window.set_status("خروجی ذخیره شد: "+path)
