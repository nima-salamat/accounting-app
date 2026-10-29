"""API-driven point-of-sale screen with search, quantity selection, and idempotent checkout."""
from PySide6.QtCore import Qt, QSettings, QTimer, QEvent, QPoint
from PySide6.QtGui import QColor, QBrush, QPixmap, QIcon
import uuid

from client.payment_terminal import authorize_payment, void_payment
from client.ui.device_settings import device_settings
from client.ui.invoice_dialog import InvoiceDialog, auto_print_invoice
from client.ui.invoice_render import DEFAULT_TEMPLATE
from client.ui.permissions import can_access
from client.ui.icons import apply_button_icons, set_button_icon

from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHeaderView, QWidget, QListWidget, QListWidgetItem,
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
        self._product_stock_labels = {}
        self._cart_line_total_labels = {}
        self._cart_quantity_labels = {}
        self._cart_plus_buttons = {}
        self._cart_minus_buttons = {}
        self._category_names = {}
        self._rendered_columns = 0
        self._business_profile = {}
        self._is_standalone_pos = bool(getattr(window, "standalone_pos", False))
        self._editing_receipt_id = None
        self._editing_receipt = None
        self._can_edit_receipts = False

        self._suggestion_query = ""
        self._suggestion_page = 0
        self._suggestion_page_size = 8
        self._suggestion_total = 0
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(280)
        self._search_timer.timeout.connect(self._run_search_suggestions)

        self._local_settings = QSettings(
            "AccountingApp", "POSClient" if self._is_standalone_pos else "DesktopClient"
        )
        saved_sizes = self._local_settings.value("sales/splitter_sizes", [780, 360])
        try:
            self._saved_splitter_sizes = [max(1, int(saved_sizes[0])), max(1, int(saved_sizes[1]))]
        except (TypeError, ValueError, IndexError):
            self._saved_splitter_sizes = [780, 360]
        self._show_product_images = self._local_settings.value(
            "sales/show_product_images", True, type=bool
        )
        self._product_layout_mode = str(
            self._local_settings.value("sales/product_layout_mode", "grid") or "grid"
        ).strip().lower()
        if self._product_layout_mode not in {"grid", "horizontal", "list", "table"}:
            self._product_layout_mode = "grid"
        self._product_card_density = str(
            self._local_settings.value("sales/product_card_density", "comfortable") or "comfortable"
        ).strip().lower()
        if self._product_card_density not in {"compact", "comfortable"}:
            self._product_card_density = "comfortable"
        try:
            self._product_columns = max(0, min(6, int(
                self._local_settings.value("sales/product_columns", 0) or 0
            )))
        except (TypeError, ValueError):
            self._product_columns = 0

        self.setObjectName("POSWorkspace" if self._is_standalone_pos else "Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        if self._is_standalone_pos:
            root.setContentsMargins(6, 6, 6, 6)
        else:
            root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # The host window already identifies the sales screen. Keep every action
        # in one compact toolbar; never render a second page title here.
        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 0)
        header.setSpacing(6)
        self.header_layout = header

        self.theme_button = QPushButton("☾ تم تاریک")
        self.theme_button.setObjectName("SalesToolbarButton")
        self.theme_button.setToolTip("تم برنامه از نوار ابزار اصلی کنترل می‌شود")
        self.theme_button.clicked.connect(self._toggle_theme)
        self.theme_button.hide()

        self.cancel_edit_button = QPushButton("لغو ویرایش")
        self.cancel_edit_button.setObjectName("SalesToolbarButton")
        self.cancel_edit_button.setToolTip("لغو ویرایش و بازگشت به فروش جدید")
        self.cancel_edit_button.clicked.connect(self.cancel_invoice_edit)
        self.cancel_edit_button.hide()
        header.addWidget(self.cancel_edit_button)

        self.refresh_button = QPushButton("بازخوانی")
        self.refresh_button.setObjectName("SalesToolbarButton")
        self.refresh_button.setToolTip("بازخوانی کالاها")
        self.refresh_button.clicked.connect(self.refresh_products)
        header.addWidget(self.refresh_button)

        self.history_button = QPushButton("فاکتورهای اخیر")
        self.history_button.setObjectName("SalesToolbarButton")
        self.history_button.clicked.connect(self.show_recent_receipts)
        header.addWidget(self.history_button)

        self.show_cart_button = QPushButton("سبد")
        self.show_cart_button.setObjectName("SalesToolbarButton")
        self.show_cart_button.setToolTip("نمایش پنل سبد خرید")
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
        self.splitter.splitterMoved.connect(self._splitter_moved)
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
        self.paid.toggled.connect(self._payment_status_changed)
        self.payment_method_label = QLabel("روش پرداخت")
        self.payment_method_label.setObjectName("PageSubtitle")
        self.payment_method_combo = QComboBox()
        for label, value in (
            ("نقدی", "cash"),
            ("کارت", "card"),
            ("انتقال بانکی", "bank_transfer"),
            ("اعتباری", "store_credit"),
        ):
            self.payment_method_combo.addItem(label, value)
        self.payment_method_combo.setMinimumWidth(118)
        self.payment_method_combo.setEnabled(False)
        self.total_label = QLabel("جمع تخمینی: —")
        self.total_label.setObjectName("MetricValue")
        self.submit_button = QPushButton("ثبت امن فروش")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.clicked.connect(self.checkout)
        footer.addWidget(self.paid)
        footer.addWidget(self.payment_method_label)
        footer.addWidget(self.payment_method_combo)
        footer.addStretch(1)
        footer.addWidget(self.total_label)
        footer.addWidget(self.submit_button)
        root.addWidget(footer_card)

        self._refresh_cart_summary()
        self._update_invoice_mode_controls()
        self.sync_theme_button()
        apply_button_icons(self, getattr(self.window, "mode", "light"))
        self.sync_theme_button()

    def _build_catalog_panel(self):
        """Build the searchable, category-filtered product grid shown on the right."""
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(300)
        panel.installEventFilter(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(9, 9, 9, 9)
        layout.setSpacing(7)

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
        self.search.installEventFilter(self)
        self.search.returnPressed.connect(self.refresh_products)
        self.search_button = QPushButton("جست‌وجو")
        self.search_button.setToolTip("جست‌وجوی کالا")
        self.search_button.clicked.connect(self.refresh_products)
        self.search.textChanged.connect(self._search_text_changed)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.search_button)
        layout.addLayout(filters)

        # Suggestions are a floating overlay attached to the catalog panel, not a
        # row in the main layout: opening search results must never move the catalog.
        self.search_suggestions_frame = QFrame(panel)
        self.search_suggestions_frame.setObjectName("SalesSearchSuggestions")
        self.search_suggestions_frame.setMinimumWidth(260)
        self.search_suggestions_frame.setMaximumHeight(270)
        suggestions_layout = QVBoxLayout(self.search_suggestions_frame)
        suggestions_layout.setContentsMargins(8, 6, 8, 6)
        suggestions_layout.setSpacing(4)
        self.search_suggestion_list = QListWidget()
        self.search_suggestion_list.setObjectName("SalesSearchSuggestionList")
        self.search_suggestion_list.setMaximumHeight(188)
        self.search_suggestion_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.search_suggestion_list.itemClicked.connect(self._add_suggestion_to_cart)
        suggestions_layout.addWidget(self.search_suggestion_list)
        suggestion_footer = QHBoxLayout()
        self.search_suggestion_status = QLabel("")
        self.search_suggestion_status.setObjectName("PageSubtitle")
        self.search_more_button = QPushButton("▾ بارگذاری بیشتر")
        self.search_more_button.setToolTip("نمایش موارد مشابه بیشتر")
        self.search_more_button.clicked.connect(self._load_more_search_suggestions)
        self.search_more_button.hide()
        suggestion_footer.addWidget(self.search_suggestion_status, 1)
        suggestion_footer.addWidget(self.search_more_button)
        suggestions_layout.addLayout(suggestion_footer)
        self.search_suggestions_frame.hide()

        options = QHBoxLayout()
        category_label = QLabel("دسته‌بندی")
        category_label.setObjectName("PageSubtitle")
        self.category_combo = QComboBox()
        self.category_combo.setMinimumWidth(150)
        self.category_combo.addItem("همهٔ دسته‌ها", None)
        self.category_combo.currentIndexChanged.connect(self._category_changed)
        self.product_display_settings_button = QPushButton("⚙")
        self.product_display_settings_button.setObjectName("SalesDisplaySettingsButton")
        self.product_display_settings_button.setToolTip("تنظیمات و پیش‌نمایش نمایش کالاها")
        self.product_display_settings_button.setAccessibleName("تنظیمات نمایش کالاها")
        self.product_display_settings_button.setFixedSize(36, 36)
        self.product_display_settings_button.clicked.connect(self.open_product_display_settings)
        options.addWidget(category_label)
        options.addWidget(self.category_combo, 1)
        options.addWidget(self.product_display_settings_button)
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
        self.catalog_scroll.viewport().installEventFilter(self)

        self.catalog_results_stack = QStackedWidget()
        self.catalog_results_stack.setObjectName("SalesCatalogResults")
        self.catalog_results_stack.addWidget(self.catalog_scroll)

        self.product_table = QTableWidget(0, 6)
        self.product_table.setObjectName("SalesProductTable")
        self.product_table.setHorizontalHeaderLabels(["تصویر", "نام کالا", "دسته‌بندی", "قیمت", "موجودی", ""])
        self.product_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.product_table.setAlternatingRowColors(True)
        self.product_table.setWordWrap(False)
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.product_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.product_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.product_table.setShowGrid(False)
        self.product_table.setSortingEnabled(False)
        table_header = self.product_table.horizontalHeader()
        table_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4, 5):
            table_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.product_table.doubleClicked.connect(self._add_table_selection_to_cart)
        self.catalog_results_stack.addWidget(self.product_table)
        layout.addWidget(self.catalog_results_stack, 1)

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
        set_button_icon(self.cart_panel_toggle, "minus", getattr(self.window, "mode", "light"))
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
        currently_visible = not self.cart_panel.isHidden()
        if visible == currently_visible:
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
        self._can_edit_receipts = can_access(user, "sales", "update")

    def set_business_profile(self, profile):
        self._business_profile = dict(profile or {})
        self.seat_row.setVisible(
            self._business_profile.get("business_profile") == "cafe"
            or bool(self._business_profile.get("cafe_seat_selection"))
        )

    def _toggle_theme(self):
        change_theme = getattr(self.window, "change_theme", None)
        if callable(change_theme):
            change_theme("dark" if getattr(self.window, "mode", "light") == "light" else "light")
        self.sync_theme_button()

    def sync_theme_button(self):
        mode = getattr(self.window, "mode", "light")
        self.theme_button.setText("☾ تم تاریک" if mode == "light" else "☀ تم روشن")
        self.theme_button.setToolTip("تم برنامه از نوار ابزار اصلی کنترل می‌شود")
        self.theme_button.hide()

    def _payment_status_changed(self, paid):
        self.payment_method_combo.setEnabled(bool(paid))

    def _update_invoice_mode_controls(self):
        editing = self._editing_receipt_id is not None
        if editing:
            receipt_number = (
                (self._editing_receipt or {}).get("day_receipt_id")
                or str(self._editing_receipt_id)[:8]
            )
            self.submit_button.setText("ذخیرهٔ تغییرات فاکتور")
            self.cancel_edit_button.show()
        else:
            self.submit_button.setText("ثبت امن فروش")
            self.cancel_edit_button.hide()

    def cancel_invoice_edit(self):
        self._editing_receipt_id = None
        self._editing_receipt = None
        self._cart.clear()
        self.paid.setChecked(False)
        cash_index = self.payment_method_combo.findData("cash")
        if cash_index >= 0:
            self.payment_method_combo.setCurrentIndex(cash_index)
        self.seat_number.setCurrentIndex(0)
        self._render_cart()
        self._refresh_cart_summary()
        self._refresh_product_stock_states()
        self._update_invoice_mode_controls()
        self.window.set_status("ویرایش فاکتور لغو شد؛ آماده ثبت فروش جدید هستید.")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            if watched is getattr(self, "catalog_panel", None) or watched is getattr(self, "search", None):
                QTimer.singleShot(0, self._position_search_suggestions)
            elif watched is getattr(getattr(self, "catalog_scroll", None), "viewport", lambda: None)():
                QTimer.singleShot(0, self._reflow_products_for_resize)
        return super().eventFilter(watched, event)

    def _position_search_suggestions(self):
        """Anchor search results below the input as an overlay over the catalog."""
        if not hasattr(self, "search_suggestions_frame") or not hasattr(self, "search"):
            return
        if self.search_suggestions_frame.parentWidget() is not self.catalog_panel:
            return
        top_left = self.search.mapTo(
            self.catalog_panel, QPoint(0, self.search.height() + 4)
        )
        available_height = max(110, self.catalog_panel.height() - top_left.y() - 50)
        height = min(270, available_height)
        self.search_suggestions_frame.setGeometry(
            9, top_left.y(), max(260, self.catalog_panel.width() - 18), height
        )

    def _reflow_products_for_resize(self):
        if not getattr(self, "products", None) or self._product_layout_mode != "grid":
            return
        width = max(260, self.catalog_scroll.viewport().width())
        columns = max(1, min(6, self._product_columns or width // 165))
        if columns != self._rendered_columns:
            self._render_products()

    def _search_text_changed(self, value):
        self._search_timer.stop()
        query = str(value or "").strip()
        self._suggestion_query = query
        self._suggestion_page = 0
        self._suggestion_total = 0
        self.search_suggestion_list.clear()
        self.search_more_button.hide()
        if len(query) < 2 or not self.window.api:
            self.search_suggestions_frame.hide()
            return
        self._position_search_suggestions()
        self.search_suggestions_frame.show()
        self.search_suggestions_frame.raise_()
        self.search_suggestion_status.setText("در حال جست‌وجوی نام‌های مشابه…")
        self._search_timer.start()

    def _run_search_suggestions(self):
        query = self.search.text().strip()
        if len(query) >= 2:
            self._request_search_suggestions(query, 1)

    def _request_search_suggestions(self, query, page):
        if not self.window.api or query != self.search.text().strip():
            return
        self.search_suggestion_status.setText("در حال بارگذاری نتایج…")
        self.search_more_button.setEnabled(False)
        self.window.run_api(
            lambda: self.window.api.list_products_page(
                q=query,
                category_id=self.category_combo.currentData(),
                page=page,
                page_size=self._suggestion_page_size,
            ),
            lambda payload: self._show_search_suggestions(payload, query, page),
            failure=lambda error: self._search_suggestions_failed(error, query),
        )

    def _show_search_suggestions(self, payload, query, page):
        self.search_more_button.setEnabled(True)
        if query != self.search.text().strip():
            return
        items = list(payload.get("items") or [])
        if page == 1:
            self.search_suggestion_list.clear()
        for product in items:
            key = str(product.get("id") or "")
            if not key:
                continue
            previous = self._product_cache.get(key, {})
            if "_image_bytes" in previous and "_image_bytes" not in product:
                product["_image_bytes"] = previous["_image_bytes"]
            self._product_cache[key] = product
            row = QListWidgetItem(
                "{}   ·   {:,.2f}".format(
                    product.get("name") or "کالای بدون نام",
                    float(product.get("sell_price") or 0),
                )
            )
            row.setData(Qt.ItemDataRole.UserRole, product)
            row.setToolTip("برای افزودن سریع این کالا به سبد کلیک کنید.")
            self.search_suggestion_list.addItem(row)
        try:
            self._suggestion_total = max(0, int(payload.get("total", len(items)) or 0))
        except (TypeError, ValueError):
            self._suggestion_total = len(items)
        self._suggestion_page = page
        displayed = self.search_suggestion_list.count()
        self.search_suggestion_status.setText(
            "{} نتیجه · {} مورد نمایش داده شده".format(self._suggestion_total, displayed)
        )
        if displayed == 0:
            self.search_suggestion_status.setText("مورد مشابهی پیدا نشد.")
        self.search_more_button.setVisible(displayed < self._suggestion_total)
        self._position_search_suggestions()
        self.search_suggestions_frame.setVisible(True)
        self.search_suggestions_frame.raise_()

    def _search_suggestions_failed(self, error, query):
        self.search_more_button.setEnabled(True)
        if query == self.search.text().strip():
            self.search_suggestion_status.setText("بارگذاری پیشنهادهای جست‌وجو ناموفق بود.")
            self.search_more_button.hide()

    def _load_more_search_suggestions(self):
        if not self._suggestion_query or self._suggestion_page < 1:
            return
        if self.search_more_button.isEnabled() and (
            self.search_suggestion_list.count() < self._suggestion_total
        ):
            self._request_search_suggestions(
                self._suggestion_query, self._suggestion_page + 1
            )

    def _add_suggestion_to_cart(self, item):
        product = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(product, dict):
            self.add_to_cart(product)
        self.search_suggestions_frame.hide()

    def _add_table_selection_to_cart(self, index):
        if not index.isValid():
            return
        item = self.product_table.item(index.row(), 1)
        product = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(product, dict):
            self.add_to_cart(product)

    def _category_changed(self, *_args):
        self.product_page = 1
        self.refresh_products()
        query = self.search.text().strip()
        if len(query) >= 2:
            self._search_text_changed(query)

    def _toggle_product_images(self, enabled):
        self._apply_product_display_settings(
            self._product_layout_mode, bool(enabled), self._product_card_density,
            self._product_columns,
        )

    def open_product_display_settings(self):
        """Open the POS display preferences with a live preview of the selected style."""
        dialog = QDialog(self.window)
        dialog.setObjectName("ProductDisplaySettingsDialog")
        dialog.setWindowTitle("تنظیمات نمایش کالاها")
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setMinimumSize(560, 520)
        dialog.resize(680, 590)
        root = QVBoxLayout(dialog)
        intro = QLabel("چیدمان کارت کالاها را انتخاب کنید؛ پیش‌نمایش با تغییر گزینه‌ها به‌روز می‌شود.")
        intro.setObjectName("PageSubtitle")
        intro.setWordWrap(True)
        root.addWidget(intro)

        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(9)
        mode_label = QLabel("شیوهٔ نمایش")
        mode_combo = QComboBox()
        for label, value in (
            ("کارت شبکه‌ای", "grid"),
            ("کارت افقی؛ تصویر کنار متن", "horizontal"),
            ("فهرست خطی و فشرده", "list"),
            ("جدول کالاها", "table"),
        ):
            mode_combo.addItem(label, value)
        mode_index = mode_combo.findData(self._product_layout_mode)
        mode_combo.setCurrentIndex(max(0, mode_index))

        image_checkbox = QCheckBox("نمایش تصویر کالا")
        image_checkbox.setChecked(self._show_product_images)
        density_label = QLabel("تراکم کارت")
        density_combo = QComboBox()
        density_combo.addItem("معمولی", "comfortable")
        density_combo.addItem("فشرده", "compact")
        density_combo.setCurrentIndex(max(0, density_combo.findData(self._product_card_density)))
        columns_label = QLabel("تعداد ستون‌ها در حالت شبکه‌ای")
        columns_combo = QComboBox()
        for label, value in (
            ("خودکار بر اساس عرض پنجره", 0),
            ("۲ ستون", 2),
            ("۳ ستون", 3),
            ("۴ ستون", 4),
            ("۵ ستون", 5),
            ("۶ ستون", 6),
        ):
            columns_combo.addItem(label, value)
        columns_index = columns_combo.findData(self._product_columns)
        columns_combo.setCurrentIndex(max(0, columns_index))

        controls.addWidget(mode_label, 0, 0)
        controls.addWidget(mode_combo, 0, 1)
        controls.addWidget(image_checkbox, 1, 0, 1, 2)
        controls.addWidget(density_label, 2, 0)
        controls.addWidget(density_combo, 2, 1)
        controls.addWidget(columns_label, 3, 0)
        controls.addWidget(columns_combo, 3, 1)
        root.addLayout(controls)

        preview_title = QLabel("پیش‌نمایش")
        preview_title.setObjectName("PageTitle")
        root.addWidget(preview_title)
        preview_frame = QFrame()
        preview_frame.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        root.addWidget(preview_frame, 1)

        sample = next(iter(self.products), None)
        if sample is None:
            sample = {
                "id": "__display-preview__", "name": "نمونهٔ کالا",
                "sell_price": 125000, "category_id": None, "track_stock": True,
                "stock_quantity": 7, "_image_bytes": None,
            }
        else:
            sample = dict(sample)

        def rebuild_preview(*_args):
            self._clear_layout(preview_layout)
            mode = mode_combo.currentData()
            if mode == "table":
                table_preview = QTableWidget(1, 4)
                table_preview.setObjectName("SalesProductTable")
                table_preview.setHorizontalHeaderLabels(["نام کالا", "قیمت", "موجودی", ""])
                table_preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                table_preview.verticalHeader().setVisible(False)
                table_preview.horizontalHeader().setSectionResizeMode(
                    0, QHeaderView.ResizeMode.Stretch
                )
                for column in (1, 2, 3):
                    table_preview.horizontalHeader().setSectionResizeMode(
                        column, QHeaderView.ResizeMode.ResizeToContents
                    )
                table_preview.setRowCount(1)
                table_preview.setItem(0, 0, QTableWidgetItem(str(sample.get("name") or "نمونهٔ کالا")))
                table_preview.setItem(0, 1, QTableWidgetItem("{:,.2f}".format(float(sample.get("sell_price") or 0))))
                table_preview.setItem(0, 2, QTableWidgetItem("موجودی: ۷"))
                table_preview.setItem(0, 3, QTableWidgetItem("افزودن"))
                table_preview.setFixedHeight(90)
                preview_layout.addWidget(table_preview)
                return
            card = self._build_product_card(
                sample, preview=True, layout_mode=mode,
                show_images=image_checkbox.isChecked(),
                density=density_combo.currentData(),
            )
            preview_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)

        mode_combo.currentIndexChanged.connect(rebuild_preview)
        image_checkbox.toggled.connect(rebuild_preview)
        density_combo.currentIndexChanged.connect(rebuild_preview)
        columns_combo.currentIndexChanged.connect(rebuild_preview)
        rebuild_preview()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("اعمال تنظیمات")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("انصراف")
        root.addWidget(buttons)

        def apply_settings():
            self._apply_product_display_settings(
                mode_combo.currentData(), image_checkbox.isChecked(),
                density_combo.currentData(), columns_combo.currentData(),
            )
            dialog.accept()

        buttons.accepted.connect(apply_settings)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def _apply_product_display_settings(self, layout_mode, show_images, density, columns):
        layout_mode = str(layout_mode or "grid").strip().lower()
        if layout_mode not in {"grid", "horizontal", "list", "table"}:
            layout_mode = "grid"
        density = str(density or "comfortable").strip().lower()
        if density not in {"compact", "comfortable"}:
            density = "comfortable"
        try:
            columns = max(0, min(6, int(columns or 0)))
        except (TypeError, ValueError):
            columns = 0

        self._product_layout_mode = layout_mode
        self._show_product_images = bool(show_images)
        self._product_card_density = density
        self._product_columns = columns
        self._local_settings.setValue("sales/product_layout_mode", layout_mode)
        self._local_settings.setValue("sales/show_product_images", self._show_product_images)
        self._local_settings.setValue("sales/product_card_density", density)
        self._local_settings.setValue("sales/product_columns", columns)
        self._local_settings.sync()
        if self.window.api:
            self.refresh_products()
        else:
            self._render_products()

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
        """Render the chosen catalog presentation and adapt grid columns to its width."""
        self._product_add_buttons = {}
        self._product_stock_labels = {}
        if self._product_layout_mode == "table":
            self.catalog_results_stack.setCurrentWidget(self.product_table)
            self._render_product_table()
            self._rendered_columns = 0
            return

        self.catalog_results_stack.setCurrentWidget(self.catalog_scroll)
        width = max(260, self.catalog_scroll.viewport().width())
        if self._product_layout_mode in {"horizontal", "list"}:
            columns = 1
        else:
            columns = max(1, min(6, self._product_columns or width // 165))
        self._rendered_columns = columns
        self.product_grid.setHorizontalSpacing(6 if self._product_card_density == "compact" else 10)
        self.product_grid.setVerticalSpacing(6 if self._product_card_density == "compact" else 10)
        for row in range(max(2, len(self.products) // columns + 3)):
            self.product_grid.setRowStretch(row, 0)
        for column in range(6):
            self.product_grid.setColumnStretch(column, 0)
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

    def _render_product_table(self):
        """Render products as an accessible, selectable table with direct add actions."""
        table = self.product_table
        table.clearSpans()
        table.clearContents()
        table.setRowCount(len(self.products) if self.products else 1)
        table.setColumnHidden(0, not self._show_product_images)
        if not self.products:
            empty = QTableWidgetItem("کالایی مطابق فیلترها پیدا نشد.")
            empty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(0, 0, empty)
            table.setSpan(0, 0, 1, table.columnCount())
            table.setRowHeight(0, 52)
            return

        row_height = 42 if self._product_card_density == "compact" else 52
        for row, product in enumerate(self.products):
            key = str(product.get("id") or "")
            image_item = QTableWidgetItem()
            raw_image = product.get("_image_bytes")
            if raw_image:
                pixmap = QPixmap()
                if pixmap.loadFromData(raw_image):
                    image_item.setIcon(QIcon(pixmap.scaled(
                        36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )))
            image_item.setToolTip(str(product.get("name") or "کالا"))
            table.setItem(row, 0, image_item)

            name_item = QTableWidgetItem(str(product.get("name") or "کالای بدون نام"))
            name_item.setData(Qt.ItemDataRole.UserRole, product)
            table.setItem(row, 1, name_item)

            category_name = self._category_names.get(str(product.get("category_id")), "—")
            category_item = QTableWidgetItem(category_name)
            category_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, category_item)

            price_item = QTableWidgetItem("{:,.2f}".format(float(product.get("sell_price") or 0)))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 3, price_item)

            tracked = bool(product.get("track_stock"))
            capacity = self._stock_capacity(product, key)
            available = max(0, capacity - int(self._cart.get(key, {}).get("quantity", 0)))
            stock_text = (
                ("ناموجود" if available <= 0 else "موجودی: {:g}".format(available))
                if tracked else "آماده فروش"
            )
            stock_badge = QLabel(stock_text)
            stock_badge.setObjectName("SalesProductStock")
            stock_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stock_badge.setProperty("outOfStock", bool(tracked and available <= 0))
            table.setCellWidget(row, 4, stock_badge)
            self._product_stock_labels[key] = stock_badge

            add = QPushButton("افزودن")
            add.setObjectName("SalesProductAddButton")
            add.setMinimumHeight(25 if self._product_card_density == "compact" else 29)
            add.setToolTip("افزودن {} به سبد خرید".format(product.get("name") or "کالا"))
            add.clicked.connect(lambda _checked=False, selected=product: self.add_to_cart(selected))
            add.setEnabled(not tracked or available > 0)
            table.setCellWidget(row, 5, add)
            self._product_add_buttons[key] = add
            table.setRowHeight(row, row_height)

    def _original_quantity_for_product(self, product_key):
        if not self._editing_receipt:
            return 0
        quantity = 0
        for item in self._editing_receipt.get("items") or []:
            item_product_id = item.get("product_id") or item.get("product")
            if str(item_product_id or "") == str(product_key):
                try:
                    quantity += max(0, int(item.get("quantity") or 0))
                except (TypeError, ValueError):
                    continue
        return quantity

    def _stock_capacity(self, product, product_key):
        stock = max(0, int(float(product.get("stock_quantity") or 0)))
        if self._editing_receipt_id:
            stock += self._original_quantity_for_product(product_key)
        return stock

    def _build_product_card(
        self, product, preview=False, layout_mode=None, show_images=None, density=None
    ):
        """Build a product card for the catalog or a side-effect-free settings preview."""
        key = str(product.get("id") or "")
        mode = str(layout_mode or self._product_layout_mode)
        show_images = self._show_product_images if show_images is None else bool(show_images)
        density = str(density or self._product_card_density)
        compact = density == "compact"
        horizontal = mode in {"horizontal", "list"}

        card = QFrame()
        card.setObjectName("SalesProductCard")
        card.setProperty("displayMode", mode)
        card.setFrameShape(QFrame.Shape.NoFrame)
        if mode == "grid":
            card.setMinimumWidth(128)
            card.setMaximumWidth(218)
            card_layout = QVBoxLayout(card)
        else:
            card.setMinimumWidth(0)
            card.setMaximumWidth(16777215)
            card.setMinimumHeight(58 if mode == "list" else 94)
            card_layout = QHBoxLayout(card)
        margin = 5 if compact else 7
        card_layout.setContentsMargins(margin, margin, margin, margin)
        card_layout.setSpacing(4 if compact else 6)

        image = None
        if show_images:
            image = QLabel()
            image.setObjectName("SalesProductImage")
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap()
            image_bytes = product.get("_image_bytes")
            if image_bytes and pixmap.loadFromData(image_bytes):
                target = (42, 42) if mode == "list" else ((76, 76) if horizontal else (138, 54 if compact else 66))
                image.setPixmap(pixmap.scaled(
                    target[0], target[1], Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            else:
                image.setText("بدون تصویر")
            if mode == "grid":
                image.setMinimumHeight(40 if compact else 48)
                image.setMaximumHeight(58 if compact else 74)
            elif mode == "list":
                image.setFixedSize(48, 48)
            else:
                image.setFixedSize(84, 84)

        name = QLabel(str(product.get("name") or "کالای بدون نام"))
        name.setObjectName("SalesProductTitle")
        name.setWordWrap(mode != "list")
        name.setAlignment(
            Qt.AlignmentFlag.AlignCenter if mode == "grid"
            else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        if mode == "grid":
            name.setMinimumHeight(25 if compact else 28)

        category_id = product.get("category_id")
        category_name = self._category_names.get(str(category_id), "")
        category = QLabel(category_name) if category_name else None
        if category is not None:
            category.setObjectName("Muted")
            category.setWordWrap(True)
            category.setAlignment(
                Qt.AlignmentFlag.AlignCenter if mode == "grid"
                else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

        price = QLabel("{:,.2f}".format(float(product.get("sell_price") or 0)))
        price.setObjectName("SalesProductPrice")
        price.setAlignment(
            Qt.AlignmentFlag.AlignCenter if mode == "grid"
            else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        tracked = bool(product.get("track_stock"))
        capacity = self._stock_capacity(product, key) if not preview else max(
            0, int(float(product.get("stock_quantity") or 0))
        )
        available = max(0, capacity - int(self._cart.get(key, {}).get("quantity", 0))) if not preview else capacity
        if tracked:
            stock_text = "ناموجود" if available <= 0 else "موجودی: {:g}".format(available)
        else:
            stock_text = "آماده فروش"
        stock_badge = QLabel(stock_text)
        stock_badge.setObjectName("SalesProductStock")
        stock_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter if mode == "grid"
            else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        stock_badge.setProperty("outOfStock", bool(tracked and available <= 0))

        add = QPushButton("افزودن به سبد" if mode != "list" else "افزودن")
        add.setObjectName("SalesProductAddButton")
        add.setMinimumHeight(25 if compact else 29)
        add.setToolTip("افزودن {} به سبد خرید".format(product.get("name") or "کالا"))
        if preview:
            add.setEnabled(False)
        else:
            add.clicked.connect(lambda _checked=False, selected=product: self.add_to_cart(selected))
            add.setEnabled(not tracked or available > 0)
            self._product_stock_labels[key] = stock_badge
            self._product_add_buttons[key] = add
            set_button_icon(add, "cart", getattr(self.window, "mode", "light"))

        if not horizontal:
            if image is not None:
                card_layout.addWidget(image)
            card_layout.addWidget(name)
            if category is not None:
                card_layout.addWidget(category)
            card_layout.addWidget(price)
            card_layout.addWidget(stock_badge)
            card_layout.addWidget(add)
        else:
            if image is not None:
                card_layout.addWidget(image, 0, Qt.AlignmentFlag.AlignVCenter)
            info = QWidget()
            info_layout = QVBoxLayout(info)
            info_layout.setContentsMargins(3, 0, 3, 0)
            info_layout.setSpacing(2 if compact else 4)
            info_layout.addWidget(name)
            if category is not None:
                info_layout.addWidget(category)
            info_layout.addWidget(price)
            info_layout.addWidget(stock_badge)
            card_layout.addWidget(info, 1)
            card_layout.addWidget(add, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _refresh_product_stock_states(self):
        """Synchronize stock badges and add-button states with selected quantities."""
        for product in self.products:
            key = str(product.get("id") or "")
            button = self._product_add_buttons.get(key)
            stock_badge = self._product_stock_labels.get(key)
            tracked = bool(product.get("track_stock"))
            capacity = self._stock_capacity(product, key)
            selected = int(self._cart.get(key, {}).get("quantity", 0))
            available = max(0, capacity - selected)
            if stock_badge is not None:
                stock_badge.setText(
                    ("ناموجود" if available <= 0 else "موجودی: {:g}".format(available))
                    if tracked else "آماده فروش"
                )
                stock_badge.setProperty("outOfStock", bool(tracked and available <= 0))
                stock_badge.style().unpolish(stock_badge)
                stock_badge.style().polish(stock_badge)
            if button is not None:
                button.setEnabled(not tracked or selected < capacity)

    def add_to_cart(self, product):
        """Add one unit, enforcing known stock limits without replacing server validation."""
        key = str(product.get("id") or "")
        if not key:
            return
        product = self._product_cache.get(key, product)
        current = int(self._cart.get(key, {}).get("quantity", 0))
        next_quantity = current + 1
        if product.get("track_stock") and next_quantity > self._stock_capacity(product, key):
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
            stock = self._stock_capacity(product, product_key)
            if quantity > stock:
                quantity = stock
        if quantity <= 0:
            self._cart.pop(product_key, None)
            self._render_cart()
        else:
            entry["quantity"] = quantity
            line_total = self._cart_line_total_labels.get(product_key)
            if line_total is not None:
                price = float(product.get("sell_price") or 0)
                line_total.setText("{:,.2f}".format(price * quantity))
            quantity_label = self._cart_quantity_labels.get(product_key)
            if quantity_label is not None:
                quantity_label.setText(str(quantity))
            minus_button = self._cart_minus_buttons.get(product_key)
            if minus_button is not None:
                minus_button.setEnabled(quantity > 1)
            plus_button = self._cart_plus_buttons.get(product_key)
            if plus_button is not None:
                plus_button.setEnabled(
                    not product.get("track_stock")
                    or quantity < self._stock_capacity(product, product_key)
                )
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
        """Render a compact invoice-like cart line with small quantity and remove controls."""
        self._cart_line_total_labels = {}
        self._cart_quantity_labels = {}
        self._cart_plus_buttons = {}
        self._cart_minus_buttons = {}
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
            price = float(product.get("sell_price") or 0)

            card = QFrame()
            card.setObjectName("SalesCartItem")
            card.setMinimumHeight(56)
            card.setMaximumHeight(74)
            row_layout = QHBoxLayout(card)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(6)

            product_info = QWidget(card)
            info_layout = QVBoxLayout(product_info)
            info_layout.setContentsMargins(0, 0, 0, 0)
            info_layout.setSpacing(1)
            title = QLabel(str(product.get("name") or "کالا"))
            title.setObjectName("SalesCartItemTitle")
            title.setWordWrap(True)
            unit_price = QLabel("هر واحد: {:,.2f}".format(price))
            unit_price.setObjectName("PageSubtitle")
            info_layout.addWidget(title)
            info_layout.addWidget(unit_price)
            row_layout.addWidget(product_info, 1)

            minus = QPushButton("−")
            minus.setObjectName("SalesQtyButton")
            minus.setToolTip("کم‌کردن تعداد")
            minus.setAccessibleName("کم‌کردن تعداد {}".format(product.get("name") or "کالا"))
            minus.setFixedSize(27, 27)
            minus.setEnabled(quantity > 1)
            minus.clicked.connect(
                lambda _checked=False, item_key=key: self._change_cart_quantity(item_key, -1)
            )
            row_layout.addWidget(minus)
            self._cart_minus_buttons[key] = minus

            quantity_label = QLabel(str(quantity))
            quantity_label.setObjectName("SalesCartQuantity")
            quantity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            quantity_label.setMinimumWidth(22)
            quantity_label.setMaximumWidth(34)
            row_layout.addWidget(quantity_label)
            self._cart_quantity_labels[key] = quantity_label

            plus = QPushButton("+")
            plus.setObjectName("SalesQtyButton")
            plus.setToolTip("زیادکردن تعداد")
            plus.setAccessibleName("زیادکردن تعداد {}".format(product.get("name") or "کالا"))
            plus.setFixedSize(27, 27)
            plus.setEnabled(
                not product.get("track_stock")
                or quantity < self._stock_capacity(product, key)
            )
            plus.clicked.connect(
                lambda _checked=False, item_key=key: self._change_cart_quantity(item_key, 1)
            )
            row_layout.addWidget(plus)
            self._cart_plus_buttons[key] = plus

            line_total = QLabel("{:,.2f}".format(price * quantity))
            line_total.setObjectName("SalesCartLineTotal")
            line_total.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            line_total.setMinimumWidth(62)
            self._cart_line_total_labels[key] = line_total
            row_layout.addWidget(line_total)

            remove = QPushButton("×")
            remove.setObjectName("SalesRemoveButton")
            remove.setToolTip("حذف کالا از فاکتور")
            remove.setAccessibleName("حذف {}".format(product.get("name") or "کالا"))
            remove.setFixedSize(26, 26)
            remove.clicked.connect(
                lambda _checked=False, item_key=key: self._remove_cart_item(item_key)
            )
            row_layout.addWidget(remove)

            self.cart_items_layout.addWidget(card)
        self.cart_items_layout.addStretch(1)
        self._refresh_cart_summary()

    def _change_cart_quantity(self, product_key, delta):
        entry = self._cart.get(product_key)
        if not entry:
            return
        self._set_cart_quantity(
            product_key, int(entry.get("quantity") or 0) + int(delta)
        )

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

    def _splitter_moved(self, *_args):
        """Persist pane proportions and reflow cards while the cashier drags the divider."""
        sizes = self.splitter.sizes()
        if len(sizes) == 2 and all(size > 0 for size in sizes):
            self._saved_splitter_sizes = sizes
            self._local_settings.setValue("sales/splitter_sizes", sizes)
        self._reflow_product_grid()

    def _reflow_product_grid(self):
        if not hasattr(self, "catalog_scroll"):
            return
        width = self.catalog_scroll.viewport().width()
        columns = max(1, min(5, max(260, width) // 225))
        if columns != self._rendered_columns:
            self._rendered_columns = columns
            self._render_products()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_product_grid()

    def checkout(self):
        items = self.collect_items()
        if not items:
            self.window.show_error("برای ثبت فروش حداقل یک تعداد مثبت وارد کنید.")
            return

        editing = self._editing_receipt_id is not None
        if editing:
            prompt = "تغییرات فاکتور {} ذخیره شود؟ مبلغ و موجودی دوباره در سرور اعتبارسنجی می‌شوند.".format(
                (self._editing_receipt or {}).get("day_receipt_id")
                or str(self._editing_receipt_id)[:8]
            )
        else:
            prompt = "فروش با {} نوع کالا ثبت شود؟ مبلغ نهایی در سرور محاسبه می‌شود.".format(len(items))
        answer = QMessageBox.question(
            self,
            "تأیید تغییرات" if editing else "تأیید فروش",
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        paid = self.paid.isChecked()
        payment_method = self.payment_method_combo.currentData() or "cash"
        if not paid:
            payment_method = "unpaid"
        seat_number = self.seat_number.currentData() if self.seat_row.isVisible() else None
        if self.seat_row.isVisible() and not seat_number:
            self.window.show_error("برای فروش کافه، شماره صندلی یا میز را انتخاب کنید.")
            self.seat_number.setFocus()
            return

        if editing:
            receipt_id = self._editing_receipt_id
            self.window.run_api(
                lambda: self.window.api.update_sale(
                    receipt_id,
                    items,
                    paid=paid,
                    payment_method=payment_method,
                    seat_number=seat_number,
                ),
                lambda receipt: self._sale_created(receipt, updated=True),
                busy=self.submit_button,
            )
            return

        settings = device_settings()
        if paid and payment_method == "card" and settings.get("terminal_mode") == "tcp":
            self.window.run_api(
                lambda: self._checkout_via_terminal(items, settings, seat_number=seat_number),
                self._terminal_sale_created,
                busy=self.submit_button,
            )
        else:
            self.window.run_api(
                lambda: self.window.api.create_sale(
                    items, paid=paid, payment_method=payment_method, seat_number=seat_number
                ),
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

    def _sale_created(self, receipt, updated=False):
        self._editing_receipt_id = None
        self._editing_receipt = None
        self.paid.setChecked(False)
        self.payment_method_combo.setCurrentIndex(max(0, self.payment_method_combo.findData("cash")))
        self.seat_number.setCurrentIndex(0)
        self._cart.clear()
        self._render_cart()
        self._update_invoice_mode_controls()
        self._refresh_product_stock_states()
        self._refresh_cart_summary()
        if updated:
            message = "فاکتور شمارهٔ {} با مبلغ {:,.2f} به‌روزرسانی شد.".format(
                receipt.get("day_receipt_id", "—"), float(receipt.get("total_price") or 0)
            )
        else:
            message = "فروش شمارهٔ {} با مبلغ {:,.2f} ثبت شد.".format(
                receipt.get("day_receipt_id", "—"), float(receipt.get("total_price") or 0)
            )
        self.window.set_status(message)
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
                lambda template: self._present_invoice(receipt, template, auto_print=not updated),
                failure=lambda _error: self._present_invoice(
                    receipt, DEFAULT_TEMPLATE, auto_print=not updated
                ),
            )
        else:
            self._present_invoice(receipt, DEFAULT_TEMPLATE, auto_print=not updated)

    def _present_invoice(self, receipt, template, auto_print=True):
        if auto_print:
            auto_print_invoice(receipt, template, self.window)
        InvoiceDialog(receipt, template, self.window).exec()

    def show_recent_receipts(self):
        """Open a tabbed recent-invoice workspace with a consistent preview/edit flow."""
        if not self.window.api:
            return

        from PySide6.QtWidgets import QApplication, QDialog, QTabWidget

        hours = int(
            (getattr(self.window, "company_profile", None) or {}).get(
                "receipt_history_hours", 48
            )
        )
        dialog = QDialog(self)
        dialog.setObjectName("RecentInvoicesDialog")
        dialog.setWindowTitle("فاکتورهای اخیر")
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        screen = self.window.screen() if hasattr(self.window, "screen") else QApplication.primaryScreen()
        if screen is None:
            dialog.resize(1120, 760)
        else:
            available = screen.availableGeometry()
            dialog.resize(
                min(1480, max(800, int(available.width() * 0.92))),
                min(1180, max(560, int(available.height() * 0.88))),
            )
        dialog.setMinimumSize(760, 480)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        heading = QHBoxLayout()
        title = QLabel("مدیریت فاکتورها")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "سوابق {} ساعت اخیر · برای مشاهده دوبار کلیک کنید یا ویرایش را انتخاب کنید.".format(hours)
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(subtitle, 1)
        root.addLayout(heading)

        tabs = QTabWidget(dialog)
        tabs.setObjectName("RecentInvoicesTabs")
        tabs.setDocumentMode(True)
        root.addWidget(tabs, 1)

        tab_specs = (
            ("all", "همهٔ فاکتورها"),
            ("unpaid", "پرداخت‌نشده"),
            ("paid", "پرداخت‌شده"),
        )
        tables = {}
        tab_labels = {}
        for key, label in tab_specs:
            page = QWidget(tabs)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(4, 8, 4, 4)
            page_layout.setSpacing(6)
            table = QTableWidget(0, 7, page)
            table.setObjectName("RecentInvoicesTable")
            table.setHorizontalHeaderLabels([
                "شناسه", "شماره فاکتور", "وضعیت", "تاریخ", "میز / صندلی", "مبلغ", "روش پرداخت"
            ])
            table.setColumnHidden(0, True)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setWordWrap(False)
            page_layout.addWidget(table, 1)
            page_hint = QLabel("")
            page_hint.setObjectName("PageSubtitle")
            page_layout.addWidget(page_hint)
            tabs.addTab(page, label)
            tables[key] = table
            tab_labels[key] = (page_hint, label)

        footer = QHBoxLayout()
        history_status = QLabel("در حال بارگذاری فاکتورها…")
        history_status.setObjectName("PageSubtitle")
        load_more_button = QPushButton("بارگذاری فاکتورهای بیشتر")
        load_more_button.setObjectName("SalesToolbarButton")
        load_more_button.setToolTip("دریافت صفحهٔ بعدی فاکتورها")
        refresh_history_button = QPushButton("بازخوانی")
        refresh_history_button.setObjectName("SalesToolbarButton")
        preview_button = QPushButton("پیش‌نمایش فاکتور")
        preview_button.setObjectName("PrimaryButton")
        edit_button = QPushButton("بارگذاری برای ویرایش")
        edit_button.setObjectName("PrimaryButton")
        edit_button.setVisible(self._can_edit_receipts)
        close_button = QPushButton("بستن")
        close_button.setObjectName("SalesToolbarButton")
        footer.addWidget(history_status, 1)
        footer.addWidget(load_more_button)
        footer.addWidget(refresh_history_button)
        footer.addWidget(preview_button)
        footer.addWidget(edit_button)
        footer.addWidget(close_button)
        root.addLayout(footer)
        close_button.clicked.connect(dialog.reject)

        page_size = 50
        current_page = 0
        total_records = 0
        records = []

        def filtered_records(key):
            if key == "unpaid":
                return [item for item in records if not bool(item.get("payed"))]
            if key == "paid":
                return [item for item in records if bool(item.get("payed"))]
            return list(records)

        def render_tables():
            for key, table in tables.items():
                visible_records = filtered_records(key)
                table.setRowCount(0)
                for row, record in enumerate(visible_records):
                    table.insertRow(row)
                    receipt_id = str(record.get("id") or "")
                    number = record.get("day_receipt_id") or receipt_id[:8] or "—"
                    paid = bool(record.get("payed"))
                    payment_method = {
                        "cash": "نقدی",
                        "card": "کارت",
                        "bank_transfer": "انتقال بانکی",
                        "store_credit": "اعتباری",
                        "unpaid": "پرداخت‌نشده",
                    }.get(str(record.get("payment_method") or ""), "—")
                    values = [
                        receipt_id,
                        str(number),
                        "پرداخت‌شده" if paid else "پرداخت‌نشده",
                        str(record.get("created_at") or "—").replace("T", " ")[:19],
                        str(record.get("seat_number") or "—"),
                        "{:,.2f}".format(float(record.get("total_price") or 0)),
                        payment_method,
                    ]
                    for column, value in enumerate(values):
                        cell = QTableWidgetItem(value)
                        if column == 0:
                            cell.setData(Qt.ItemDataRole.UserRole, record)
                        table.setItem(row, column, cell)

                page_hint, label = tab_labels[key]
                page_hint.setText("{} فاکتور در این تب".format(len(visible_records)))
                tabs.setTabText(
                    tabs.indexOf(table.parentWidget()),
                    "{} ({})".format(label, len(visible_records)),
                )

            unpaid_count = sum(not bool(item.get("payed")) for item in records)
            paid_count = len(records) - unpaid_count
            history_status.setText(
                "{} از {} فاکتور بارگذاری شده · {} پرداخت‌نشده · {} پرداخت‌شده".format(
                    len(records), total_records, unpaid_count, paid_count
                )
            )
            load_more_button.setVisible(len(records) < total_records)
            load_more_button.setEnabled(len(records) < total_records)

        def populate(payload, append=False):
            nonlocal current_page, total_records, records
            incoming = list(payload.get("items") or [])
            if not append:
                records = []
            known_ids = {str(item.get("id") or "") for item in records}
            for record in incoming:
                record_id = str(record.get("id") or "")
                if record_id and record_id not in known_ids:
                    records.append(record)
                    known_ids.add(record_id)
            try:
                total_records = max(0, int(payload.get("total", len(records)) or 0))
                current_page = max(1, int(payload.get("page", current_page or 1) or 1))
            except (TypeError, ValueError):
                total_records = len(records)
                current_page = max(1, current_page or 1)
            render_tables()

        def load_page(page, append=False):
            load_more_button.setEnabled(False)
            self.window.run_api(
                lambda: self.window.api.list_recent_receipts_page(
                    page=page, page_size=page_size
                ),
                lambda payload: populate(payload, append=append),
                failure=lambda error: (
                    history_status.setText("دریافت فاکتورها ناموفق بود."),
                    QMessageBox.warning(dialog, "خطای دریافت فاکتورها", str(error)),
                    load_more_button.setEnabled(True),
                ),
                busy=refresh_history_button if not append else load_more_button,
            )

        def selected_record():
            key = next(
                (name for name, table in tables.items() if tabs.currentWidget() is table.parentWidget()),
                "all",
            )
            table = tables[key]
            row = table.currentRow()
            cell = table.item(row, 0) if row >= 0 else None
            record = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if not record:
                QMessageBox.information(dialog, "انتخاب فاکتور", "ابتدا یک فاکتور را از تب جاری انتخاب کنید.")
                return None
            return record

        def open_selected():
            record = selected_record()
            if not record:
                return
            self.window.run_api(
                lambda: self._load_recent_invoice(record["id"]),
                lambda result: self._show_recent_invoice(result, dialog),
                failure=lambda error: QMessageBox.warning(dialog, "خطای دریافت فاکتور", str(error)),
                busy=preview_button,
            )

        def edit_selected():
            record = selected_record()
            if not record:
                return
            self.window.run_api(
                lambda: self._load_recent_invoice(record["id"]),
                lambda result: self._load_invoice_into_editor(result, dialog),
                failure=lambda error: QMessageBox.warning(dialog, "خطای بارگذاری برای ویرایش", str(error)),
                busy=edit_button,
            )

        for key, table in tables.items():
            table.cellDoubleClicked.connect(
                lambda _row, _column, _key=key: open_selected()
            )
        preview_button.clicked.connect(open_selected)
        edit_button.clicked.connect(edit_selected)
        load_more_button.clicked.connect(lambda: load_page(current_page + 1, append=True))
        refresh_history_button.clicked.connect(lambda: load_page(1, append=False))

        load_page(1, append=False)
        apply_button_icons(dialog, getattr(self.window, "mode", "light"))
        dialog.exec()

    def _load_recent_invoice(self, receipt_id):
        api = self.window.api
        receipt = api.get_receipt(receipt_id)
        products = {}
        for item in receipt.get("items") or []:
            product_id = str(item.get("product_id") or "")
            if not product_id or product_id in products:
                continue
            try:
                product = api.get_product(product_id)
            except Exception as error:
                if getattr(error, "status_code", None) != 404:
                    raise
                product = {
                    "id": product_id,
                    "name": item.get("product_name") or "محصول حذف‌شده",
                    "sell_price": item.get("sell_price") or 0,
                    "buy_price": item.get("buy_price") or 0,
                    "track_stock": False,
                    "stock_quantity": 0,
                    "category_id": None,
                    "image_path": None,
                    "_deleted_product": True,
                }
            if self._show_product_images and product.get("image_path"):
                try:
                    product["_image_bytes"] = api.get_product_image_bytes(product_id)
                except Exception:
                    product["_image_bytes"] = None
            products[product_id] = product
        try:
            template = api.get_invoice_template()
        except Exception:
            template = DEFAULT_TEMPLATE
        return {"receipt": receipt, "products": products, "template": template}

    def _load_invoice_into_editor(self, payload, dialog=None):
        if self._cart:
            answer = QMessageBox.question(
                self,
                "جایگزینی سبد فعلی",
                "سبد فعلی با اقلام فاکتور انتخاب‌شده جایگزین شود؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        receipt = dict(payload.get("receipt") or {})
        receipt_id = str(receipt.get("id") or "")
        if not receipt_id:
            self.window.show_error("شناسهٔ فاکتور برای ویرایش معتبر نیست.")
            return False

        products = payload.get("products") or {}
        new_cart = {}
        for line in receipt.get("items") or []:
            product_id = str(line.get("product_id") or "")
            if not product_id:
                continue
            product = dict(
                products.get(product_id)
                or self._product_cache.get(product_id)
                or {}
            )
            product.setdefault("id", product_id)
            product.setdefault("name", line.get("product_name") or "کالا")
            product.setdefault("sell_price", line.get("sell_price") or 0)
            product.setdefault("buy_price", line.get("buy_price") or 0)
            product.setdefault("track_stock", False)
            product.setdefault("stock_quantity", 0)
            previous = self._product_cache.get(product_id, {})
            if "_image_bytes" not in product and previous.get("_image_bytes"):
                product["_image_bytes"] = previous["_image_bytes"]
            self._product_cache[product_id] = product
            try:
                quantity = max(1, int(line.get("quantity") or 1))
            except (TypeError, ValueError):
                quantity = 1
            if product_id in new_cart:
                new_cart[product_id]["quantity"] += quantity
            else:
                new_cart[product_id] = {"product": product, "quantity": quantity}

        self._editing_receipt_id = receipt_id
        self._editing_receipt = receipt
        self._cart = new_cart
        self.paid.setChecked(bool(receipt.get("payed")))
        payment_index = self.payment_method_combo.findData(receipt.get("payment_method"))
        if payment_index >= 0:
            self.payment_method_combo.setCurrentIndex(payment_index)
        seat_number = receipt.get("seat_number")
        if seat_number:
            seat_value = str(seat_number)
            seat_index = self.seat_number.findData(seat_value)
            if seat_index < 0:
                self.seat_number.addItem("میز {}".format(seat_value), seat_value)
                seat_index = self.seat_number.count() - 1
            self.seat_number.setCurrentIndex(seat_index)
        else:
            self.seat_number.setCurrentIndex(0)

        self._set_cart_panel_visible(True)
        self._update_invoice_mode_controls()
        self._render_cart()
        self._refresh_cart_summary()
        self._refresh_product_stock_states()
        self.window.set_status(
            "فاکتور شمارهٔ {} برای ویرایش بارگذاری شد.".format(
                receipt.get("day_receipt_id") or receipt_id[:8]
            )
        )
        if dialog is not None:
            dialog.accept()
        return True

    def _show_recent_invoice(self, payload, dialog):
        InvoiceDialog(payload["receipt"], payload.get("template") or DEFAULT_TEMPLATE, self.window).exec()
