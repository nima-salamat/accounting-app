"""Permission-controlled administration of self-service kiosk policy."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from client.ui.permissions import can_access


class KioskSettingsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.products = []
        self._loading = False
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("مدیریت کیوسک خودخدمت")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "کیوسک باید از این بخش فعال شود. فقط کالاهای انتخاب‌شده نمایش داده می‌شوند و سرور نیز "
            "فروش کالاهای خارج از این فهرست را رد می‌کند."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles, 1)
        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button)
        root.addLayout(heading)

        settings_card = QFrame()
        settings_card.setObjectName("Card")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setSpacing(10)
        self.active_checkbox = QCheckBox("کیوسک فعال باشد و اجازه ثبت سفارش داشته باشد")
        self.active_checkbox.setStyleSheet("font-weight:800;font-size:15px;")
        self.allow_unpaid_checkbox = QCheckBox(
            "اجازه ثبت سفارش پرداخت‌نشده (فقط برای پرداخت یا تحویل توسط کارمند)"
        )
        self.seat_checkbox = QCheckBox("انتخاب شماره صندلی / میز برای کافه")
        self.history_hours = QSpinBox()
        self.history_hours.setRange(0, 720)
        self.history_hours.setSuffix(" ساعت")
        self.history_hours.setToolTip("۰ یعنی فاکتور قبلی نشان داده نشود؛ بیشینه ۳۰ روز است.")
        history_row = QHBoxLayout()
        history_label = QLabel("مدت نمایش فاکتورهای قبلی در صندوق")
        history_label.setObjectName("PageSubtitle")
        history_row.addWidget(history_label, 1)
        history_row.addWidget(self.history_hours)
        settings_layout.addWidget(self.active_checkbox)
        settings_layout.addWidget(self.allow_unpaid_checkbox)
        settings_layout.addWidget(self.seat_checkbox)
        settings_layout.addLayout(history_row)
        history_hint = QLabel(
            "پیش‌فرض ۴۸ ساعت است. این محدودیت برای فهرست فاکتورهای اخیر صندوق اعمال می‌شود؛ "
            "گزارش‌ها و صفحهٔ آرشیو رسیدها مسیر جداگانه دارند."
        )
        history_hint.setObjectName("PageSubtitle")
        history_hint.setWordWrap(True)
        settings_layout.addWidget(history_hint)
        root.addWidget(settings_card)

        products_card = QFrame()
        products_card.setObjectName("Card")
        products_layout = QVBoxLayout(products_card)
        products_layout.setContentsMargins(16, 14, 16, 14)
        products_layout.setSpacing(8)
        product_heading = QHBoxLayout()
        product_title = QLabel("محصولات قابل نمایش در کیوسک")
        product_title.setObjectName("PageTitle")
        self.selection_label = QLabel("۰ محصول انتخاب‌شده")
        self.selection_label.setObjectName("StatusPill")
        product_heading.addWidget(product_title, 1)
        product_heading.addWidget(self.selection_label)
        products_layout.addLayout(product_heading)
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText("جست‌وجوی نام کالا…")
        self.product_search.setClearButtonEnabled(True)
        self.product_search.textChanged.connect(self._filter_products)
        products_layout.addWidget(self.product_search)
        self.product_list = QListWidget()
        self.product_list.setMinimumHeight(240)
        self.product_list.itemChanged.connect(self._selection_changed)
        products_layout.addWidget(self.product_list, 1)
        select_tools = QHBoxLayout()
        self.select_visible_button = QPushButton("انتخاب نتایج")
        self.select_visible_button.clicked.connect(lambda: self._set_visible_checked(True))
        self.clear_visible_button = QPushButton("لغو نتایج")
        self.clear_visible_button.clicked.connect(lambda: self._set_visible_checked(False))
        select_tools.addWidget(self.select_visible_button)
        select_tools.addWidget(self.clear_visible_button)
        select_tools.addStretch(1)
        products_layout.addLayout(select_tools)
        root.addWidget(products_card, 1)

        footer = QHBoxLayout()
        self.status = QLabel("تنظیمات ذخیره نشده است.")
        self.status.setObjectName("PageSubtitle")
        self.status.setWordWrap(True)
        self.save_button = QPushButton("ذخیره تنظیمات کیوسک")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setMinimumHeight(42)
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.status, 1)
        footer.addWidget(self.save_button)
        root.addLayout(footer)
        self.set_permissions(window.current_user)

    def set_permissions(self, user):
        can_read = can_access(user, "kiosk", "read") and can_access(user, "products", "read")
        can_update = can_access(user, "kiosk", "update") and can_access(user, "products", "read")
        for widget in (
            self.active_checkbox, self.allow_unpaid_checkbox, self.seat_checkbox,
            self.history_hours, self.product_search, self.product_list,
            self.select_visible_button, self.clear_visible_button,
        ):
            widget.setEnabled(can_update)
        self.save_button.setVisible(can_update)
        self.refresh_button.setVisible(can_read)
        if not can_read:
            self.status.setText("برای مشاهده تنظیمات کیوسک، مجوز مدیریت کیوسک لازم است.")

    def refresh(self):
        if not self.window.api or not can_access(self.window.current_user, "kiosk", "read"):
            return
        self.window.run_api(
            self._load_payload,
            self._populate,
            failure=lambda error: self.window.show_error(error),
            busy=self.refresh_button,
        )

    def _load_payload(self):
        config = self.window.api.get_kiosk_settings()
        products = []
        page = 1
        total = None
        while True:
            data = self.window.api.list_products_page(page=page, page_size=200)
            batch = list(data.get("items") or [])
            products.extend(batch)
            total = int(data.get("total", len(products)))
            if not batch or len(products) >= total or len(batch) < 200:
                break
            page += 1
        company = self.window.api.get_company_profile()
        return {"config": config, "products": products, "company": company}

    def _populate(self, payload):
        config = payload.get("config") or {}
        self.products = list(payload.get("products") or [])
        company = payload.get("company") or {}
        selected = {str(value) for value in config.get("allowed_product_ids") or []}
        self._loading = True
        self.active_checkbox.setChecked(bool(config.get("active")))
        self.allow_unpaid_checkbox.setChecked(bool(config.get("allow_unpaid_orders")))
        default_seat = company.get("business_profile") == "cafe"
        self.seat_checkbox.setChecked(bool(config.get("cafe_seat_selection", default_seat)))
        self.history_hours.setValue(int(config.get("receipt_history_hours", 48)))
        self.product_list.clear()
        for product in self.products:
            name = str(product.get("name") or "کالای بدون نام")
            suffix = " · {:,.2f}".format(float(product.get("sell_price") or 0))
            if product.get("track_stock"):
                suffix += " · موجودی {}".format(product.get("stock_quantity") or 0)
            item = QListWidgetItem(name + suffix)
            item.setData(Qt.ItemDataRole.UserRole, str(product.get("id")))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(
                Qt.CheckState.Checked if str(product.get("id")) in selected else Qt.CheckState.Unchecked
            )
            self.product_list.addItem(item)
        self._loading = False
        self._filter_products()
        self._selection_changed()
        self.status.setText("تنظیمات بارگذاری شد. برای اعمال تغییرات، ذخیره را بزنید.")

    def _filter_products(self, *_args):
        query = self.product_search.text().strip().casefold()
        for row in range(self.product_list.count()):
            item = self.product_list.item(row)
            name = item.text().casefold()
            item.setHidden(bool(query) and query not in name)

    def _set_visible_checked(self, checked):
        self._loading = True
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.product_list.count()):
            item = self.product_list.item(row)
            if not item.isHidden():
                item.setCheckState(state)
        self._loading = False
        self._selection_changed()

    def _selection_changed(self, *_args):
        if self._loading:
            return
        count = sum(
            self.product_list.item(row).checkState() == Qt.CheckState.Checked
            for row in range(self.product_list.count())
        )
        self.selection_label.setText("{} محصول انتخاب‌شده".format(count))

    def save(self):
        if not self.window.api or not can_access(self.window.current_user, "kiosk", "update"):
            self.window.show_error("مجوز تغییر تنظیمات کیوسک را ندارید.")
            return
        selected = [
            self.product_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.product_list.count())
            if self.product_list.item(row).checkState() == Qt.CheckState.Checked
        ]
        if self.active_checkbox.isChecked() and not selected:
            QMessageBox.warning(self, "محصولی انتخاب نشده", "برای فعال‌سازی کیوسک، حداقل یک محصول انتخاب کنید.")
            return
        payload = {
            "active": self.active_checkbox.isChecked(),
            "allowed_product_ids": selected,
            "receipt_history_hours": self.history_hours.value(),
            "cafe_seat_selection": self.seat_checkbox.isChecked(),
            "allow_unpaid_orders": self.allow_unpaid_checkbox.isChecked(),
        }
        self.window.run_api(
            lambda: self.window.api.save_kiosk_settings(**payload),
            self._saved,
            busy=self.save_button,
        )

    def _saved(self, config):
        self.status.setText(
            "ذخیره شد · کیوسک {} · {} محصول مجاز · تاریخچه {} ساعت".format(
                "فعال" if config.get("active") else "غیرفعال",
                len(config.get("allowed_product_ids") or []),
                config.get("receipt_history_hours", 48),
            )
        )
        self.window.set_status("تنظیمات کیوسک ذخیره شد.")
        QMessageBox.information(self, "تنظیمات ذخیره شد", "سیاست سرور برای کیوسک به‌روزرسانی شد.")
