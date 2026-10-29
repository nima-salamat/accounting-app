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
from client.ui.invoice_render import SALES_INVOICE_TEMPLATE_KIND
from client.ui.returns_page import ReturnDialog
from client.ui.currency import format_currency
from client.ui.currency import format_currency


def display_value(key, value):
    if key in ("payed", "is_admin", "is_active", "requires_session_activation", "custom_product", "track_stock"):
        return ("فعال" if value else "غیرفعال") if key == "is_active" else ("بله" if value else "خیر")
    if key == "status":
        return {"pending": "در انتظار تأیید", "active": "فعال",
                "revoked": "لغوشده", "expired": "منقضی"}.get(value, value or "—")
    if key == "image_path":
        return "دارد" if value else "ندارد"
    if key in ("buy_price", "sell_price", "price", "total_price", "revenue"):
        try:
            return format_currency(value)
        except (ValueError, TypeError):
            pass
    return "—" if value is None or value == "" else str(value)


class ApiTablePage(QFrame):
    """Reusable record table. Data access always crosses AccountingApiClient."""
    def __init__(self, window, title, subtitle, columns, load_fn, fields=(),
                 create_fn=None, update_fn=None, delete_fn=None, searchable=True,
                 schema_entity=None):
        super().__init__()
        self.window, self.title = window, title
        self.base_columns = list(columns)
        self.columns = list(columns)
        self.schema_entity = schema_entity
        self.custom_fields = []
        self.load_fn, self.fields = load_fn, list(fields)
        self.create_fn, self.update_fn, self.delete_fn = create_fn, update_fn, delete_fn
        self.searchable = searchable
        self.records = []
        self.current_page = 1
        self.page_size = 25
        self.total_records = 0
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
        self.select_page_button = QPushButton("انتخاب همهٔ صفحه")
        self.select_page_button.clicked.connect(self.select_current_page)
        self.clear_selection_button = QPushButton("لغو انتخاب")
        self.clear_selection_button.clicked.connect(self.table_clear_selection)
        self.selection_count = QLabel("انتخاب‌شده: ۰")
        self.selection_count.setObjectName("StatusPill")
        tools.addWidget(self.select_page_button)
        tools.addWidget(self.clear_selection_button)
        tools.addWidget(self.selection_count)
        layout.addLayout(tools)
        self.table = QTableWidget(0, len(columns))
        self.table.setObjectName("ResourceTable")
        self.table.setHorizontalHeaderLabels([label for _key, label in columns])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.table.itemSelectionChanged.connect(self._update_selection_count)
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

    def _form_fields(self):
        return list(self.fields)

    def set_admin(self, is_admin):
        self.create_button.setVisible(bool(is_admin) and self.create_fn is not None)
        self.edit_button.setVisible(bool(is_admin) and self.update_fn is not None)
        self.delete_button.setVisible(bool(is_admin) and self.delete_fn is not None)

    def set_permissions(self, user, resource):
        self.create_button.setVisible(can_access(user, resource, "create") and self.create_fn is not None)
        self.edit_button.setVisible(can_access(user, resource, "update") and self.update_fn is not None)
        self.delete_button.setVisible(can_access(user, resource, "delete") and self.delete_fn is not None)

    def refresh(self, *_args):
        if not self.window.api:
            return
        self.current_page = 1
        self._request_current_page()

    def _request_current_page(self):
        if not self.window.api:
            return
        query = self.search_input.text().strip() if self.searchable else ""
        self.window.run_api(
            lambda: self._load_table_payload(
                self.window.api, query, self.current_page, self.page_size
            ),
            self.populate,
            busy=self.refresh_button,
        )

    def _load_table_payload(self, api, query, page, page_size):
        response = self.load_fn(api, query, page, page_size)
        if isinstance(response, dict) and "items" in response:
            records = list(response.get("items") or [])
            total = int(response.get("total", len(records)))
        else:
            records = list(response or [])
            total = len(records)
        payload = {
            "records": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "custom": {"fields": [], "values": {}},
        }
        if self.schema_entity and payload["records"] and can_access(
            self.window.current_user, "schemas", "read"
        ):
            extension = api.get_custom_table_data(
                self.schema_entity, [record.get("id") for record in payload["records"]]
            )
            payload["custom"] = extension or payload["custom"]
        return payload

    def populate(self, payload):
        if isinstance(payload, dict) and "records" in payload:
            self.records = list(payload.get("records") or [])
            self.total_records = int(payload.get("total", len(self.records)))
            self.current_page = int(payload.get("page", 1))
            custom = payload.get("custom") or {}
        else:
            self.records = list(payload or [])
            self.total_records = len(self.records)
            self.current_page = 1
            custom = {}
        self.custom_fields = list(custom.get("fields") or [])
        values_by_id = custom.get("values") or {}
        self.columns = list(self.base_columns) + [
            ("custom:" + field["key"], field["label"])
            for field in self.custom_fields
        ]
        for record in self.records:
            record["custom_fields"] = dict(values_by_id.get(str(record.get("id")), {}))
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels([label for _key, label in self.columns])
        self.table.setColumnHidden(0, True)
        self._render_page()

    def _render_page(self):
        total = self.total_records
        pages = max(1, (total + self.page_size - 1) // self.page_size)
        self.current_page = max(1, min(self.current_page, pages))
        start = (self.current_page - 1) * self.page_size
        visible = self.records
        self.table.clearSelection()
        self.table.setRowCount(0)
        for row, record in enumerate(visible):
            self.table.insertRow(row)
            for col, (key, _label) in enumerate(self.columns):
                if key.startswith("custom:"):
                    value = (record.get("custom_fields") or {}).get(key.split(":", 1)[1])
                else:
                    value = record.get(key)
                item = QTableWidgetItem(display_value(key, value))
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
        self._update_selection_count()

    def _page_size_changed(self, *_args):
        if hasattr(self, "page_size_combo"):
            self.page_size = int(self.page_size_combo.currentData() or 25)
            self.current_page = 1
            self._request_current_page()

    def previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._request_current_page()

    def next_page(self):
        pages = max(1, (self.total_records + self.page_size - 1) // self.page_size)
        if self.current_page < pages:
            self.current_page += 1
            self._request_current_page()

    def select_current_page(self):
        self.table.selectAll()
        self._update_selection_count()

    def table_clear_selection(self):
        self.table.clearSelection()
        self._update_selection_count()

    def _update_selection_count(self):
        count = len(self.table.selectionModel().selectedRows()) if self.table.selectionModel() else 0
        self.selection_count.setText("انتخاب‌شده: {}".format(count))
        self.clear_selection_button.setEnabled(count > 0)

    def selected_record(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def create_record(self):
        if not self.create_fn:
            return
        dialog = RecordDialog("افزودن " + self.title, self._form_fields(), parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            payload = dialog.values()
        except ValueError as exc:
            self.window.show_error(exc); return
        self.window.run_api(
            lambda: self.create_fn(self.window.api, payload),
            lambda result: self._mutation_done(self.title + " ساخته شد.", result=result),
            busy=self.create_button,
        )

    def edit_record(self):
        if not self.update_fn:
            return
        record = self.selected_record()
        if not record:
            self.window.show_error("ابتدا یک رکورد را انتخاب کنید."); return
        dialog = RecordDialog("ویرایش " + self.title, self._form_fields(), record, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            payload = dialog.values()
        except ValueError as exc:
            self.window.show_error(exc); return
        self.window.run_api(
            lambda: self.update_fn(self.window.api, record["id"], payload),
            lambda result: self._mutation_done(self.title + " به‌روزرسانی شد.", result=result),
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

    def _mutation_done(self, message, result=None):
        self.window.set_status(message)
        self.refresh()
        self.window.refresh_dashboard_data()
        image_error = result.get("_image_upload_error") if isinstance(result, dict) else None
        if image_error:
            record_name = result.get("name") or result.get("id") or "محصول"
            QMessageBox.warning(
                self,
                "رکورد ذخیره شد؛ بارگذاری تصویر ناموفق بود",
                "«{}» با موفقیت ذخیره شده است، اما تصویر آن بارگذاری نشد. برای جلوگیری از ایجاد رکورد تکراری، محصول را دوباره نسازید؛ پس از اصلاح دسترسی یا انتخاب فایل، تصویر را از بخش ویرایش محصول بارگذاری کنید.\n\nجزئیات خطا: {}".format(record_name, image_error),
            )

    def export_csv(self):
        if not self.records and self.total_records == 0:
            self.window.show_error("داده‌ای برای خروجی وجود ندارد.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "ذخیرهٔ CSV", "export.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        self.window.run_api(
            self._collect_export_payload,
            lambda payload: self._write_export_csv(path, payload),
            busy=self.export_button,
        )

    def _collect_export_payload(self):
        api = self.window.api
        query = self.search_input.text().strip() if self.searchable else None
        page_size = 200
        page = 1
        records = []
        total = None
        fields = []
        while True:
            response = self.load_fn(api, query, page, page_size)
            if isinstance(response, dict) and "items" in response:
                batch = list(response.get("items") or [])
                total = int(response.get("total", len(batch))) if total is None else total
            else:
                batch = list(response or [])
                total = len(batch) if total is None else total
            if not batch:
                break
            extension = {"fields": [], "values": {}}
            if self.schema_entity and can_access(self.window.current_user, "schemas", "read"):
                extension = api.get_custom_table_data(
                    self.schema_entity, [item.get("id") for item in batch]
                ) or extension
            fields = list(extension.get("fields") or fields)
            values = extension.get("values") or {}
            for record in batch:
                record["custom_fields"] = dict(values.get(str(record.get("id")), {}))
            records.extend(batch)
            if len(records) >= total or len(batch) < page_size:
                break
            page += 1
        return {"records": records, "custom_fields": fields}

    def _write_export_csv(self, path, payload):
        records = list(payload.get("records") or [])
        custom_fields = list(payload.get("custom_fields") or [])
        columns = list(self.base_columns) + [
            ("custom:" + field["key"], field["label"]) for field in custom_fields
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                fieldnames = [key for key, _label in columns]
                writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for record in records:
                    row = dict(record)
                    custom_values = row.get("custom_fields") or {}
                    for key, _label in columns:
                        if key.startswith("custom:"):
                            row[key] = custom_values.get(key.split(":", 1)[1])
                    writer.writerow(row)
        except OSError as exc:
            self.window.show_error(exc)
            return
        self.window.set_status("خروجی کامل {} رکورد ذخیره شد: {}".format(len(records), path))


class ProductsPage(ApiTablePage):
    def __init__(self, window):
        fields = [
            {"key": "name", "label": "نام محصول", "required": True},
            {"key": "buy_price", "label": "قیمت خرید", "kind": "number", "required": False, "currency": True},
            {"key": "sell_price", "label": "قیمت فروش", "kind": "number", "required": True, "currency": True},
            {"key": "category_id", "label": "شناسهٔ دسته‌بندی (اختیاری)", "nullable": True},
            {"key": "custom_product", "label": "محصول سفارشی", "kind": "bool"},
            {"key": "track_stock", "label": "رهگیری موجودی", "kind": "bool"},
            {"key": "reorder_level", "label": "حد سفارش", "kind": "number", "default": 0, "required": True},
            {"key": "image_file", "display_key": "image_path", "label": "عکس محصول (اختیاری)", "kind": "image"},
        ]
        super().__init__(window, "محصولات", "نام، قیمت‌ها و دسته‌بندی کالاها.",
            [("id","شناسه"),("name","نام محصول"),("image_path","تصویر"),
             ("buy_price","قیمت خرید"),("sell_price","قیمت فروش"),("track_stock","رهگیری"),
             ("stock_quantity","موجودی"),("reorder_level","حد سفارش"),("category_id","دسته‌بندی")],
            lambda api,q,page,page_size: api.list_products_page(q=q or None,page=page,page_size=page_size), fields,
            lambda api,p: self._create_product(api, p),
            lambda api,rid,p: self._update_product(api, rid, p),
            lambda api,rid: api.delete_product(rid), schema_entity="products")

    def _form_fields(self):
        required = bool((getattr(self.window, "company_profile", None) or {}).get(
            "product_buy_price_required", True
        ))
        specs = []
        for source in self.fields:
            spec = dict(source)
            if spec.get("key") == "buy_price":
                spec["required"] = required
                spec["label"] = "قیمت خرید" if required else "قیمت خرید (اختیاری)"
            specs.append(spec)
        return specs

    @staticmethod
    def _save_product_image_without_losing_record(api, product, image_file):
        """Keep the successful record mutation when its optional image upload fails."""
        if not image_file:
            return product
        try:
            api.upload_product_image(product["id"], image_file)
        except Exception as exc:
            # The record already exists. Returning partial-success data avoids unsafe retries.
            result = dict(product)
            result["_image_upload_error"] = str(exc) or exc.__class__.__name__
            return result
        return product

    @staticmethod
    def _create_product(api, payload):
        values = dict(payload)
        image_file = values.pop("image_file", None)
        product = api.create_product(**values)
        return ProductsPage._save_product_image_without_losing_record(api, product, image_file)

    @staticmethod
    def _update_product(api, record_id, payload):
        values = dict(payload)
        image_file = values.pop("image_file", None)
        product = dict(api.update_product(record_id, **values))
        product.setdefault("id", record_id)
        return ProductsPage._save_product_image_without_losing_record(api, product, image_file)


class CategoriesPage(ApiTablePage):
    def __init__(self, window):
        super().__init__(window, "دسته‌بندی‌ها", "گروه‌بندی کالاها برای یافتن و تحلیل بهتر.",
            [("id","شناسه"),("name","نام دسته‌بندی")],
            lambda api,q,page,page_size: api.list_categories_page(q=q or None,page=page,page_size=page_size),
            [{"key":"name","label":"نام دسته‌بندی","required":True}],
            lambda api,p: api.create_category(**p),
            lambda api,rid,p: api.update_category(rid,**p),
            lambda api,rid: api.delete_category(rid), schema_entity="categories")


class WarehousePage(ApiTablePage):
    def __init__(self, window):
        fields = [
            {"key":"name","label":"نام","required":True},
            {"key":"price","label":"قیمت واحد","kind":"number","required":True,"currency":True},
            {"key":"amount","label":"مقدار","kind":"number","required":True},
            {"key":"unit","label":"واحد","kind":"select","required":True,"choices":[
                ("عدد","pcs"),("کیلوگرم","kg"),("متر","m"),("لیتر","l")]},
        ]
        super().__init__(window,"انبار","مقدار و ارزش اقلام انبار.",
            [("id","شناسه"),("name","نام"),("price","قیمت"),("amount","مقدار"),("unit","واحد")],
            lambda api,q,page,page_size: api.list_warehouses_page(q=q or None,page=page,page_size=page_size), fields,
            lambda api,p: api.create_warehouse(**p),
            lambda api,rid,p: api.update_warehouse(rid,**p),
            lambda api,rid: api.delete_warehouse(rid), schema_entity="warehouses")


class ChecksPage(ApiTablePage):
    def __init__(self, window, direction="in"):
        self.direction = direction
        title = "چک‌های دریافتی" if direction == "in" else "چک‌های پرداختی"
        fields = [
            {"key":"name","label":"طرف حساب","required":True},
            {"key":"check_id","label":"شماره چک","required":True},
            {"key":"price","label":"مبلغ","kind":"number","required":True,"currency":True},
            {"key":"date","label":"تاریخ","required":True},
            {"key":"payed","label":"پرداخت‌شده","kind":"bool"},
        ]
        super().__init__(window,title,"اطلاعات و وضعیت چک‌ها.",
            [("id","شناسه"),("name","طرف حساب"),("check_id","شماره چک"),
             ("price","مبلغ"),("date","تاریخ"),("payed","پرداخت")],
            lambda api,q,page,page_size: api.list_checks_page(direction,q=q or None,page=page,page_size=page_size), fields,
            lambda api,p: api.create_check(direction,**p),
            lambda api,rid,p: api.update_check(direction,rid,**p),
            lambda api,rid: api.delete_check(direction,rid),
            schema_entity="check_ins" if direction == "in" else "check_outs")


class UsersPage(ApiTablePage):
    def __init__(self, window):
        fields = [
            {"key":"username","label":"نام کاربری","required":True},
            {"key":"password","label":"رمز عبور","kind":"password","required":True,
             "placeholder":"برای ویرایش، خالی بماند"},
            {"key":"is_admin","label":"مدیر سیستم","kind":"bool"},
            {"key":"is_active","label":"حساب فعال","kind":"bool","default":True},
            {"key":"requires_session_activation","label":"تأیید مدیر برای ورود هر دستگاه","kind":"bool","default":True},
            {"key":"max_active_sessions","label":"حداکثر نشست هم‌زمان","kind":"integer","default":1,"placeholder":"۱ تا ۲۰؛ پیش‌فرض ۱"},
            {"key":"buttons","label":"مجوزهای پنل","nullable":True},
        ]
        super().__init__(window,"کاربران و دسترسی‌ها",
            "حساب‌ها را فعال یا غیرفعال کنید و تعیین کنید نشست دستگاه‌های جدید به تأیید مدیر نیاز دارند یا خیر.",
            [("id","شناسه"),("username","نام کاربری"),("is_admin","مدیر"),
             ("is_active","حساب فعال"),("requires_session_activation","تأیید دستگاه"),
             ("max_active_sessions","حد نشست فعال"),("buttons","مجوزها")],
            lambda api,q,page,page_size: api.list_users_page(q=q or None,page=page,page_size=page_size), fields,
            lambda api,p: api.create_user(**p),
            lambda api,rid,p: api.update_user(rid,**p),
            lambda api,rid: api.delete_user(rid), schema_entity="users")


class ReceiptsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window, self.records = window, []
        self.current_page, self.page_size = 1, 25
        self.total_records = 0
        self.base_columns = [
            ("id", "شناسه"), ("invoice_number", "شماره فاکتور"),
            ("total_price", "مبلغ کل"), ("payed", "پرداخت"), ("created_at", "زمان"),
        ]
        self.columns = list(self.base_columns)
        self.custom_fields = []
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
        self.return_button = QPushButton("مرجوعی / استرداد"); self.return_button.clicked.connect(self.create_return)
        self.delete_button = QPushButton("حذف رسید"); self.delete_button.setObjectName("DangerButton")
        self.delete_button.clicked.connect(self.delete_receipt)
        self.export_button = QPushButton("خروجی CSV"); self.export_button.clicked.connect(self.export_csv)
        for button in (self.refresh_button,self.detail_button,self.invoice_button,self.return_button,self.delete_button,self.export_button): header.addWidget(button)
        layout.addLayout(header)
        self.table = QTableWidget(0,len(self.columns))
        self.table.setHorizontalHeaderLabels([label for _key, label in self.columns])
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

    def refresh(self, *_args):
        if self.window.api:
            self.window.run_api(self._load_receipts_payload, self.populate, busy=self.refresh_button)

    def _load_receipts_payload(self):
        page_data = self.window.api.list_receipts_page(
            page=self.current_page, page_size=self.page_size
        )
        records = list(page_data.get("items") or [])
        custom = {"fields": [], "values": {}}
        if records and can_access(self.window.current_user, "schemas", "read"):
            custom = self.window.api.get_custom_table_data(
                "receipts", [record.get("id") for record in records]
            )
        return {
            "records": records,
            "total": int(page_data.get("total", len(records))),
            "page": int(page_data.get("page", self.current_page)),
            "custom": custom or {"fields": [], "values": {}},
        }

    def populate(self, payload):
        if isinstance(payload, dict) and "records" in payload:
            self.records = list(payload.get("records") or [])
            self.total_records = int(payload.get("total", len(self.records)))
            self.current_page = int(payload.get("page", 1))
            custom = payload.get("custom") or {}
        else:
            self.records = list(payload or [])
            self.total_records = len(self.records)
            self.current_page = 1
            custom = {}
        self.custom_fields = list(custom.get("fields") or [])
        values_by_id = custom.get("values") or {}
        self.columns = list(self.base_columns) + [
            ("custom:" + field["key"], field["label"])
            for field in self.custom_fields
        ]
        for record in self.records:
            record["custom_fields"] = dict(values_by_id.get(str(record.get("id")), {}))
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels([label for _key, label in self.columns])
        self.table.setColumnHidden(0, True)
        self._render_page()

    def _render_page(self):
        total = self.total_records
        pages = max(1, (total + self.page_size - 1) // self.page_size)
        self.current_page = min(max(1, self.current_page), pages)
        start = (self.current_page - 1) * self.page_size
        visible = self.records
        self.table.setRowCount(0)
        for row, record in enumerate(visible):
            self.table.insertRow(row)
            for col, (key, _label) in enumerate(self.columns):
                if key.startswith("custom:"):
                    value = (record.get("custom_fields") or {}).get(key.split(":", 1)[1])
                elif key == "total_price":
                    value = display_value(key, record.get(key))
                elif key == "payed":
                    value = "پرداخت‌شده" if record.get(key) else "پرداخت‌نشده"
                elif key == "invoice_number":
                    value = record.get("invoice_number") or record.get("day_receipt_id")
                else:
                    value = record.get(key)
                item = QTableWidgetItem(display_value(key, value))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record)
                self.table.setItem(row, col, item)
        self.page_label.setText("صفحه {} از {} · {} رسید".format(self.current_page, pages, total))
        self.previous_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < pages)
        user = self.window.current_user
        self.delete_button.setVisible(can_access(user, "receipts", "delete"))
        self.invoice_button.setVisible(can_access(user, "invoices", "read"))
        self.return_button.setVisible(can_access(user, "returns", "create") and can_access(user, "receipts", "read"))

    def _page_size_changed(self, *_args):
        self.page_size = int(self.page_size_combo.currentData() or 25)
        self.current_page = 1
        self.refresh()

    def previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh()

    def next_page(self):
        pages = max(1, (self.total_records + self.page_size - 1) // self.page_size)
        if self.current_page < pages:
            self.current_page += 1
            self.refresh()

    def selected(self):
        row=self.table.currentRow()
        item=self.table.item(row,0) if row>=0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def details(self):
        record=self.selected()
        if not record:self.window.show_error("ابتدا یک رسید را انتخاب کنید.");return
        self.window.run_api(lambda:self.window.api.get_receipt(record["id"]),self.show_details)

    def show_details(self, receipt):
        lines=["شماره فاکتور: {}".format(receipt.get("invoice_number") or receipt["day_receipt_id"]),
               "مبلغ کل: {}".format(format_currency(receipt["total_price"])),
               "پرداخت: {}".format("بله" if receipt["payed"] else "خیر"),"","اقلام:"]
        lines += ["{} × {} | خرید {} | فروش {}".format(
                  item.get("product_name") or "محصول حذف‌شده", item["quantity"],
                  format_currency(item["buy_price"]), format_currency(item["sell_price"])
                  ) for item in receipt.get("items",[])]
        QMessageBox.information(self,"جزئیات رسید","\n".join(lines))

    def create_return(self):
        record = self.selected()
        if not record:
            self.window.show_error("ابتدا فاکتور اصلی را انتخاب کنید.")
            return
        if not can_access(self.window.current_user, "returns", "create"):
            self.window.show_error("مجوز ثبت مرجوعی ندارید.")
            return
        self.window.run_api(
            lambda: self.window.api.get_receipt(record["id"]),
            self._open_return_dialog,
        )

    def _open_return_dialog(self, receipt):
        dialog = ReturnDialog(receipt, self)
        if dialog.exec() != ReturnDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.window.run_api(
            lambda: self.window.api.create_return(
                receipt["id"],
                values["items"],
                refund_method=values["refund_method"],
                reason=values["reason"],
                notes=values["notes"],
            ),
            self._return_created,
            busy=self.return_button,
        )

    def _return_created(self, result):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "مرجوعی ثبت شد",
            "سند مرجوعی به‌صورت موفق ثبت شد. مبلغ ثبت‌شده: {:,.2f}".format(
                float(result.get("total_amount") or 0)
            ),
        )
        self.window.set_status("مرجوعی برای فاکتور شمارهٔ {} ثبت شد.".format(result.get("day_receipt_id", "—")))
        self.refresh()
        returns_page = getattr(self.window, "returns_page", None)
        if returns_page is not None:
            returns_page.refresh()

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
        # The POS checkout preview, recent-invoice preview and receipt-list print
        # dialog all use the same admin-designed "فاکتور فروش" template.
        self.window.run_api(
            lambda: self.window.api.get_invoice_template(
                kind=SALES_INVOICE_TEMPLATE_KIND
            ),
            lambda template: InvoiceDialog(receipt, template, self).exec(),
            failure=lambda error: self.window.show_error(
                "قالب «فاکتور فروش» ذخیره‌شده در تنظیمات ادمین بارگذاری نشد: {}".format(error)
            ),
        )

    def delete_receipt(self):
        record=self.selected()
        if not record:self.window.show_error("ابتدا یک رسید را انتخاب کنید.");return
        answer=QMessageBox.question(self,"حذف رسید","رسید {} حذف شود؟".format(record.get("invoice_number") or record["day_receipt_id"]),
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.window.run_api(lambda:self.window.api.delete_receipt(record["id"]),lambda _r:self._deleted(),busy=self.delete_button)

    def _deleted(self):
        self.window.set_status("رسید حذف شد.");self.refresh();self.window.refresh_dashboard_data()

    def export_csv(self):
        if self.total_records == 0:
            self.window.show_error("داده‌ای برای خروجی وجود ندارد.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "ذخیرهٔ CSV", "receipts.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        self.window.run_api(
            self._collect_receipt_export,
            lambda payload: self._write_receipt_export(path, payload),
            busy=self.export_button,
        )

    def _collect_receipt_export(self):
        api = self.window.api
        page, page_size = 1, 200
        records, total, custom_fields = [], 0, []
        while True:
            result = api.list_receipts_page(page=page, page_size=page_size)
            batch = list(result.get("items") or [])
            total = int(result.get("total", len(batch)))
            if not batch:
                break
            extension = {"fields": [], "values": {}}
            if can_access(self.window.current_user, "schemas", "read"):
                extension = api.get_custom_table_data(
                    "receipts", [item.get("id") for item in batch]
                ) or extension
            custom_fields = list(extension.get("fields") or custom_fields)
            values = extension.get("values") or {}
            for record in batch:
                record["custom_fields"] = dict(values.get(str(record.get("id")), {}))
            records.extend(batch)
            if len(records) >= total or len(batch) < page_size:
                break
            page += 1
        return {"records": records, "custom_fields": custom_fields, "total": total}

    def _write_receipt_export(self, path, payload):
        records = list(payload.get("records") or [])
        custom_fields = list(payload.get("custom_fields") or [])
        columns = list(self.base_columns) + [("user_id", "شناسه کاربر")] + [
            ("custom:" + field["key"], field["label"]) for field in custom_fields
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                fieldnames = [key for key, _label in columns]
                writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for record in records:
                    row = dict(record)
                    custom_values = row.get("custom_fields") or {}
                    for key, _label in columns:
                        if key.startswith("custom:"):
                            row[key] = custom_values.get(key.split(":", 1)[1])
                    row["payed"] = "بله" if row.get("payed") else "خیر"
                    writer.writerow(row)
        except OSError as exc:
            self.window.show_error(exc)
            return
        self.window.set_status("خروجی کامل {} رسید ذخیره شد: {}".format(len(records), path))
