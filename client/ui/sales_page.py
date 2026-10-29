"""API-driven point-of-sale screen with search, quantity selection, and idempotent checkout."""
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor, QBrush, QPixmap
import uuid

from client.payment_terminal import authorize_payment, void_payment
from client.ui.device_settings import device_settings
from client.ui.invoice_dialog import InvoiceDialog, auto_print_invoice
from client.ui.invoice_render import DEFAULT_TEMPLATE
from client.ui.permissions import can_access
from client.ui.icons import apply_button_icons, set_button_icon

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QHeaderView, QWidget,
)


class SalesPage(QFrame):
    """API-driven point-of-sale page with a responsive catalog and independent cart."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.products = []
        self.categories = []
        self.product_page = 1
        self.product_page_size = 24
        self.total_products = 0
        self._last_filters = None
        self._loaded_product_page = 1
        self._cart = {}
        self._product_cache = {}
        self._product_add_buttons = {}
        self._category_names = {}
        self._rendered_columns = 0
        self._saved_splitter_sizes = [780, 360]
        self._business_profile = {}

        self._local_settings = QSettings("AccountingApp", "DesktopClient")
        self._show_product_images = self._local_settings.value(
            "sales/show_product_images", True, type=bool
        )

        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Keep global sale actions outside the splitter so they remain reachable
        # when the cashier collapses the cart or resizes the product catalog.
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("صندوق فروش")
        title.setObjectName("PageTitle")
        subtitle = QLabel("کالاها را انتخاب کنید و سبد را بررسی کنید؛ مبلغ قطعی و موجودی همیشه سمت سرور اعتبارسنجی می‌شود.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        self.refresh_button = QPushButton("بازخوانی کالاها")
        self.refresh_button.clicked.connect(self.refresh_products)
        header.addWidget(self.refresh_button)

        self.history_button = QPushButton("فاکتورهای اخیر")
        self.history_button.clicked.connect(self.show_recent_receipts)
        header.addWidget(self.history_button)

        self.show_cart_button = QPushButton("نمایش سبد")
        self.show_cart_button.setObjectName("PrimaryButton")
        self.show_cart_button.clicked.connect(lambda: self._set_cart_panel_visible(True))
        self.show_cart_button.hide()
        header.addWidget(self.show_cart_button)
        root.addLayout(header)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setObjectName("SalesWorkspaceSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.splitter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # In RTL mode the first splitter child is the right-hand catalog; the
        # cart is the second child and stays on the left-hand side.
        self.catalog_panel = self._build_catalog_panel()
        self.cart_panel = self._build_cart_panel()
        self.splitter.addWidget(self.catalog_panel)
        self.splitter.addWidget(self.cart_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes(self._saved_splitter_sizes)
        root.addWidget(self.splitter, 1)

        self.seat_row = QFrame()
        self.seat_row.setObjectName("Card")
        seat_layout = QHBoxLayout(self.seat_row)
        seat_layout.setContentsMargins(12, 8, 12, 8)
        self.seat_label = QLabel("شماره صندلی / میز")
        self.seat_label.setObjectName("PageSubtitle")
        self.seat_number = QComboBox()
        self.seat_number.addItem("انتخاب صندلی…", None)
        for seat in range(1, 31):
            self.seat_number.addItem("صندلی {}".format(seat), str(seat))
        seat_layout.addWidget(self.seat_label)
        seat_layout.addWidget(self.seat_number, 1)
        self.seat_row.hide()
        root.addWidget(self.seat_row)

        footer_card = QFrame()
        footer_card.setObjectName("Card")
        footer = QHBoxLayout(footer_card)
        footer.setContentsMargins(14, 10, 14, 10)
        self.paid = QCheckBox("فاکتور پرداخت شده است")
        self.total_label = QLabel("جمع تخمینی: —")
        self.total_label.setObjectName("MetricValue")
        self.submit_button = QPushButton("ثبت امن فروش")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.clicked.connect(self.checkout)
        footer.addWidget(self.paid)
        footer.addStretch(1)
        footer.addWidget(self.total_label)
        footer.addWidget(self.submit_button)
        root.addWidget(footer_card)

        self._refresh_cart_summary()
        apply_button_icons(self, getattr(self.window, "mode", "light"))

    def _build_catalog_panel(self):
        """Build the searchable, category-filtered product grid shown on the right."""
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("فهرست کالاها")
        title.setObjectName("PageTitle")
        self.catalog_count_label = QLabel("در حال بارگذاری کالاها")
        self.catalog_count_label.setObjectName("StatusPill")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.catalog_count_label)
        layout.addLayout(title_row)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("SalesProductSearch")
        self.search.setPlaceholderText("نام کالا را جست‌وجو کنید…")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.refresh_products)
        self.search_button = QPushButton("جست‌وجو")
        self.search_button.setToolTip("جست‌وجوی کالا")
        self.search_button.clicked.connect(self.refresh_products)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.search_button)
        layout.addLayout(filters)

        options = QHBoxLayout()
        category_label = QLabel("دسته‌بندی")
        category_label.setObjectName("PageSubtitle")
        self.category_combo = QComboBox()
        self.category_combo.setMinimumWidth(150)
        self.category_combo.addItem("همهٔ دسته‌ها", None)
        self.category_combo.currentIndexChanged.connect(self._category_changed)
        self.show_images_checkbox = QCheckBox("نمایش تصاویر کالا")
        self.show_images_checkbox.setChecked(self._show_product_images)
        self.show_images_checkbox.toggled.connect(self._toggle_product_images)
        options.addWidget(category_label)
        options.addWidget(self.category_combo, 1)
        options.addWidget(self.show_images_checkbox)
        layout.addLayout(options)

        self.catalog_scroll = QScrollArea()
        self.catalog_scroll.setObjectName("SalesProductScrollArea")
        self.catalog_scroll.setWidgetResizable(True)
        self.catalog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.product_grid_host = QWidget()
        self.product_grid_host.setObjectName("SalesProductGridHost")
        self.product_grid = QGridLayout(self.product_grid_host)
        self.product_grid.setContentsMargins(4, 4, 4, 4)
        self.product_grid.setHorizontalSpacing(10)
        self.product_grid.setVerticalSpacing(10)
        self.product_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.catalog_scroll.setWidget(self.product_grid_host)
        layout.addWidget(self.catalog_scroll, 1)

        pager = QHBoxLayout()
        self.previous_page_button = QPushButton("صفحهٔ قبل")
        self.previous_page_button.clicked.connect(lambda: self._change_product_page(-1))
        self.product_page_label = QLabel("صفحه ۱ از ۱")
        self.product_page_label.setObjectName("PageSubtitle")
        self.product_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_page_button = QPushButton("صفحهٔ بعد")
        self.next_page_button.clicked.connect(lambda: self._change_product_page(1))
        pager.addWidget(self.previous_page_button)
        pager.addWidget(self.product_page_label, 1)
        pager.addWidget(self.next_page_button)
        layout.addLayout(pager)
        return panel

    def _build_cart_panel(self):
        """Build a separately scrollable cart that can be resized or collapsed."""
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("سبد خرید")
        title.setObjectName("PageTitle")
        hint = QLabel("تعداد و اقلام انتخاب‌شده")
        hint.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)
        self.cart_status_label = QLabel("۰ قلم")
        self.cart_status_label.setObjectName("StatusPill")
        header.addWidget(self.cart_status_label)
        self.cart_panel_toggle = QPushButton("جمع‌کردن")
        self.cart_panel_toggle.setToolTip("جمع‌کردن پنل سبد خرید")
        self.cart_panel_toggle.clicked.connect(lambda: self._set_cart_panel_visible(False))
        header.addWidget(self.cart_panel_toggle)
        layout.addLayout(header)

        self.cart_scroll = QScrollArea()
        self.cart_scroll.setObjectName("SalesCartScrollArea")
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cart_items_host = QWidget()
        self.cart_items_layout = QVBoxLayout(self.cart_items_host)
        self.cart_items_layout.setContentsMargins(0, 0, 0, 0)
        self.cart_items_layout.setSpacing(8)
        self.cart_items_layout.addStretch(1)
        self.cart_scroll.setWidget(self.cart_items_host)
        layout.addWidget(self.cart_scroll, 1)

        self.clear_cart_button = QPushButton("خالی‌کردن سبد")
        self.clear_cart_button.setObjectName("DangerButton")
        self.clear_cart_button.clicked.connect(self.clear_cart)
        layout.addWidget(self.clear_cart_button)

        self.cart_empty_label = QLabel("سبد خالی است. از فهرست سمت راست کالا اضافه کنید.")
        self.cart_empty_label.setObjectName("PageSubtitle")
        self.cart_empty_label.setWordWrap(True)
        self.cart_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.insertWidget(1, self.cart_empty_label)
        return panel

    def _set_cart_panel_visible(self, visible):
        """Toggle the left cart without losing quantities or splitter proportions."""
        visible = bool(visible)
        if visible == self.cart_panel.isVisible():
            return
        if not visible:
            sizes = self.splitter.sizes()
            if len(sizes) == 2 and all(size > 0 for size in sizes):
                self._saved_splitter_sizes = sizes
            self.cart_panel.hide()
            self.show_cart_button.show()
        else:
            self.cart_panel.show()
            self.show_cart_button.hide()
            self.splitter.setSizes(self._saved_splitter_sizes or [780, 360])

    def set_permissions(self, user):
        self.history_button.setVisible(can_access(user, "receipts", "read"))

    def set_business_profile(self, profile):
        self._business_profile = dict(profile or {})
        self.seat_row.setVisible(
            self._business_profile.get("business_profile") == "cafe"
            or bool(self._business_profile.get("cafe_seat_selection"))
        )

    def _category_changed(self, *_args):
        self.product_page = 1
        self.refresh_products()

    def _toggle_product_images(self, enabled):
        self._show_product_images = bool(enabled)
        self._local_settings.setValue("sales/show_product_images", self._show_product_images)
        self._local_settings.sync()
        self._render_products() if not self.window.api else self.refresh_products()

    def refresh_products(self):
        """Load one API page plus categories and optional images on a worker thread."""
        if not self.window.api:
            return
        query = self.search.text().strip() or None
        category_id = self.category_combo.currentData()
        filters = (query, category_id)
        if filters != self._last_filters:
            self._last_filters = filters
            self.product_page = 1
        page = self.product_page
        include_images = self._show_product_images

        self.window.run_api(
            lambda: self._load_catalog_payload(query, category_id, page, include_images),
            self.populate,
            failure=self._products_load_failed,
            busy=self.refresh_button,
        )

    def _load_catalog_payload(self, query, category_id, page, include_images):
        """Fetch product metadata and image bytes away from the GUI thread."""
        api = self.window.api
        data = api.list_products_page(
            q=query, category_id=category_id, page=page, page_size=self.product_page_size
        )
        products = list(data.get("items") or [])
        if include_images:
            for product in products:
                if product.get("image_path"):
                    try:
                        product["_image_bytes"] = api.get_product_image_bytes(product["id"])
                    except Exception:
                        # A bad/missing image must not prevent the cashier from selling the item.
                        product["_image_bytes"] = None
        try:
            category_payload = api.list_categories_page(page=1, page_size=200)
            categories = list(category_payload.get("items") or [])
        except Exception:
            categories = []

        return {
            "items": products,
            "total": int(data.get("total", len(products))),
            "page": int(data.get("page", page)),
            "page_size": int(data.get("page_size", self.product_page_size)),
            "categories": categories,
        }

    def _update_pagination_controls(self):
        page_count = max(1, (self.total_products + self.product_page_size - 1) // self.product_page_size)
        self.product_page_label.setText(
            "صفحه {} از {} · {} کالا".format(self.product_page, page_count, self.total_products)
        )
        self.previous_page_button.setEnabled(self.product_page > 1)
        self.next_page_button.setEnabled(self.product_page < page_count)
        self.catalog_count_label.setText("{} کالا".format(self.total_products))

    def _products_load_failed(self, error):
        self.product_page = self._loaded_product_page
        self.window.show_error(error)
        self._update_pagination_controls()

    def _change_product_page(self, delta):
        page_count = max(1, (self.total_products + self.product_page_size - 1) // self.product_page_size)
        target = self.product_page + int(delta)
        if 1 <= target <= page_count and target != self.product_page:
            self.product_page = target
            self.refresh_products()

    def populate(self, payload):
        """Refresh the visible page while leaving the current cart untouched."""
        products = list(payload.get("items") or [])
        self.categories = list(payload.get("categories") or [])
        try:
            self.total_products = max(len(products), int(payload.get("total", len(products)) or 0))
        except (TypeError, ValueError):
            self.total_products = len(products)
        self.product_page = max(1, int(payload.get("page", self.product_page) or 1))
        self._loaded_product_page = self.product_page

        selected_category = self.category_combo.currentData()
        self._category_names = {
            str(category.get("id")): str(category.get("name") or "دسته‌بندی")
            for category in self.categories if category.get("id") is not None
        }
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("همهٔ دسته‌ها", None)
        for category in self.categories:
            self.category_combo.addItem(str(category.get("name") or "—"), category.get("id"))
        selected_index = self.category_combo.findData(selected_category)
        self.category_combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.category_combo.blockSignals(False)

        for product in products:
            key = str(product.get("id") or "")
            if not key:
                continue
            previous = self._product_cache.get(key, {})
            if "_image_bytes" not in product and previous.get("_image_bytes"):
                product["_image_bytes"] = previous["_image_bytes"]
            self._product_cache[key] = product
            if key in self._cart:
                self._cart[key]["product"] = product

        self.products = products
        self._render_products()
        self._update_pagination_controls()
        self._render_cart()
        self._refresh_cart_summary()

    def _render_products(self):
        """Rebuild only the visible product grid, adapting the number of columns."""
        width = max(260, self.catalog_scroll.viewport().width() if hasattr(self, "catalog_scroll") else 800)
        columns = max(1, min(5, width // 225))
        if not self.products:
            columns = max(1, columns)
        # Reflow only when the viewport's available column count changes or data changes.
        self._rendered_columns = columns
        self._product_add_buttons = {}
        while self.product_grid.count():
            item = self.product_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        if not self.products:
            empty = QLabel("کالایی مطابق فیلترها پیدا نشد.")
            empty.setObjectName("PageSubtitle")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.product_grid.addWidget(empty, 0, 0, 1, columns)
            self.product_grid.setRowStretch(1, 1)
            return

        for index, product in enumerate(self.products):
            card = self._build_product_card(product)
            self.product_grid.addWidget(card, index // columns, index % columns)
        self.product_grid.setRowStretch((len(self.products) // columns) + 1, 1)

    def _build_product_card(self, product):
        """Create a compact product card with optional photography and stock state."""
        key = str(product.get("id") or "")
        card = QFrame()
        card.setObjectName("SalesProductCard")
        card.setMinimumWidth(180)
        card.setMaximumWidth(340)
        card.setFrameShape(QFrame.Shape.NoFrame)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(7)

        if self._show_product_images:
            image = QLabel()
            image.setObjectName("SalesProductImage")
            image.setMinimumHeight(78)
            image.setMaximumHeight(112)
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap()
            image_bytes = product.get("_image_bytes")
            if image_bytes and pixmap.loadFromData(image_bytes):
                image.setPixmap(pixmap.scaled(
                    180, 102, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            else:
                image.setText("بدون تصویر")
            card_layout.addWidget(image)

        name = QLabel(str(product.get("name") or "کالای بدون نام"))
        name.setObjectName("SalesProductTitle")
        name.setWordWrap(True)
        name.setMinimumHeight(36)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(name)

        category_id = product.get("category_id")
        category_name = self._category_names.get(str(category_id), "")
        if category_name:
            category = QLabel(category_name)
            category.setObjectName("Muted")
            category.setAlignment(Qt.AlignmentFlag.AlignCenter)
            category.setWordWrap(True)
            card_layout.addWidget(category)

        price = QLabel("{:,.2f}".format(float(product.get("sell_price") or 0)))
        price.setObjectName("SalesProductPrice")
        price.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(price)

        tracked = bool(product.get("track_stock"))
        stock = float(product.get("stock_quantity") or 0)
        if tracked:
            available = max(0, stock - int(self._cart.get(key, {}).get("quantity", 0)))
            stock_text = "ناموجود" if available <= 0 else "موجودی: {:g}".format(available)
        else:
            available = None
            stock_text = "آماده فروش"
        stock_badge = QLabel(stock_text)
        stock_badge.setObjectName("SalesProductStock")
        stock_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stock_badge.setProperty("outOfStock", bool(tracked and available <= 0))
        card_layout.addWidget(stock_badge)

        add = QPushButton("افزودن به سبد")
        add.setObjectName("PrimaryButton")
        add.setMinimumHeight(38)
        add.setToolTip("افزودن {} به سبد خرید".format(product.get("name") or "کالا"))
        add.clicked.connect(lambda _checked=False, selected=product: self.add_to_cart(selected))
        add.setEnabled(not tracked or available > 0)
        set_button_icon(add, "cart", getattr(self.window, "mode", "light"))
        card_layout.addWidget(add)
        self._product_add_buttons[key] = add
        return card

    def _refresh_product_stock_states(self):
        """Synchronize stock badges and add-button states with selected quantities."""
        for product in self.products:
            key = str(product.get("id") or "")
            button = self._product_add_buttons.get(key)
            if button is None:
                continue
            tracked = bool(product.get("track_stock"))
            stock = float(product.get("stock_quantity") or 0)
            selected = int(self._cart.get(key, {}).get("quantity", 0))
            button.setEnabled(not tracked or selected < stock)

    def add_to_cart(self, product):
        """Add one unit, enforcing known stock limits without replacing server validation."""
        key = str(product.get("id") or "")
        if not key:
            return
        product = self._product_cache.get(key, product)
        current = int(self._cart.get(key, {}).get("quantity", 0))
        next_quantity = current + 1
        if product.get("track_stock") and next_quantity > int(float(product.get("stock_quantity") or 0)):
            QMessageBox.information(self, "موجودی کافی نیست", "تعداد انتخاب‌شده از موجودی فعلی بیشتر است.")
            return
        self._cart[key] = {"product": product, "quantity": next_quantity}
        self._render_cart()
        self._refresh_cart_summary()
        self._refresh_product_stock_states()

    def _set_cart_quantity(self, product_key, quantity):
        quantity = max(0, int(quantity))
        entry = self._cart.get(product_key)
        if not entry:
            return
        product = entry["product"]
        if product.get("track_stock"):
            stock = int(float(product.get("stock_quantity") or 0))
            if quantity > stock:
                quantity = stock
        if quantity <= 0:
            self._cart.pop(product_key, None)
            self._render_cart()
        else:
            entry["quantity"] = quantity
            self._refresh_cart_summary()
            self._refresh_product_stock_states()

    def _remove_cart_item(self, product_key):
        self._cart.pop(product_key, None)
        self._render_cart()
        self._refresh_cart_summary()
        self._refresh_product_stock_states()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _render_cart(self):
        """Render selected products separately from the currently visible catalog page."""
        while self.cart_items_layout.count():
            item = self.cart_items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        self.cart_empty_label.setVisible(not self._cart)
        for key, entry in self._cart.items():
            product = entry["product"]
            quantity = int(entry["quantity"])
            card = QFrame()
            card.setObjectName("SalesCartItem")
            row_layout = QVBoxLayout(card)
            row_layout.setContentsMargins(10, 8, 10, 8)
            row_layout.setSpacing(6)

            title_row = QHBoxLayout()
            title = QLabel(str(product.get("name") or "کالا"))
            title.setObjectName("SalesCartItemTitle")
            title.setWordWrap(True)
            remove = QPushButton("حذف")
            remove.setObjectName("DangerButton")
            remove.setToolTip("حذف این کالا از سبد")
            remove.clicked.connect(lambda _checked=False, item_key=key: self._remove_cart_item(item_key))
            set_button_icon(remove, "delete", getattr(self.window, "mode", "light"))
            title_row.addWidget(title, 1)
            title_row.addWidget(remove)
            row_layout.addLayout(title_row)

            price = float(product.get("sell_price") or 0)
            unit_price = QLabel("هر واحد: {:,.2f}".format(price))
            unit_price.setObjectName("PageSubtitle")
            row_layout.addWidget(unit_price)

            quantity_row = QHBoxLayout()
            quantity_label = QLabel("تعداد")
            quantity_label.setObjectName("PageSubtitle")
            quantity_spin = QSpinBox()
            quantity_spin.setMinimum(0)
            quantity_spin.setMaximum(
                max(0, int(float(product.get("stock_quantity") or 0)))
                if product.get("track_stock") else 100000
            )
            quantity_spin.setValue(quantity)
            quantity_spin.valueChanged.connect(
                lambda value, item_key=key: self._set_cart_quantity(item_key, value)
            )
            line_total = QLabel("مجموع: {:,.2f}".format(price * quantity))
            line_total.setObjectName("SalesCartLineTotal")
            quantity_row.addWidget(quantity_label)
            quantity_row.addWidget(quantity_spin)
            quantity_row.addStretch(1)
            quantity_row.addWidget(line_total)
            row_layout.addLayout(quantity_row)

            self.cart_items_layout.addWidget(card)
        self.cart_items_layout.addStretch(1)
        self._refresh_cart_summary()

    def _refresh_cart_summary(self):
        total = 0.0
        item_kinds = len(self._cart)
        units = 0
        for entry in self._cart.values():
            product = entry["product"]
            quantity = int(entry["quantity"])
            units += quantity
            try:
                total += float(product.get("sell_price") or 0) * quantity
            except (TypeError, ValueError):
                continue
        self.total_label.setText("جمع تخمینی: {:,.2f}".format(total))
        self.cart_status_label.setText("{} نوع · {} عدد".format(item_kinds, units))
        self.clear_cart_button.setEnabled(bool(item_kinds))
        self.submit_button.setEnabled(bool(item_kinds))

    def clear_cart(self):
        self._cart.clear()
        self._render_cart()
        self._refresh_product_stock_states()

    def collect_items(self):
        """Build the checkout payload independently of catalog filters and pagination."""
        output = []
        for key, entry in self._cart.items():
            quantity = int(entry.get("quantity") or 0)
            if quantity <= 0:
                continue
            product = entry.get("product") or self._product_cache.get(key, {})
            product_id = product.get("id", key)
            output.append({"product_id": product_id, "quantity": quantity})
        return output

    def update_estimate(self, *_):
        # Keep this compatibility method for callers that previously connected a table signal.
        self._refresh_cart_summary()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "catalog_scroll"):
            return
        width = self.catalog_scroll.viewport().width()
        columns = max(1, min(5, max(260, width) // 225))
        if columns != self._rendered_columns:
            self._rendered_columns = columns
            self._render_products()

    def checkout(self):
        items=self.collect_items()
        if not items:
            self.window.show_error("برای ثبت فروش حداقل یک تعداد مثبت وارد کنید.");return
        answer=QMessageBox.question(self,"تأیید فروش",
            "فروش با {} نوع کالا ثبت شود؟ مبلغ نهایی در سرور محاسبه می‌شود.".format(len(items)),
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.Yes)
        if answer!=QMessageBox.StandardButton.Yes:return
        paid = self.paid.isChecked()
        seat_number = self.seat_number.currentData() if self.seat_row.isVisible() else None
        if self.seat_row.isVisible() and not seat_number:
            self.window.show_error("برای فروش کافه، شماره صندلی یا میز را انتخاب کنید.")
            self.seat_number.setFocus()
            return
        settings = device_settings()
        if paid and settings.get("terminal_mode") == "tcp":
            self.window.run_api(
                lambda: self._checkout_via_terminal(items, settings),
                self._terminal_sale_created,
                busy=self.submit_button,
            )
        else:
            self.window.run_api(
                lambda: self.window.api.create_sale(items, paid=paid, seat_number=seat_number),
                self._sale_created,
                busy=self.submit_button,
            )

    def _checkout_via_terminal(self, items, settings, seat_number=None):
        quote = self.window.api.quote_sale(items, paid=True, payment_method="card", seat_number=seat_number)
        amount = str(quote.get("total") or "0")
        reference = uuid.uuid4().hex
        payment = authorize_payment(amount, reference, settings)
        try:
            receipt = self.window.api.create_sale(
                items, paid=True, idempotency_key=reference, payment_method="card",
                seat_number=seat_number,
            )
        except Exception as first_error:
            try:
                receipt = self.window.api.create_sale(
                    items, paid=True, idempotency_key=reference, payment_method="card",
                    seat_number=seat_number,
                )
            except Exception as retry_error:
                try:
                    void_payment(amount, reference, payment["transaction_id"], settings)
                except Exception as void_error:
                    raise RuntimeError(
                        "کارت‌خوان تراکنش را تأیید کرده اما ثبت فروش/لغو نامشخص است. "
                        "شناسه تراکنش {} و مرجع {} را با مدیر/پرداخت‌یار بررسی کنید. خطا: {}؛ {}".format(
                            payment["transaction_id"], reference, retry_error, void_error
                        )
                    ) from retry_error
                raise RuntimeError(
                    "ثبت فروش ناموفق بود و لغو وجه تأیید شد؛ مرجع {}. {}".format(reference, retry_error)
                ) from first_error
        return {"receipt": receipt, "transaction_id": payment["transaction_id"]}

    def _terminal_sale_created(self, result):
        receipt = result["receipt"]
        self.window.set_status(
            "پرداخت کارت‌خوان تأیید شد · شناسه تراکنش {}".format(result.get("transaction_id", "—"))
        )
        self._sale_created(receipt)

    def _sale_created(self, receipt):
        self.paid.setChecked(False)
        self.seat_number.setCurrentIndex(0)
        self._cart.clear()
        self._render_cart()
        self._refresh_product_stock_states()
        self._refresh_cart_summary()
        self.window.set_status(
            "فروش شمارهٔ {} با مبلغ {:,.2f} ثبت شد.".format(
                receipt.get("day_receipt_id", "—"), float(receipt.get("total_price") or 0)
            )
        )
        self.refresh_products()
        refresh_dashboard = getattr(self.window, "refresh_dashboard_data", None)
        if callable(refresh_dashboard):
            refresh_dashboard()
        receipts_page = getattr(self.window, "receipts_page", None)
        if receipts_page is not None:
            receipts_page.refresh()
        if self.window.api:
            self.window.run_api(
                lambda: self.window.api.get_invoice_template(kind="pos_receipt"),
                lambda template: self._present_invoice(receipt, template),
                failure=lambda _error: self._present_invoice(receipt, DEFAULT_TEMPLATE),
            )
        else:
            self._present_invoice(receipt, DEFAULT_TEMPLATE)

    def _present_invoice(self, receipt, template):
        auto_print_invoice(receipt, template, self.window)
        InvoiceDialog(receipt, template, self.window).exec()

    def show_recent_receipts(self):
        if not self.window.api:
            return
        hours = int((getattr(self.window, "company_profile", None) or {}).get("receipt_history_hours", 48))
        from PySide6.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView
        dialog = QDialog(self)
        dialog.setWindowTitle("فاکتورهای اخیر")
        dialog.resize(980, 580)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(dialog)
        title = QLabel("فاکتورهای {} ساعت اخیر".format(hours))
        title.setObjectName("PageTitle")
        hint = QLabel("فاکتورهای پرداخت‌نشده با رنگ قرمز علامت‌گذاری شده‌اند. این فهرست بر اساس بازه تنظیم‌شده در پنل مدیریت محدود است.")
        hint.setObjectName("PageSubtitle")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["شناسه", "وضعیت پرداخت", "تاریخ", "صندلی / میز", "مبلغ", "روش پرداخت"])
        table.setColumnHidden(0, True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(table, 1)
        footer = QHBoxLayout()
        status = QLabel("")
        status.setObjectName("PageSubtitle")
        open_button = QPushButton("نمایش و چاپ فاکتور")
        open_button.setObjectName("PrimaryButton")
        close_button = QPushButton("بستن")
        footer.addWidget(status, 1)
        footer.addWidget(open_button)
        footer.addWidget(close_button)
        root.addLayout(footer)
        close_button.clicked.connect(dialog.reject)

        def populate(payload):
            records = list(payload.get("items") or [])
            table.setRowCount(0)
            for row, item in enumerate(records):
                table.insertRow(row)
                paid = bool(item.get("payed"))
                created_at = str(item.get("created_at") or "—").replace("T", " ")[:19]
                values = [
                    str(item.get("id") or ""),
                    "پرداخت‌شده" if paid else "پرداخت‌نشده",
                    created_at,
                    str(item.get("seat_number") or "—"),
                    "{:,.2f}".format(float(item.get("total_price") or 0)),
                    str(item.get("payment_method") or "—"),
                ]
                for col, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    if col == 0:
                        cell.setData(Qt.ItemDataRole.UserRole, item)
                    if not paid:
                        cell.setBackground(QBrush(QColor("#FCE8E6")))
                        cell.setForeground(QBrush(QColor("#9B1C1C")))
                    table.setItem(row, col, cell)
            status.setText("{} فاکتور · {} مورد پرداخت‌نشده".format(
                len(records), sum(not bool(item.get("payed")) for item in records)
            ))

        def open_selected():
            row = table.currentRow()
            cell = table.item(row, 0) if row >= 0 else None
            record = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if not record:
                QMessageBox.information(dialog, "انتخاب فاکتور", "ابتدا یک فاکتور را انتخاب کنید.")
                return
            self.window.run_api(
                lambda: self._load_recent_invoice(record["id"]),
                lambda result: self._show_recent_invoice(result, dialog),
            )

        open_button.clicked.connect(open_selected)
        table.cellDoubleClicked.connect(lambda _row, _column: open_selected())
        dialog.setMinimumSize(760, 460)
        self.window.run_api(
            self.window.api.list_recent_receipts_page,
            populate,
            failure=lambda error: QMessageBox.warning(dialog, "خطای دریافت فاکتورها", str(error)),
        )
        apply_button_icons(dialog, getattr(self.window, "mode", "light"))
        dialog.exec()

    def _load_recent_invoice(self, receipt_id):
        receipt = self.window.api.get_receipt(receipt_id)
        try:
            template = self.window.api.get_invoice_template()
        except Exception:
            template = DEFAULT_TEMPLATE
        return {"receipt": receipt, "template": template}

    def _show_recent_invoice(self, payload, dialog):
        InvoiceDialog(payload["receipt"], payload.get("template") or DEFAULT_TEMPLATE, self.window).exec()
