"""API-driven point-of-sale screen with search, quantity selection, and idempotent checkout."""
from PySide6.QtCore import Qt, QSettings, QTimer, QEvent, QPoint
from PySide6.QtGui import QColor, QBrush, QPixmap
import uuid
import json

from client.payment_terminal import authorize_payment, void_payment
from client.ui.device_settings import device_settings
from client.ui.invoice_dialog import InvoiceDialog, InvoicePreviewWidget, auto_print_invoice
from client.ui.invoice_render import DEFAULT_TEMPLATE, SALES_INVOICE_TEMPLATE_KIND
from client.ui.permissions import can_access
from client.ui.icons import apply_button_icons, set_button_icon

from PySide6.QtWidgets import (
    QAbstractItemView, QBoxLayout, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHeaderView, QWidget, QListWidget, QListWidgetItem,
    QSizePolicy, QTabBar, QTabWidget, QMenu, QApplication,
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
        self._cart_collapsed = False
        self._history_preview_collapsed = False
        self._history_page_size = 50
        self._history_current_page = 0
        self._history_total_records = 0
        self._history_records = []
        self._history_loaded = False
        self._history_invoice_payload = None
        self._history_search_query = ""

        self._suggestion_query = ""
        self._search_committed = False
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
        # Drop the obsolete fixed-pixel column preference from older versions.
        self._local_settings.remove("sales/product_table_column_widths")
        self._cart_was_collapsed = self._local_settings.value(
            "sales/cart_collapsed", False, type=bool
        )
        self._history_preview_was_collapsed = self._local_settings.value(
            "sales/history_preview_collapsed", True, type=bool
        )
        self._use_category_tabs = self._local_settings.value(
            "sales/use_category_tabs", False, type=bool
        )
        saved_sizes = self._local_settings.value("sales/splitter_sizes", [780, 360])
        try:
            self._saved_splitter_sizes = [max(1, int(saved_sizes[0])), max(1, int(saved_sizes[1]))]
        except (TypeError, ValueError, IndexError):
            self._saved_splitter_sizes = [780, 360]
        self._show_product_images = self._local_settings.value(
            "sales/show_product_images", True, type=bool
        )
        self._zoom_product_images = self._local_settings.value(
            "sales/zoom_product_images", True, type=bool
        )
        self._show_product_stock = self._local_settings.value(
            "sales/show_product_stock", True, type=bool
        )
        self._show_product_add_button = self._local_settings.value(
            "sales/show_product_add_button", True, type=bool
        )
        self._product_stock_display_style = str(
            self._local_settings.value("sales/product_stock_display_style", "text") or "text"
        ).strip().lower()
        if self._product_stock_display_style not in {"text", "circle"}:
            self._product_stock_display_style = "text"
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

        self.theme_button = QPushButton("", self)
        self.theme_button.setObjectName("SalesThemeButton")
        self.theme_button.setFixedSize(32, 32)
        self.theme_button.setToolTip("تغییر تم روشن / تاریک")
        self.theme_button.setAccessibleName("تغییر تم روشن یا تاریک")
        self.theme_button.clicked.connect(self._toggle_theme)
        self.theme_button.hide()

        self.cancel_edit_button = QPushButton("لغو بارگذاری")
        self.cancel_edit_button.setObjectName("SalesToolbarButton")
        self.cancel_edit_button.setToolTip("لغو فاکتور بارگذاری‌شده و بازگشت به فروش جدید")
        self.cancel_edit_button.clicked.connect(self.cancel_invoice_edit)
        self.cancel_edit_button.hide()

        self.refresh_button = QPushButton("", self)
        self.refresh_button.setObjectName("SalesCatalogRefreshButton")
        self.refresh_button.setFixedSize(32, 32)
        self.refresh_button.setToolTip("بازخوانی کالاها")
        self.refresh_button.setAccessibleName("بازخوانی کالاها")
        set_button_icon(self.refresh_button, "refresh", getattr(self.window, "mode", "light"))
        self.refresh_button.clicked.connect(self.refresh_products)

        self.catalog_mode_button = QPushButton("کالاها و فروش")
        self.catalog_mode_button.setObjectName("SalesToolbarButton")
        self.catalog_mode_button.setCheckable(True)
        self.catalog_mode_button.setChecked(True)
        self.catalog_mode_button.clicked.connect(lambda: self.set_workspace_mode("sales"))
        set_button_icon(
            self.catalog_mode_button, "sales", getattr(self.window, "mode", "light")
        )
        header.addWidget(self.catalog_mode_button)

        self.history_button = QPushButton("فاکتورهای اخیر")
        self.history_button.setObjectName("SalesToolbarButton")
        self.history_button.setCheckable(True)
        self.history_button.setToolTip("نمایش فهرست فاکتورها در فضای اصلی POS")
        self.history_button.clicked.connect(lambda: self.set_workspace_mode("history"))
        set_button_icon(
            self.history_button, "history", getattr(self.window, "mode", "light")
        )
        header.addWidget(self.history_button)
        root.addLayout(header)

        self.workspace_stack = QStackedWidget(self)
        self.workspace_stack.setObjectName("POSModeStack")
        root.addWidget(self.workspace_stack, 1)

        self.sales_workspace = QWidget(self.workspace_stack)
        self.sales_workspace.setObjectName("POSSalesMode")
        self.sales_layout = QVBoxLayout(self.sales_workspace)
        self.sales_layout.setContentsMargins(0, 0, 0, 0)
        self.sales_layout.setSpacing(8)
        self.workspace_stack.addWidget(self.sales_workspace)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self.sales_workspace)
        self.splitter.setObjectName("SalesWorkspaceSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.splitter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # In RTL mode the first splitter child is the right-hand catalog; the
        # cart remains on the left and can collapse to a narrow control rail.
        self.catalog_panel = self._build_catalog_panel()
        self.cart_panel = self._build_cart_panel()
        self.splitter.addWidget(self.catalog_panel)
        self.splitter.addWidget(self.cart_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.installEventFilter(self)
        self.sales_workspace.installEventFilter(self)
        self.workspace_stack.installEventFilter(self)
        self.splitter.setSizes(self._saved_splitter_sizes)
        self.splitter.splitterMoved.connect(self._splitter_moved)
        self.sales_layout.addWidget(self.splitter, 1)

        self.seat_row = QFrame(self.sales_workspace)
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
        self.sales_layout.addWidget(self.seat_row)

        footer_card = QFrame(self.sales_workspace)
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
        self.submit_button = QPushButton("ثبت فروش")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.clicked.connect(self.checkout)
        footer.addWidget(self.paid)
        footer.addWidget(self.payment_method_label)
        footer.addWidget(self.payment_method_combo)
        footer.addStretch(1)
        # In the RTL footer the cancel action is inserted before the total so it
        # appears immediately to the total's right on screen.
        footer.addWidget(self.cancel_edit_button)
        footer.addWidget(self.total_label)
        footer.addWidget(self.submit_button)
        self.footer_layout = footer
        self.sales_layout.addWidget(footer_card)

        self.history_workspace = self._build_recent_receipts_workspace()
        self.workspace_stack.addWidget(self.history_workspace)
        self.workspace_stack.setCurrentWidget(self.sales_workspace)
        self._sync_category_selector()
        self._refresh_cart_summary()
        self._update_invoice_mode_controls()
        self.sync_theme_button()
        apply_button_icons(self, getattr(self.window, "mode", "light"))
        self.sync_theme_button()
        if self._cart_was_collapsed:
            # Start fully hidden rather than briefly showing a clipped cart rail.
            self._set_cart_panel_visible(False)
        if self._history_preview_was_collapsed:
            QTimer.singleShot(0, lambda: self._set_history_preview_visible(False))

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
        self.cart_panel_toggle = QPushButton("‹", panel)
        self.cart_panel_toggle.setObjectName("SalesCartToggleButton")
        self.cart_panel_toggle.setFixedSize(30, 30)
        self.cart_panel_toggle.setAccessibleName("جمع یا باز کردن پنل سبد خرید")
        self.cart_panel_toggle.setToolTip("جمع‌کردن پنل سبد خرید")
        self.cart_panel_toggle.clicked.connect(self._toggle_cart_panel)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.refresh_button)
        title_row.addWidget(self.catalog_count_label)
        title_row.addWidget(self.cart_panel_toggle)
        self.catalog_title_row = title_row
        layout.addLayout(title_row)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("SalesProductSearch")
        self.search.setPlaceholderText("نام کالا را جست‌وجو کنید…")
        self.search.setClearButtonEnabled(True)
        self.search.installEventFilter(self)
        self.search.returnPressed.connect(self._commit_search)
        self.search_button = QPushButton("جست‌وجو")
        self.search_button.setToolTip("نمایش نتایج جست‌وجو در فهرست کالاها")
        self.search_button.clicked.connect(self._commit_search)
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
        self.category_label = category_label
        self.category_combo = QComboBox()
        self.category_combo.setMinimumWidth(150)
        self.category_combo.addItem("همهٔ دسته‌ها", None)
        self.category_combo.currentIndexChanged.connect(self._category_changed)
        self.category_tabs = QTabBar(panel)
        self.category_tabs.setObjectName("SalesCategoryTabs")
        self.category_tabs.setUsesScrollButtons(True)
        self.category_tabs.setExpanding(False)
        self.category_tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.category_tabs.setDrawBase(False)
        self.category_tabs.addTab("همهٔ دسته‌ها")
        self.category_tabs.setTabData(0, None)
        self.category_tabs.currentChanged.connect(self._category_tab_changed)
        self.product_display_settings_button = QPushButton("⚙")
        self.product_display_settings_button.setObjectName("SalesDisplaySettingsButton")
        self.product_display_settings_button.setToolTip("تنظیمات و پیش‌نمایش نمایش کالاها")
        self.product_display_settings_button.setAccessibleName("تنظیمات نمایش کالاها")
        self.product_display_settings_button.setFixedSize(36, 36)
        self.product_display_settings_button.clicked.connect(self.open_product_display_settings)
        self.product_deselect_button = QPushButton("", panel)
        self.product_deselect_button.setObjectName("SalesDeselectButton")
        self.product_deselect_button.setFixedSize(32, 32)
        self.product_deselect_button.setToolTip("لغو انتخاب سطر جدول")
        self.product_deselect_button.setAccessibleName("لغو انتخاب سطر جدول کالاها")
        set_button_icon(self.product_deselect_button, "clear", getattr(self.window, "mode", "light"))
        self.product_deselect_button.clicked.connect(self._deselect_product_table_row)
        self.product_deselect_button.setVisible(self._product_layout_mode == "table")
        self.product_deselect_button.setEnabled(False)
        options.addWidget(category_label)
        options.addWidget(self.category_combo, 1)
        options.addWidget(self.category_tabs, 1)
        options.addWidget(self.product_display_settings_button)
        options.addWidget(self.product_deselect_button)
        layout.addLayout(options)

        self.catalog_scroll = QScrollArea()
        self.catalog_scroll.setObjectName("SalesProductScrollArea")
        self.catalog_scroll.setWidgetResizable(True)
        self.catalog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.product_grid_host = QWidget()
        self.product_grid_host.setObjectName("SalesProductGridHost")
        self.product_grid_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.product_grid_host.setMinimumWidth(0)
        self.product_grid = QGridLayout(self.product_grid_host)
        self.product_grid.setContentsMargins(4, 4, 4, 4)
        self.product_grid.setHorizontalSpacing(10)
        self.product_grid.setVerticalSpacing(10)
        self.catalog_scroll.setWidget(self.product_grid_host)
        self.catalog_scroll.viewport().installEventFilter(self)

        self.catalog_results_stack = QStackedWidget()
        self.catalog_results_stack.setObjectName("SalesCatalogResults")
        self.catalog_results_stack.installEventFilter(self)
        self.catalog_results_stack.addWidget(self.catalog_scroll)

        self.product_table = QTableWidget(0, 6)
        self.product_table.setObjectName("SalesProductTable")
        self.product_table.setHorizontalHeaderLabels(
            ["تصویر", "نام کالا", "دسته‌بندی", "قیمت", "موجودی", "عملیات"]
        )
        self.product_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.product_table.setAlternatingRowColors(True)
        self.product_table.setWordWrap(False)
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.product_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.product_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.product_table.setShowGrid(False)
        self.product_table.setSortingEnabled(False)
        self.product_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.product_table.installEventFilter(self)
        table_header = self.product_table.horizontalHeader()
        table_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table_header.setStretchLastSection(False)
        # Default proportions are in-memory only. Resizing a column adjusts the
        # live proportions for this window, never a saved pixel/width preference.
        self._product_table_column_weights = [116, 198, 95, 105, 90, 100]
        for column, width in enumerate(self._product_table_column_weights):
            self.product_table.setColumnWidth(column, width)
        self.product_table.viewport().installEventFilter(self)
        # Refit after Qt has propagated a resize through the stacked widgets and
        # splitter; this keeps the table responsive even when no products refresh.
        self._product_table_refit_timer = QTimer(self)
        self._product_table_refit_timer.setSingleShot(True)
        self._product_table_refit_timer.setInterval(0)
        self._product_table_refit_timer.timeout.connect(self._fit_product_table_columns)
        self._product_table_column_adjust_timer = QTimer(self)
        self._product_table_column_adjust_timer.setSingleShot(True)
        self._product_table_column_adjust_timer.setInterval(120)
        self._product_table_column_adjust_timer.timeout.connect(
            self._remember_manual_product_table_column_widths
        )
        table_header.sectionResized.connect(self._schedule_product_table_column_adjustment)
        self.product_table.itemSelectionChanged.connect(self._update_product_table_selection_controls)
        self.product_table.currentCellChanged.connect(self._update_product_table_selection_controls)
        self.product_table.doubleClicked.connect(self._add_table_selection_to_cart)
        self._update_product_table_selection_controls()
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
        """Build the cart with a narrow collapsed rail and a header-local toggle."""
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.cart_title_box = QVBoxLayout()
        title = QLabel("سبد خرید")
        title.setObjectName("PageTitle")
        hint = QLabel("تعداد و اقلام انتخاب‌شده")
        hint.setObjectName("PageSubtitle")
        self.cart_title_box.addWidget(title)
        self.cart_title_box.addWidget(hint)
        header.addLayout(self.cart_title_box, 1)
        self.cart_status_label = QLabel("0 نوع · 0 عدد")
        self.cart_status_label.setObjectName("StatusPill")
        self.cart_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cart_status_label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.cart_status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.cart_status_label.setMinimumWidth(112)
        self.cart_status_label.setMaximumWidth(220)
        self.cart_status_label.setToolTip("تعداد کالاها و تعداد کل واحدهای سبد خرید")
        header.addWidget(self.cart_status_label)
        self.cart_header_layout = header
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

    def _toggle_cart_panel(self, _checked=False):
        """Handle QPushButton.clicked(bool) without mistaking its payload for visibility."""
        self._set_cart_panel_visible(self._cart_collapsed)

    def _set_cart_panel_visible(self, visible):
        """Expand the cart or collapse it into a narrow rail without losing its contents."""
        visible = bool(visible)
        if visible == (not self._cart_collapsed):
            return

        sizes = list(self.splitter.sizes())
        cart_index = self.splitter.indexOf(self.cart_panel)
        if visible:
            # Restore constraints and show the complete cart as one unit.
            self._cart_collapsed = False
            self._local_settings.setValue("sales/cart_collapsed", False)
            self.cart_panel.setMaximumWidth(16777215)
            self.cart_panel.setMinimumWidth(320)
            self.cart_panel.show()
            self.cart_status_label.setObjectName("StatusPill")
            self.cart_status_label.setMinimumWidth(112)
            self.cart_status_label.setMaximumWidth(220)
            self.cart_status_label.style().unpolish(self.cart_status_label)
            self.cart_status_label.style().polish(self.cart_status_label)
            self.cart_scroll.show()
            self.clear_cart_button.show()
            self.cart_empty_label.setVisible(not bool(self._cart))
            self.cart_panel_toggle.setText("‹")
            self.cart_panel_toggle.setToolTip("جمع‌کردن پنل سبد خرید")
        else:
            # Save expanded proportions, then hide the entire panel. A thin rail still
            # leaves the badge/margins visible and is not a true collapsed state.
            if (
                not self._cart_collapsed
                and len(sizes) == 2
                and sizes[cart_index] > 150
                and sum(sizes) > 200
            ):
                self._saved_splitter_sizes = sizes
                self._local_settings.setValue("sales/splitter_sizes", sizes)
            self._cart_collapsed = True
            self._local_settings.setValue("sales/cart_collapsed", True)
            self.cart_panel.hide()
            self.cart_panel_toggle.setText("›")
            self.cart_panel_toggle.setToolTip("بازکردن پنل سبد خرید")

        self._local_settings.sync()
        self._refresh_cart_summary()
        # QSplitter sometimes applies new min/max constraints one layout pass later.
        # Recompute from the current width on that pass rather than reusing stale sizes.
        QTimer.singleShot(0, self._apply_cart_splitter_sizes)

    def _apply_cart_splitter_sizes(self):
        """Reapply sane splitter sizes after the cart width constraints have changed."""
        if not hasattr(self, "splitter") or self.splitter.count() != 2:
            return
        cart_index = self.splitter.indexOf(self.cart_panel)
        catalog_index = 1 - cart_index
        available = max(1, self.splitter.width() - self.splitter.handleWidth())
        sizes = [1, 1]

        if self._cart_collapsed:
            self.cart_panel.hide()
            sizes[cart_index] = 0
            sizes[catalog_index] = available
        else:
            self.cart_panel.show()
            saved = list(self._saved_splitter_sizes or [])
            if len(saved) == 2 and sum(saved) > 0:
                cart_ratio = saved[cart_index] / sum(saved)
            else:
                cart_ratio = 0.30
            max_cart_width = max(
                self.cart_panel.minimumWidth(),
                available - self.catalog_panel.minimumWidth(),
            )
            cart_width = min(
                max(self.cart_panel.minimumWidth(), int(round(available * cart_ratio))),
                max_cart_width,
            )
            sizes[cart_index] = cart_width
            sizes[catalog_index] = max(1, available - cart_width)

        self.splitter.setSizes(sizes)
        # Changing splitter sizes does not emit splitterMoved, and Qt may not
        # propagate the final child/viewport geometry until the next event-loop
        # turn. Explicitly refit after that layout pass so cart toggles never
        # leave stale column widths or oversized thumbnails behind.
        self._schedule_product_table_refit()
        QTimer.singleShot(0, self._refit_product_table_after_cart_layout)

    def _refit_product_table_after_cart_layout(self):
        if self._product_layout_mode != "table":
            return
        timer = getattr(self, "_product_table_refit_timer", None)
        if timer is not None:
            timer.stop()
        self._fit_product_table_columns()
        # One final pass handles viewport geometry updates queued by QSplitter.
        QTimer.singleShot(0, self._fit_product_table_columns)

    def set_permissions(self, user):
        can_read_receipts = can_access(user, "receipts", "read")
        self.history_button.setVisible(can_read_receipts)
        self._can_edit_receipts = can_access(user, "sales", "update")
        if hasattr(self, "history_edit_button"):
            self.history_edit_button.setVisible(self._can_edit_receipts)
        if not can_read_receipts and self.workspace_stack.currentWidget() is self.history_workspace:
            self.set_workspace_mode("sales")

    def set_workspace_mode(self, mode):
        """Switch between the sale workspace and invoice-history workspace in place."""
        mode = "history" if mode == "history" else "sales"
        if mode == "history" and not self.history_button.isVisible():
            return
        page = self.history_workspace if mode == "history" else self.sales_workspace
        self.workspace_stack.setCurrentWidget(page)
        self.catalog_mode_button.setChecked(mode == "sales")
        self.history_button.setChecked(mode == "history")
        current_mode = getattr(self.window, "mode", "light")
        set_button_icon(self.catalog_mode_button, "sales", current_mode)
        set_button_icon(self.history_button, "history", current_mode)
        self.refresh_button.setVisible(mode == "sales")
        self.cancel_edit_button.setVisible(
            mode == "sales" and self._editing_receipt_id is not None
        )
        if mode == "history" and not self._history_loaded:
            self._load_recent_receipt_page(1, append=False)

    def show_recent_receipts(self):
        """Compatibility entry point that switches to the in-place invoice mode."""
        self.set_workspace_mode("history")

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
        self.theme_button.setText("")
        self.theme_button.setToolTip("تغییر تم روشن / تاریک")
        self.theme_button.setAccessibleName("تغییر تم روشن یا تاریک")
        self.theme_button.setVisible(self._is_standalone_pos)
        set_button_icon(
            self.theme_button,
            "theme_dark" if mode != "dark" else "theme_light",
            mode,
            accessible_name="تغییر تم روشن یا تاریک",
        )
        # Refresh icons are semantic too, so tint them whenever the theme changes.
        for button_name, action in (
            ("refresh_button", "refresh"),
            ("history_refresh_button", "refresh"),
            ("product_deselect_button", "clear"),
            ("history_deselect_button", "clear"),
            ("history_preview_close_button", "clear"),
            ("history_preview_reopen_button", "previous" if not self._history_preview_collapsed else "next"),
            ("history_export_button", "download"),
            ("catalog_mode_button", "sales"),
            ("history_button", "history"),
        ):
            button = getattr(self, button_name, None)
            if button is not None:
                set_button_icon(button, action, mode)

    def _payment_status_changed(self, paid):
        self.payment_method_combo.setEnabled(bool(paid))

    def _update_invoice_mode_controls(self):
        editing = self._editing_receipt_id is not None
        if editing:
            self.submit_button.setText("ذخیرهٔ تغییرات فاکتور")
            self.cancel_edit_button.setText("لغو بارگذاری")
            self.cancel_edit_button.show()
        else:
            self.submit_button.setText("ثبت فروش")
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
            object_name = watched.objectName() if hasattr(watched, "objectName") else ""
            if object_name == "SalesProductCard":
                self._position_product_stock_circle(watched)
            elif object_name == "SalesProductDetails":
                self._adapt_product_details_layout(watched)
            if self._product_layout_mode == "table" and any(
                watched is target
                for target in (
                    getattr(self, "catalog_panel", None),
                    getattr(self, "catalog_results_stack", None),
                    getattr(self, "product_table", None),
                    getattr(getattr(self, "product_table", None), "viewport", lambda: None)(),
                    getattr(self, "splitter", None),
                    getattr(self, "sales_workspace", None),
                    getattr(self, "workspace_stack", None),
                )
            ):
                self._schedule_product_table_refit()
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and not self._show_product_add_button
            and self._product_layout_mode != "table"
        ):
            node = watched if isinstance(watched, QWidget) else None
            while node is not None and node is not self:
                if node.objectName() == "SalesProductCard":
                    product_key = str(node.property("salesProductKey") or "")
                    if product_key:
                        product = self._product_cache.get(product_key) or next(
                            (
                                item for item in self.products
                                if str(item.get("id") or "") == product_key
                            ),
                            None,
                        )
                        if product is not None:
                            self.add_to_cart(product)
                            return True
                    break
                node = node.parentWidget()
        if event.type() == QEvent.Type.Resize:
            if watched is getattr(self, "catalog_panel", None) or watched is getattr(self, "search", None):
                QTimer.singleShot(0, self._position_search_suggestions)
            elif watched is getattr(getattr(self, "catalog_scroll", None), "viewport", lambda: None)():
                QTimer.singleShot(0, self._reflow_products_for_resize)
            elif (
                watched is getattr(getattr(self, "product_table", None), "viewport", lambda: None)()
                or watched is getattr(self, "product_table", None)
            ):
                self._schedule_product_table_refit()
        return super().eventFilter(watched, event)

    def _position_product_stock_circle(self, card):
        badge = card.findChild(QLabel, "SalesProductStockCircle")
        if badge is None:
            return
        badge.move(max(4, card.width() - badge.width() - 6), 6)
        badge.raise_()

    def _adapt_product_details_layout(self, details_widget):
        details_layout = details_widget.layout()
        if details_layout is None:
            return
        stack = (
            bool(details_widget.property("stackStockBelowPrice"))
            or details_widget.width() < 380
        )
        direction = (
            QBoxLayout.Direction.TopToBottom if stack
            else QBoxLayout.Direction.LeftToRight
        )
        if details_layout.direction() != direction:
            details_layout.setDirection(direction)

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

    def _grid_column_count(self, width):
        """Honor an explicit column count; automatic mode adapts to available width."""
        width = max(260, int(width))
        if self._product_columns:
            return max(1, min(6, self._product_columns))
        return max(1, min(6, width // 165))

    def _schedule_product_table_refit(self):
        """Coalesce parent/table/viewport resizes and fit after Qt finishes layout."""
        timer = getattr(self, "_product_table_refit_timer", None)
        if timer is not None:
            timer.start()

    def _reflow_products_for_resize(self):
        if self._product_layout_mode == "table":
            self._schedule_product_table_refit()
            return
        if not getattr(self, "products", None) or self._product_layout_mode != "grid":
            return
        width = max(260, self.catalog_scroll.viewport().width())
        columns = self._grid_column_count(width)
        if columns != self._rendered_columns:
            self._render_products()

    def _search_text_changed(self, value):
        self._search_timer.stop()
        self._search_committed = False
        query = str(value or "").strip()
        self._suggestion_query = query
        if self._use_category_tabs and query:
            self._set_category_tab(None)
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

    def _commit_search(self):
        """Commit search. Tab mode searches across every category."""
        self._search_timer.stop()
        self._search_committed = True
        self.search_suggestions_frame.hide()
        self.product_page = 1
        if self._use_category_tabs and self.search.text().strip():
            self._set_category_tab(None)
        self.refresh_products()

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
                category_id=(
                    None if self._use_category_tabs
                    else self.category_combo.currentData()
                ),
                page=page,
                page_size=self._suggestion_page_size,
            ),
            lambda payload: self._show_search_suggestions(payload, query, page),
            failure=lambda error: self._search_suggestions_failed(error, query),
        )

    def _show_search_suggestions(self, payload, query, page):
        self.search_more_button.setEnabled(True)
        if self._search_committed:
            self.search_suggestions_frame.hide()
            return
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

    def _deselect_product_table_row(self):
        self.product_table.clearSelection()
        self.product_table.setCurrentCell(-1, -1)
        self._update_product_table_selection_controls()

    def _update_product_table_selection_controls(self, *_args):
        if not hasattr(self, "product_deselect_button"):
            return
        in_table_mode = getattr(self, "_product_layout_mode", "grid") == "table"
        self.product_deselect_button.setVisible(in_table_mode)
        table = getattr(self, "product_table", None)
        # Prefer a real selection; a valid current cell is also actionable because
        # Qt can move the current row without exposing it through selectedRows().
        selected = bool(
            table and (
                table.selectionModel().hasSelection()
                or table.currentIndex().isValid()
            )
        )
        self.product_deselect_button.setEnabled(in_table_mode and selected)

    def _schedule_product_table_column_adjustment(self, *_args):
        """Debounce manual header drags, without writing widths to persistent settings."""
        timer = getattr(self, "_product_table_column_adjust_timer", None)
        if timer is not None:
            timer.start()

    def _remember_manual_product_table_column_widths(self):
        """Use the user's latest drag as live weights, then refit to the viewport."""
        table = getattr(self, "product_table", None)
        if table is None:
            return
        widths = [
            max(1, int(table.columnWidth(column)))
            for column in range(table.columnCount())
        ]
        if widths:
            self._product_table_column_weights = widths
            self._fit_product_table_columns()

    def _fit_product_table_columns(self):
        """Fit visible columns to the viewport using this window's current proportions."""
        table = getattr(self, "product_table", None)
        if table is None:
            return
        viewport_width = int(table.viewport().width())
        if viewport_width <= 0 or table.columnCount() == 0:
            return

        visible = [
            column for column in range(table.columnCount())
            if not table.isColumnHidden(column)
        ]
        if not visible:
            return
        weights = list(getattr(self, "_product_table_column_weights", []) or [])
        if len(weights) != table.columnCount():
            weights = [116, 198, 95, 105, 90, 100][:table.columnCount()]
        weights = [max(1, int(width)) for width in weights]
        total_weight = sum(weights[column] for column in visible)
        if total_weight <= 0:
            return

        widths = {}
        remaining = viewport_width
        for column in visible[:-1]:
            width = max(1, int(viewport_width * weights[column] / total_weight))
            widths[column] = width
            remaining -= width
        widths[visible[-1]] = max(1, remaining)

        header = table.horizontalHeader()
        header.blockSignals(True)
        try:
            for column, width in widths.items():
                if table.columnWidth(column) != width:
                    table.setColumnWidth(column, width)
        finally:
            header.blockSignals(False)

        # Keep the thumbnail scaled to the width actually allocated to its column.
        # This prevents large fixed-size images from spilling into adjacent cells.
        if not self._show_product_images or table.isColumnHidden(0):
            return
        image_side = min(160, max(40, table.columnWidth(0) - 12))
        for row, product in enumerate(self.products):
            if row >= table.rowCount():
                break
            cell = table.cellWidget(row, 0)
            image = cell.findChild(QLabel, "SalesProductImage") if cell else None
            if image is None or image.width() != image_side:
                table.setCellWidget(
                    row, 0, self._build_product_table_image_cell(product, image_side)
                )
                table.setRowHeight(row, image_side + 14)

    def _category_changed(self, *_args):
        self.product_page = 1
        self.refresh_products()
        query = self.search.text().strip()
        if len(query) >= 2:
            self._search_text_changed(query)

    def _category_tab_changed(self, index):
        if not self._use_category_tabs or index < 0:
            return
        if self.search.text().strip():
            self._set_category_tab(None)
            return
        self.product_page = 1
        self.refresh_products()

    def _populate_category_tabs(self, preferred_id=None):
        bar = self.category_tabs
        bar.blockSignals(True)
        while bar.count():
            bar.removeTab(bar.count() - 1)
        bar.addTab("همهٔ دسته‌ها")
        bar.setTabData(0, None)
        target_index = 0
        for category in self.categories:
            category_id = category.get("id")
            if category_id is None:
                continue
            name = str(category.get("name") or "—")
            index = bar.addTab(name)
            bar.setTabData(index, category_id)
            bar.setTabToolTip(index, name)
            if preferred_id is not None and str(category_id) == str(preferred_id):
                target_index = index
        bar.setCurrentIndex(target_index)
        bar.blockSignals(False)

    def _set_category_tab(self, category_id):
        target = 0
        if category_id is not None:
            for index in range(self.category_tabs.count()):
                value = self.category_tabs.tabData(index)
                if value is not None and str(value) == str(category_id):
                    target = index
                    break
        self.category_tabs.blockSignals(True)
        self.category_tabs.setCurrentIndex(target)
        self.category_tabs.blockSignals(False)

    def _sync_category_selector(self, preferred_id=None):
        if preferred_id is None and hasattr(self, "category_combo"):
            preferred_id = self.category_combo.currentData()
        tabs_mode = bool(self._use_category_tabs)
        self.category_combo.setVisible(not tabs_mode)
        self.category_tabs.setVisible(tabs_mode)
        self.category_label.setVisible(not tabs_mode)
        if tabs_mode:
            self._set_category_tab(preferred_id)

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
        dialog.setMinimumSize(560, 600)
        dialog.resize(680, 700)
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
        zoom_image_checkbox = QCheckBox("بزرگ‌نمایی و برش تصویر برای پرکردن مربع")
        zoom_image_checkbox.setChecked(self._zoom_product_images)
        stock_checkbox = QCheckBox("نمایش موجودی کالا")
        stock_checkbox.setChecked(self._show_product_stock)
        category_tabs_checkbox = QCheckBox("نمایش دسته‌بندی‌ها به صورت تب")
        category_tabs_checkbox.setChecked(self._use_category_tabs)
        add_button_checkbox = QCheckBox("نمایش دکمهٔ افزودن به سبد در کارت‌ها (در جدول همیشه نمایش داده می‌شود)")
        add_button_checkbox.setChecked(self._show_product_add_button)
        stock_style_label = QLabel("شیوهٔ نمایش موجودی")
        stock_style_combo = QComboBox()
        stock_style_combo.addItem("متن موجودی کنار قیمت", "text")
        stock_style_combo.addItem("دایرهٔ عددی در گوشهٔ کارت", "circle")
        stock_style_combo.setCurrentIndex(
            max(0, stock_style_combo.findData(self._product_stock_display_style))
        )
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
        controls.addWidget(zoom_image_checkbox, 2, 0, 1, 2)
        controls.addWidget(stock_checkbox, 3, 0, 1, 2)
        controls.addWidget(add_button_checkbox, 4, 0, 1, 2)
        controls.addWidget(category_tabs_checkbox, 5, 0, 1, 2)
        controls.addWidget(stock_style_label, 6, 0)
        controls.addWidget(stock_style_combo, 6, 1)
        controls.addWidget(density_label, 7, 0)
        controls.addWidget(density_combo, 7, 1)
        controls.addWidget(columns_label, 8, 0)
        controls.addWidget(columns_combo, 8, 1)
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
                table_preview = QTableWidget(1, 6)
                table_preview.setObjectName("SalesProductTable")
                table_preview.setHorizontalHeaderLabels(
                    ["تصویر", "نام کالا", "دسته‌بندی", "قیمت", "موجودی", "عملیات"]
                )
                table_preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                table_preview.verticalHeader().setVisible(False)
                table_preview.horizontalHeader().setSectionResizeMode(
                    1, QHeaderView.ResizeMode.Stretch
                )
                for column in (0, 2, 3, 4, 5):
                    table_preview.horizontalHeader().setSectionResizeMode(
                        column, QHeaderView.ResizeMode.ResizeToContents
                    )
                table_preview.setColumnHidden(0, not image_checkbox.isChecked())
                table_preview.setColumnHidden(4, not stock_checkbox.isChecked())
                table_preview.setColumnHidden(5, False)
                image_side = 72 if density_combo.currentData() == "compact" else 84
                table_preview.setCellWidget(
                    0, 0,
                    self._build_product_table_image_cell(
                        sample, image_side, zoom_images=zoom_image_checkbox.isChecked()
                    ),
                )
                table_preview.setItem(
                    0, 1, QTableWidgetItem(str(sample.get("name") or "نمونهٔ کالا"))
                )
                category_name = self._category_names.get(
                    str(sample.get("category_id")), "—"
                )
                table_preview.setItem(0, 2, QTableWidgetItem(category_name))
                table_preview.setItem(
                    0, 3,
                    QTableWidgetItem("{:,.2f}".format(float(sample.get("sell_price") or 0))),
                )
                sample_key = str(sample.get("id") or "")
                capacity = self._stock_capacity(sample, sample_key)
                stock = max(
                    0,
                    capacity - int(self._cart.get(sample_key, {}).get("quantity", 0)),
                )
                stock_text = (
                    ("ناموجود" if stock <= 0 else "موجودی: {:g}".format(stock))
                    if sample.get("track_stock") else "آماده فروش"
                )
                stock_badge = QLabel(stock_text)
                stock_badge.setObjectName("SalesProductStock")
                stock_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                stock_badge.setProperty(
                    "outOfStock", bool(sample.get("track_stock") and stock <= 0)
                )
                table_preview.setCellWidget(0, 4, stock_badge)
                preview_add_button = QPushButton("افزودن")
                preview_add_button.setObjectName("SalesProductAddButton")
                preview_add_button.setEnabled(False)
                preview_add_button.setToolTip("پیش‌نمایش دکمهٔ افزودن به سبد")
                table_preview.setCellWidget(0, 5, preview_add_button)
                table_preview.setRowHeight(0, image_side + 14)
                table_preview.setMinimumHeight(image_side + 50)
                preview_layout.addWidget(table_preview)
                return
            card = self._build_product_card(
                sample, preview=True, layout_mode=mode,
                show_images=image_checkbox.isChecked(),
                density=density_combo.currentData(),
                show_stock=stock_checkbox.isChecked(),
                show_add_button=add_button_checkbox.isChecked(),
                stock_display_style=stock_style_combo.currentData(),
                zoom_images=zoom_image_checkbox.isChecked(),
            )
            # List and horizontal previews need full width so the price, stock and add
            # action remain visible instead of shrinking to sizeHint.
            preview_layout.addWidget(card, 1)

        mode_combo.currentIndexChanged.connect(rebuild_preview)
        image_checkbox.toggled.connect(rebuild_preview)
        zoom_image_checkbox.toggled.connect(rebuild_preview)
        stock_checkbox.toggled.connect(rebuild_preview)
        add_button_checkbox.toggled.connect(rebuild_preview)
        stock_style_combo.currentIndexChanged.connect(rebuild_preview)
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
                show_stock=stock_checkbox.isChecked(),
                show_add_button=add_button_checkbox.isChecked(),
                stock_display_style=stock_style_combo.currentData(),
                use_category_tabs=category_tabs_checkbox.isChecked(),
                zoom_images=zoom_image_checkbox.isChecked(),
            )
            dialog.accept()

        buttons.accepted.connect(apply_settings)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def _apply_product_display_settings(
        self, layout_mode, show_images, density, columns,
        show_stock=None, show_add_button=None, stock_display_style=None,
        use_category_tabs=None, zoom_images=None,
    ):
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

        previous_category = (
            self.category_tabs.tabData(self.category_tabs.currentIndex())
            if self._use_category_tabs and self.category_tabs.currentIndex() >= 0
            else self.category_combo.currentData()
        )
        self._product_layout_mode = layout_mode
        self._show_product_images = bool(show_images)
        if zoom_images is not None:
            self._zoom_product_images = bool(zoom_images)
        self._show_product_stock = (
            self._show_product_stock if show_stock is None else bool(show_stock)
        )
        self._show_product_add_button = (
            self._show_product_add_button
            if show_add_button is None else bool(show_add_button)
        )
        if use_category_tabs is not None:
            self._use_category_tabs = bool(use_category_tabs)
        if stock_display_style is not None:
            stock_display_style = str(stock_display_style or "text").strip().lower()
            self._product_stock_display_style = (
                stock_display_style if stock_display_style in {"text", "circle"} else "text"
            )
        self._product_card_density = density
        self._product_columns = columns
        self.product_deselect_button.setVisible(layout_mode == "table")
        self._update_product_table_selection_controls()
        self._sync_category_selector(previous_category)
        self._local_settings.setValue("sales/product_layout_mode", layout_mode)
        self._local_settings.setValue("sales/show_product_images", self._show_product_images)
        self._local_settings.setValue("sales/zoom_product_images", self._zoom_product_images)
        self._local_settings.setValue("sales/show_product_stock", self._show_product_stock)
        self._local_settings.setValue(
            "sales/show_product_add_button", self._show_product_add_button
        )
        self._local_settings.setValue(
            "sales/product_stock_display_style", self._product_stock_display_style
        )
        self._local_settings.setValue("sales/product_card_density", density)
        self._local_settings.setValue("sales/product_columns", columns)
        self._local_settings.setValue("sales/use_category_tabs", self._use_category_tabs)
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
        category_id = (
            self.category_tabs.tabData(self.category_tabs.currentIndex())
            if self._use_category_tabs and self.category_tabs.currentIndex() >= 0
            else self.category_combo.currentData()
        )
        if self._use_category_tabs and query:
            category_id = None
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

        selected_category = (
            self.category_tabs.tabData(self.category_tabs.currentIndex())
            if self._use_category_tabs and self.category_tabs.currentIndex() >= 0
            else self.category_combo.currentData()
        )
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
        self._populate_category_tabs(selected_category)
        self._sync_category_selector(selected_category)

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
            self._update_product_table_selection_controls()
            return

        self.catalog_results_stack.setCurrentWidget(self.catalog_scroll)
        width = max(260, self.catalog_scroll.viewport().width())
        if self._product_layout_mode in {"horizontal", "list"}:
            columns = 1
        else:
            columns = self._grid_column_count(width)
        self._rendered_columns = columns
        self.product_grid.setHorizontalSpacing(6 if self._product_card_density == "compact" else 10)
        self.product_grid.setVerticalSpacing(6 if self._product_card_density == "compact" else 10)
        for row in range(max(2, len(self.products) // columns + 3)):
            self.product_grid.setRowStretch(row, 0)
        for column in range(6):
            self.product_grid.setColumnStretch(column, 1 if column < columns else 0)
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

    def _build_product_table_image_cell(self, product, side, zoom_images=None):
        """Build a centered, square table thumbnail using the full available cell area."""
        side = max(36, int(side))
        target_side = max(24, side - 12)
        cell = QWidget()
        cell.setObjectName("SalesProductImageCell")
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(3, 3, 3, 3)
        cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        image = QLabel()
        image.setObjectName("SalesProductImage")
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setFixedSize(side, side)
        image.setToolTip(str(product.get("name") or "کالا"))
        raw_image = product.get("_image_bytes")
        pixmap = QPixmap()
        zoom = self._zoom_product_images if zoom_images is None else bool(zoom_images)
        if raw_image and pixmap.loadFromData(raw_image):
            aspect_mode = (
                Qt.AspectRatioMode.KeepAspectRatioByExpanding
                if zoom else Qt.AspectRatioMode.KeepAspectRatio
            )
            scaled = pixmap.scaled(
                target_side, target_side, aspect_mode,
                Qt.TransformationMode.SmoothTransformation,
            )
            if zoom:
                left = max(0, (scaled.width() - target_side) // 2)
                top = max(0, (scaled.height() - target_side) // 2)
                scaled = scaled.copy(left, top, target_side, target_side)
            image.setPixmap(scaled)
        else:
            image.setText("بدون تصویر")
        cell_layout.addWidget(image, 0, Qt.AlignmentFlag.AlignCenter)
        cell.setToolTip(str(product.get("name") or "کالا"))
        return cell

    def _render_product_table(self):
        """Render large product thumbnails and an explicit add-to-cart action per row."""
        table = self.product_table
        table.clearSpans()
        table.clearContents()
        table.setRowCount(len(self.products) if self.products else 1)
        table.setColumnHidden(0, not self._show_product_images)
        table.setColumnHidden(4, not self._show_product_stock)
        table.setColumnHidden(5, False)
        self._product_add_buttons = {}
        self._product_stock_labels = {}
        if not self.products:
            empty = QTableWidgetItem("کالایی مطابق فیلترها پیدا نشد.")
            empty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(0, 0, empty)
            table.setSpan(0, 0, 1, table.columnCount())
            table.setRowHeight(0, 52)
            QTimer.singleShot(0, self._fit_product_table_columns)
            return

        compact = self._product_card_density == "compact"
        image_side = 104  # Fill the image column even when other table controls are compact.
        row_height = image_side + 14 if self._show_product_images else (42 if compact else 52)
        for row, product in enumerate(self.products):
            key = str(product.get("id") or "")
            if self._show_product_images:
                image_cell = self._build_product_table_image_cell(product, image_side)
                table.setCellWidget(row, 0, image_cell)

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
            if self._show_product_stock:
                table.setCellWidget(row, 4, stock_badge)
                self._product_stock_labels[key] = stock_badge

            add_button = QPushButton("افزودن")
            add_button.setObjectName("SalesProductAddButton")
            add_button.setMinimumHeight(32)
            add_button.setAccessibleName(
                "افزودن {} به سبد خرید".format(product.get("name") or "کالا")
            )
            add_button.setToolTip(
                "افزودن {} به سبد خرید".format(product.get("name") or "کالا")
            )
            add_button.clicked.connect(
                lambda _checked=False, selected=product: self.add_to_cart(selected)
            )
            add_button.setEnabled(not tracked or available > 0)
            set_button_icon(add_button, "cart", getattr(self.window, "mode", "light"))
            table.setCellWidget(row, 5, add_button)
            self._product_add_buttons[key] = add_button

            table.setRowHeight(row, row_height)

        QTimer.singleShot(0, self._fit_product_table_columns)

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
        self, product, preview=False, layout_mode=None, show_images=None, density=None,
        show_stock=None, show_add_button=None, stock_display_style=None, zoom_images=None,
    ):
        """Build a product card for the catalog or a side-effect-free settings preview."""
        key = str(product.get("id") or "")
        mode = str(layout_mode or self._product_layout_mode)
        show_images = self._show_product_images if show_images is None else bool(show_images)
        zoom_images = self._zoom_product_images if zoom_images is None else bool(zoom_images)
        density = str(density or self._product_card_density)
        show_stock = self._show_product_stock if show_stock is None else bool(show_stock)
        show_add_button = (
            self._show_product_add_button
            if show_add_button is None else bool(show_add_button)
        )
        stock_display_style = str(
            stock_display_style or self._product_stock_display_style
        ).strip().lower()
        if stock_display_style not in {"text", "circle"}:
            stock_display_style = "text"
        compact = density == "compact"
        horizontal = mode in {"horizontal", "list"}

        card = QFrame()
        card.setObjectName("SalesProductCard")
        card.setProperty("displayMode", mode)
        card.setFrameShape(QFrame.Shape.NoFrame)
        card.setProperty("salesProductPreview", bool(preview))
        card.installEventFilter(self)
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if mode == "grid":
            # Fixed columns remain responsive but must not create arbitrarily wide cards.
            card.setMaximumWidth(280 if compact else 320)
            card_layout = QVBoxLayout(card)
        else:
            card.setMaximumWidth(16777215)
            card.setMinimumHeight(72 if mode == "list" else 94)
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
            if mode == "list":
                target = (48, 48)
            elif mode == "grid":
                side = 68 if compact else 82
                target = (side, side)
            else:
                target = (76, 76)
            if image_bytes and pixmap.loadFromData(image_bytes):
                if zoom_images:
                    # Fill the square and crop symmetrically around the image centre.
                    scaled = pixmap.scaled(
                        target[0], target[1],
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    left = max(0, (scaled.width() - target[0]) // 2)
                    top = max(0, (scaled.height() - target[1]) // 2)
                    image.setPixmap(scaled.copy(left, top, target[0], target[1]))
                else:
                    image.setPixmap(pixmap.scaled(
                        target[0], target[1], Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    ))
            else:
                image.setText("بدون تصویر")
            image.setFixedSize(target[0], target[1])

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
        available = (
            max(0, capacity - int(self._cart.get(key, {}).get("quantity", 0)))
            if not preview else capacity
        )
        stock_badge = None
        if show_stock:
            if stock_display_style == "circle":
                stock_text = str(available) if tracked else "∞"
                stock_badge = QLabel(stock_text, card)
                stock_badge.setObjectName("SalesProductStockCircle")
                stock_badge.setFixedSize(32, 32)
                stock_badge.setToolTip(
                    ("موجودی قابل فروش: {:g}".format(available))
                    if tracked else "این کالا محدودیت موجودی ندارد"
                )
            else:
                stock_text = (
                    ("ناموجود" if available <= 0 else "موجودی: {:g}".format(available))
                    if tracked else "آماده فروش"
                )
                stock_badge = QLabel(stock_text)
                stock_badge.setObjectName("SalesProductStock")
            stock_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stock_badge.setProperty("outOfStock", bool(tracked and available <= 0))
            if stock_display_style == "circle":
                stock_badge.show()
                stock_badge.raise_()

        add = None
        if show_add_button:
            add = QPushButton("افزودن به سبد" if mode != "list" else "افزودن")
            add.setObjectName("SalesProductAddButton")
            add.setMinimumHeight(25 if compact else 29)
            add.setToolTip("افزودن {} به سبد خرید".format(product.get("name") or "کالا"))
            if preview:
                add.setEnabled(False)
            else:
                add.clicked.connect(lambda _checked=False, selected=product: self.add_to_cart(selected))
                add.setEnabled(not tracked or available > 0)
                self._product_add_buttons[key] = add
                set_button_icon(add, "cart", getattr(self.window, "mode", "light"))

        if not preview:
            if stock_badge is not None:
                self._product_stock_labels[key] = stock_badge
            if not show_add_button and key:
                card.setProperty("salesProductKey", key)

        if mode == "grid":
            if image is not None:
                card_layout.addWidget(image)
            card_layout.addWidget(name)
            if category is not None:
                card_layout.addWidget(category)
            card_layout.addWidget(price)
            if stock_badge is not None and stock_badge.objectName() == "SalesProductStock":
                card_layout.addWidget(stock_badge)
            if add is not None:
                card_layout.addWidget(add)
        elif mode == "list":
            # Single full-width row with a dedicated add-action column. Keeping the
            # action outside the details layout prevents it from being clipped.
            if image is not None:
                card_layout.addWidget(image, 0, Qt.AlignmentFlag.AlignVCenter)
            info = QWidget(card)
            info.setObjectName("SalesProductInfo")
            info_layout = QVBoxLayout(info)
            info_layout.setContentsMargins(3, 0, 3, 0)
            info_layout.setSpacing(2 if compact else 4)
            info_layout.addWidget(name)
            if category is not None:
                info_layout.addWidget(category)
            details_widget = QWidget(info)
            details_widget.setObjectName("SalesProductDetails")
            details_widget.setProperty("stackStockBelowPrice", not show_add_button)
            details = QHBoxLayout(details_widget)
            details.setContentsMargins(0, 0, 0, 0)
            details.setSpacing(7 if compact else 10)
            details.addWidget(price)
            if stock_badge is not None and stock_badge.objectName() == "SalesProductStock":
                details.addWidget(stock_badge)
            details.addStretch(1)
            details_widget.installEventFilter(self)
            info_layout.addWidget(details_widget)
            card_layout.addWidget(info, 1)
            if add is not None:
                add.setMinimumWidth(88)
                add.setMaximumWidth(112)
                card_layout.addWidget(add, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            if image is not None:
                card_layout.addWidget(image, 0, Qt.AlignmentFlag.AlignVCenter)
            info = QWidget(card)
            info.setObjectName("SalesProductInfo")
            info_layout = QVBoxLayout(info)
            info_layout.setContentsMargins(3, 0, 3, 0)
            info_layout.setSpacing(2 if compact else 4)
            info_layout.addWidget(name)
            if category is not None:
                info_layout.addWidget(category)
            details_widget = QWidget(info)
            details_widget.setObjectName("SalesProductDetails")
            details_widget.setProperty("stackStockBelowPrice", not show_add_button)
            details = QHBoxLayout(details_widget)
            details.setContentsMargins(0, 0, 0, 0)
            details.setSpacing(12 if not compact else 7)
            details.addWidget(price)
            if stock_badge is not None and stock_badge.objectName() == "SalesProductStock":
                details.addWidget(stock_badge)
            details.addStretch(1)
            details_widget.installEventFilter(self)
            info_layout.addWidget(details_widget)
            if add is not None:
                info_layout.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
            card_layout.addWidget(info, 1)

        if stock_badge is not None and stock_badge.objectName() == "SalesProductStockCircle":
            self._position_product_stock_circle(card)
        if not preview and not show_add_button and key and mode != "table":
            for child in card.findChildren(QWidget):
                child.installEventFilter(self)
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
                if stock_badge.objectName() == "SalesProductStockCircle":
                    stock_badge.setText(str(available) if tracked else "∞")
                    stock_badge.setToolTip(
                        ("موجودی قابل فروش: {:g}".format(available))
                        if tracked else "این کالا محدودیت موجودی ندارد"
                    )
                else:
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
        self.cart_status_label.setText(
            str(units) if self._cart_collapsed
            else "{} نوع · {} عدد".format(item_kinds, units)
        )
        self.cart_status_label.setToolTip(
            "{} عدد در سبد خرید · {} نوع کالا".format(units, item_kinds)
        )
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
        """Persist pane proportions and reflow products for the active display mode."""
        sizes = self.splitter.sizes()
        if not self._cart_collapsed and len(sizes) == 2 and all(size > 0 for size in sizes):
            self._saved_splitter_sizes = sizes
            self._local_settings.setValue("sales/splitter_sizes", sizes)
        self._reflow_products_for_resize()

    def _reflow_product_grid(self):
        """Compatibility alias for older callers; respect the selected catalog layout."""
        self._reflow_products_for_resize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_search_suggestions()
        self._reflow_products_for_resize()

    def showEvent(self, event):
        super().showEvent(event)
        # A page revealed from a stacked widget may receive its final geometry
        # after the parent resize event; ensure the visible table catches up.
        self._schedule_product_table_refit()

    def checkout(self):
        items = self.collect_items()
        if not items:
            self.window.show_error("برای ثبت فروش حداقل یک تعداد مثبت وارد کنید.")
            return

        editing = self._editing_receipt_id is not None
        if editing:
            prompt = "تغییرات فاکتور {} ذخیره شود؟ مبلغ و موجودی دوباره در سرور اعتبارسنجی می‌شوند.".format(
                (self._editing_receipt or {}).get("invoice_number")
                or (self._editing_receipt or {}).get("day_receipt_id")
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
                receipt.get("invoice_number") or receipt.get("day_receipt_id", "—"),
                float(receipt.get("total_price") or 0),
            )
        else:
            message = "فروش شمارهٔ {} با مبلغ {:,.2f} ثبت شد.".format(
                receipt.get("invoice_number") or receipt.get("day_receipt_id", "—"),
                float(receipt.get("total_price") or 0),
            )        self.window.set_status(message)
        self.refresh_products()
        refresh_dashboard = getattr(self.window, "refresh_dashboard_data", None)
        if callable(refresh_dashboard):
            refresh_dashboard()
        receipts_page = getattr(self.window, "receipts_page", None)
        if receipts_page is not None:
            receipts_page.refresh()
        self._show_sale_invoice(receipt, updated=updated)

    def _show_sale_invoice(self, receipt, updated=False):
        """Load the admin-created sales invoice template for both preview and printing."""
        if not self.window.api:
            self.window.show_error(
                "فروش ثبت شد، اما برای دریافت قالب فاکتور ذخیره‌شده، اتصال سرور در دسترس نیست. "
                "از بخش رسیدها برای تلاش دوباره استفاده کنید."
            )
            return
        self.window.run_api(
            lambda: self.window.api.get_invoice_template(
                kind=SALES_INVOICE_TEMPLATE_KIND
            ),
            lambda template: self._present_invoice(
                receipt, template, auto_print=not updated
            ),
            failure=lambda error: self.window.show_error(
                "فروش ثبت شد، اما قالب «فاکتور فروش» ذخیره‌شده در تنظیمات ادمین بارگذاری نشد؛ "
                "برای جلوگیری از نمایش/چاپ با قالب اشتباه، عملیات انجام نشد. {}".format(error)
            ),
        )

    def _present_invoice(self, receipt, template, auto_print=True):
        if auto_print:
            auto_print_invoice(receipt, template, self.window)
        InvoiceDialog(receipt, template, self.window).exec()

    def _build_recent_receipts_workspace(self):
        """Build invoice mode with selectable history on the right and live preview beside it."""
        page = QFrame(self.workspace_stack)
        page.setObjectName("RecentInvoicesWorkspace")
        page.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.history_splitter = QSplitter(Qt.Orientation.Horizontal, page)
        self.history_splitter.setObjectName("RecentInvoicesSplitter")
        self.history_splitter.setChildrenCollapsible(False)
        self.history_splitter.setHandleWidth(6)
        self.history_splitter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        list_panel = QFrame()
        list_panel.setObjectName("Card")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(6)
        history_heading = QHBoxLayout()
        self.history_title = QLabel("فاکتورهای اخیر", list_panel)
        self.history_title.setObjectName("PageTitle")
        self.history_refresh_button = QPushButton("", list_panel)
        self.history_refresh_button.setObjectName("HistoryRefreshButton")
        self.history_refresh_button.setFixedSize(32, 32)
        self.history_refresh_button.setToolTip("بازخوانی فاکتورها")
        self.history_refresh_button.setAccessibleName("بازخوانی فاکتورها")
        set_button_icon(
            self.history_refresh_button, "refresh", getattr(self.window, "mode", "light")
        )
        self.history_refresh_button.clicked.connect(
            lambda: self._load_recent_receipt_page(1, append=False)
        )
        history_heading.addWidget(self.history_title)
        history_heading.addStretch(1)
        self.history_deselect_button = QPushButton("", list_panel)
        self.history_deselect_button.setObjectName("HistoryDeselectButton")
        self.history_deselect_button.setFixedSize(32, 32)
        self.history_deselect_button.setToolTip("لغو انتخاب فاکتور")
        self.history_deselect_button.setAccessibleName("لغو انتخاب فاکتور")
        set_button_icon(self.history_deselect_button, "clear", getattr(self.window, "mode", "light"))
        self.history_deselect_button.setEnabled(False)
        self.history_deselect_button.clicked.connect(self._deselect_recent_receipt)
        self.history_preview_reopen_button = QPushButton("", list_panel)
        self.history_preview_reopen_button.setObjectName("HistoryPreviewToggleButton")
        self.history_preview_reopen_button.setFixedSize(32, 32)
        self.history_preview_reopen_button.setToolTip("بازکردن پیش‌نمایش فاکتور")
        self.history_preview_reopen_button.setAccessibleName("باز یا بستن پیش‌نمایش فاکتور")
        set_button_icon(self.history_preview_reopen_button, "next", getattr(self.window, "mode", "light"))
        self.history_preview_reopen_button.clicked.connect(self._toggle_history_preview)
        # RTL placement puts the preview toggle just left of the refresh button.
        history_heading.addWidget(self.history_deselect_button)
        history_heading.addWidget(self.history_refresh_button)
        history_heading.addWidget(self.history_preview_reopen_button)
        list_layout.addLayout(history_heading)

        search_row = QHBoxLayout()
        self.history_search_input = QLineEdit(list_panel)
        self.history_search_input.setObjectName("RecentInvoicesSearch")
        self.history_search_input.setPlaceholderText(
            "شماره، شناسه، تاریخ، مبلغ، میز، روش پرداخت یا نام کالا…"
        )
        self.history_search_input.setClearButtonEnabled(True)
        self.history_search_input.returnPressed.connect(self._commit_recent_receipt_search)
        self.history_search_timer = QTimer(self)
        self.history_search_timer.setSingleShot(True)
        self.history_search_timer.setInterval(350)
        self.history_search_timer.timeout.connect(self._commit_recent_receipt_search)
        self.history_search_input.textChanged.connect(
            lambda _value: self.history_search_timer.start()
        )
        self.history_search_button = QPushButton("جست‌وجو", list_panel)
        self.history_search_button.setObjectName("SalesToolbarButton")
        self.history_search_button.setToolTip("جست‌وجوی فاکتورها")
        self.history_search_button.clicked.connect(self._commit_recent_receipt_search)
        search_row.addWidget(self.history_search_input, 1)
        search_row.addWidget(self.history_search_button)
        list_layout.addLayout(search_row)

        self.history_tabs = QTabWidget(list_panel)
        self.history_tabs.setObjectName("RecentInvoicesTabs")
        self.history_tabs.setDocumentMode(True)
        self.history_tabs.currentChanged.connect(self._update_history_deselect_state)
        list_layout.addWidget(self.history_tabs, 1)

        self._history_tables = {}
        self._history_tab_labels = {}
        tab_specs = (
            ("all", "همهٔ فاکتورها"),
            ("unpaid", "پرداخت‌نشده"),
            ("paid", "پرداخت‌شده"),
        )
        for key, label in tab_specs:
            tab = QWidget(self.history_tabs)
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(2, 4, 2, 2)
            table = QTableWidget(0, 7, tab)
            table.setObjectName("RecentInvoicesTable")
            table.setHorizontalHeaderLabels([
                "شناسه", "شماره فاکتور", "وضعیت", "تاریخ", "میز / صندلی", "مبلغ", "روش پرداخت"
            ])
            table.setColumnHidden(0, True)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setWordWrap(False)
            table.cellDoubleClicked.connect(
                lambda _row, _column: self._preview_selected_recent_receipt()
            )
            table.itemSelectionChanged.connect(
                lambda *_args, selected_table=table: self._update_history_deselect_state(selected_table)
            )
            table.currentCellChanged.connect(
                lambda *_args, selected_table=table: self._update_history_deselect_state(selected_table)
            )
            table.cellClicked.connect(
                lambda *_args, selected_table=table: self._update_history_deselect_state(selected_table)
            )
            tab_layout.addWidget(table, 1)
            hint = QLabel("")
            hint.setObjectName("PageSubtitle")
            tab_layout.addWidget(hint)
            self.history_tabs.addTab(tab, label)
            self._history_tables[key] = table
            self._history_tab_labels[key] = (hint, label)

        actions = QHBoxLayout()
        self.history_status = QLabel("فاکتورها هنوز بارگذاری نشده‌اند.")
        self.history_status.setObjectName("PageSubtitle")
        self.history_status.setWordWrap(True)
        self.history_load_more_button = QPushButton("بارگذاری بیشتر")
        self.history_load_more_button.setObjectName("SalesToolbarButton")
        self.history_load_more_button.setToolTip("دریافت صفحهٔ بعدی فاکتورها")
        self.history_load_more_button.clicked.connect(
            lambda: self._load_recent_receipt_page(self._history_current_page + 1, append=True)
        )
        self.history_preview_button = QPushButton("پیش‌نمایش فاکتور")
        self.history_preview_button.setObjectName("PrimaryButton")
        self.history_preview_button.clicked.connect(self._preview_selected_recent_receipt)
        self.history_edit_button = QPushButton("بارگذاری برای ویرایش")
        self.history_edit_button.setObjectName("PrimaryButton")
        self.history_edit_button.setVisible(self._can_edit_receipts)
        self.history_edit_button.clicked.connect(self._edit_selected_recent_receipt)
        actions.addWidget(self.history_status, 1)
        actions.addWidget(self.history_load_more_button)
        actions.addWidget(self.history_preview_button)
        actions.addWidget(self.history_edit_button)
        list_layout.addLayout(actions)

        preview_panel = QFrame()
        preview_panel.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(6)
        preview_heading = QHBoxLayout()
        preview_title = QLabel("پیش‌نمایش فاکتور")
        preview_title.setObjectName("PageTitle")
        self.history_preview_status = QPushButton("شماره: —")
        self.history_preview_status.setObjectName("HistoryInvoiceNumberPill")
        self.history_preview_status.setToolTip("بعد از انتخاب فاکتور، برای کپی شناسه کلیک کنید.")
        self.history_preview_status.setEnabled(False)
        self.history_preview_status.clicked.connect(self._copy_history_invoice_id)
        self.history_export_button = QPushButton("", preview_panel)
        self.history_export_button.setObjectName("HistoryExportButton")
        self.history_export_button.setFixedSize(32, 32)
        self.history_export_button.setToolTip("ذخیرهٔ فاکتور به PDF، PNG یا JPG")
        self.history_export_button.setAccessibleName("ذخیرهٔ فاکتور به فایل")
        set_button_icon(self.history_export_button, "download", getattr(self.window, "mode", "light"))
        self.history_export_button.setEnabled(False)
        self.history_export_button.clicked.connect(self._open_history_export_menu)
        self.history_preview_close_button = QPushButton("", preview_panel)
        self.history_preview_close_button.setObjectName("HistoryPreviewToggleButton")
        self.history_preview_close_button.setFixedSize(32, 32)
        self.history_preview_close_button.setToolTip("لغو پیش‌نمایش فاکتور")
        self.history_preview_close_button.setAccessibleName("لغو پیش‌نمایش فاکتور")
        set_button_icon(self.history_preview_close_button, "clear", getattr(self.window, "mode", "light"))
        self.history_preview_close_button.clicked.connect(self._deselect_recent_receipt)
        preview_heading.addWidget(self.history_preview_close_button)
        preview_heading.addWidget(preview_title)
        preview_heading.addWidget(self.history_preview_status, 1)
        preview_heading.addWidget(self.history_export_button)
        preview_layout.addLayout(preview_heading)
        self.history_invoice_preview = InvoicePreviewWidget(preview_panel)
        self.history_invoice_preview.setMinimumWidth(300)
        self.history_invoice_preview.clear_invoice()
        preview_layout.addWidget(self.history_invoice_preview, 1)

        # In RTL, the first child appears on the right and the preview remains
        # adjacent to the invoice list rather than opening a separate dialog.
        self.history_splitter.addWidget(list_panel)
        self.history_splitter.addWidget(preview_panel)
        self.history_splitter.setStretchFactor(0, 3)
        self.history_splitter.setStretchFactor(1, 2)
        self._history_splitter_sizes = self._local_settings.value(
            "sales/history_splitter_sizes", [780, 520]
        )
        try:
            self._history_splitter_sizes = [
                max(1, int(self._history_splitter_sizes[0])),
                max(1, int(self._history_splitter_sizes[1])),
            ]
        except (TypeError, ValueError, IndexError):
            self._history_splitter_sizes = [780, 520]
        self.history_splitter.setSizes(self._history_splitter_sizes)
        self.history_splitter.splitterMoved.connect(self._history_splitter_moved)
        root.addWidget(self.history_splitter, 1)
        self._update_history_deselect_state()
        return page

    def _filtered_recent_receipts(self, key):
        if key == "unpaid":
            return [record for record in self._history_records if not bool(record.get("payed"))]
        if key == "paid":
            return [record for record in self._history_records if bool(record.get("payed"))]
        return list(self._history_records)

    def _render_recent_receipt_tables(self):
        for key, table in self._history_tables.items():
            records = self._filtered_recent_receipts(key)
            table.setRowCount(0)
            for row, record in enumerate(records):
                table.insertRow(row)
                receipt_id = str(record.get("id") or "")
                number = record.get("invoice_number") or record.get("day_receipt_id") or receipt_id[:8] or "—"
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
            hint, label = self._history_tab_labels[key]
            hint.setText("{} فاکتور در این تب".format(len(records)))
            index = self.history_tabs.indexOf(table.parentWidget())
            self.history_tabs.setTabText(index, "{} ({})".format(label, len(records)))

        unpaid_count = sum(not bool(record.get("payed")) for record in self._history_records)
        paid_count = len(self._history_records) - unpaid_count
        self.history_status.setText(
            "{} از {} فاکتور بارگذاری شده · {} پرداخت‌نشده · {} پرداخت‌شده".format(
                len(self._history_records), self._history_total_records, unpaid_count, paid_count
            )
        )
        has_more = len(self._history_records) < self._history_total_records
        self.history_load_more_button.setVisible(has_more)
        self.history_load_more_button.setEnabled(has_more)

    def _populate_recent_receipts(self, payload, append=False):
        incoming = list(payload.get("items") or [])
        if not append:
            self._history_records = []
        known_ids = {str(record.get("id") or "") for record in self._history_records}
        for record in incoming:
            record_id = str(record.get("id") or "")
            if record_id and record_id not in known_ids:
                self._history_records.append(record)
                known_ids.add(record_id)
        try:
            self._history_total_records = max(
                0, int(payload.get("total", len(self._history_records)) or 0)
            )
            self._history_current_page = max(
                1, int(payload.get("page", self._history_current_page or 1) or 1)
            )
        except (TypeError, ValueError):
            self._history_total_records = len(self._history_records)
            self._history_current_page = max(1, self._history_current_page or 1)
        self._history_loaded = True
        self._render_recent_receipt_tables()

    def _commit_recent_receipt_search(self):
        self.history_search_timer.stop()
        self._history_search_query = self.history_search_input.text().strip()
        self._history_current_page = 0
        self._deselect_recent_receipt()
        self._load_recent_receipt_page(1, append=False)

    def _load_recent_receipt_page(self, page, append=False):
        if not self.window.api:
            self.history_status.setText("برای دریافت فاکتورها ابتدا به سرور وصل شوید.")
            return
        query = self.history_search_input.text().strip()
        self._history_search_query = query
        if not append:
            self.history_status.setText("در حال جست‌وجو و بارگذاری فاکتورها…")
            self.history_refresh_button.setEnabled(False)
        self.history_load_more_button.setEnabled(False)
        self.window.run_api(
            lambda: self.window.api.list_recent_receipts_page(
                q=query or None, page=page, page_size=self._history_page_size
            ),
            lambda payload, requested_query=query: (
                self._populate_recent_receipts(payload, append=append)
                if requested_query == self.history_search_input.text().strip() else None
            ),
            failure=lambda error: (
                self.history_status.setText("دریافت فاکتورها ناموفق بود."),
                QMessageBox.warning(self.history_workspace, "خطای دریافت فاکتورها", str(error)),
                self.history_load_more_button.setEnabled(True),
            ),
            busy=self.history_load_more_button if append else self.history_refresh_button,
        )

    def _history_splitter_moved(self, *_args):
        sizes = self.history_splitter.sizes()
        if not self._history_preview_collapsed and len(sizes) == 2 and all(size > 0 for size in sizes):
            self._history_splitter_sizes = sizes
            self._local_settings.setValue("sales/history_splitter_sizes", sizes)

    def _toggle_history_preview(self):
        self._set_history_preview_visible(self._history_preview_collapsed)

    def _set_history_preview_visible(self, visible):
        visible = bool(visible)
        if visible == (not self._history_preview_collapsed):
            return
        preview_panel = self.history_splitter.widget(1)
        sizes = self.history_splitter.sizes()
        if visible:
            self._history_preview_collapsed = False
            self._local_settings.setValue("sales/history_preview_collapsed", False)
            preview_panel.show()
            self.history_preview_close_button.setVisible(bool(self._history_invoice_payload))
            self.history_preview_reopen_button.setToolTip("بستن پیش‌نمایش فاکتور")
            self.history_preview_reopen_button.setAccessibleName("بستن پیش‌نمایش فاکتور")
            set_button_icon(self.history_preview_reopen_button, "previous", getattr(self.window, "mode", "light"))
            self.history_splitter.setSizes(self._history_splitter_sizes or [780, 520])
        else:
            if len(sizes) == 2 and sizes[1] > 0 and sum(sizes) > 200:
                self._history_splitter_sizes = sizes
                self._local_settings.setValue("sales/history_splitter_sizes", sizes)
            self._history_preview_collapsed = True
            self._local_settings.setValue("sales/history_preview_collapsed", True)
            preview_panel.hide()
            self.history_preview_close_button.hide()
            self.history_preview_reopen_button.setToolTip("بازکردن پیش‌نمایش فاکتور")
            self.history_preview_reopen_button.setAccessibleName("بازکردن پیش‌نمایش فاکتور")
            set_button_icon(self.history_preview_reopen_button, "next", getattr(self.window, "mode", "light"))
            self.history_splitter.setSizes([max(1, sum(sizes)), 0])
        self._local_settings.sync()

    def _update_history_deselect_state(self, selected_table=None, *_args):
        if not hasattr(self, "history_deselect_button"):
            return
        # Selection can remain in a tab while Qt is switching widgets. The X clears
        # every tab's selection, so enable it when any table has a current/selected row.
        tables = list(getattr(self, "_history_tables", {}).values())
        if isinstance(selected_table, QTableWidget) and selected_table not in tables:
            tables.append(selected_table)
        selected = any(
            table.currentIndex().isValid()
            or table.selectionModel().hasSelection()
            or table.currentRow() >= 0
            for table in tables
        )
        self.history_deselect_button.setEnabled(selected)

    def _current_history_table(self):
        current = self.history_tabs.currentWidget()
        return next(
            (table for table in self._history_tables.values() if table.parentWidget() is current),
            None,
        )

    def _deselect_recent_receipt(self):
        for table in self._history_tables.values():
            table.clearSelection()
            table.setCurrentCell(-1, -1)
        self._history_invoice_payload = None
        self.history_invoice_preview.clear_invoice()
        self.history_preview_close_button.hide()
        self.history_preview_status.setText("شماره: —")
        self.history_preview_status.setProperty("receiptId", "")
        self.history_preview_status.setToolTip("ابتدا یک فاکتور را پیش‌نمایش کنید.")
        self.history_preview_status.setEnabled(False)
        self.history_export_button.setEnabled(False)
        self._update_history_deselect_state()

    def _copy_history_invoice_id(self):
        receipt_id = str(self.history_preview_status.property("receiptId") or "")
        if receipt_id:
            QApplication.clipboard().setText(receipt_id)
            self.history_preview_status.setToolTip("شناسه کپی شد: {}".format(receipt_id))

    def _open_history_export_menu(self):
        if not self._history_invoice_payload:
            return
        menu = QMenu(self.history_export_button)
        for label, fmt in (
            ("PDF · همهٔ صفحات", "pdf"),
            ("PNG · تصویر باکیفیت", "png"),
            ("JPG · تصویر", "jpg"),
        ):
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, selected=fmt: self.history_invoice_preview.export_invoice(selected)
            )
        menu.exec(self.history_export_button.mapToGlobal(QPoint(0, self.history_export_button.height())))

    def _selected_recent_receipt(self):
        current = self.history_tabs.currentWidget()
        key = next(
            (name for name, table in self._history_tables.items() if table.parentWidget() is current),
            "all",
        )
        table = self._history_tables[key]
        row = table.currentRow()
        cell = table.item(row, 0) if row >= 0 else None
        return cell.data(Qt.ItemDataRole.UserRole) if cell is not None else None

    def _preview_selected_recent_receipt(self):
        record = self._selected_recent_receipt()
        if not record:
            self.history_preview_status.setText("ابتدا یک فاکتور را از فهرست انتخاب کنید.")
            self.history_preview_status.setProperty("receiptId", "")
            self.history_preview_status.setEnabled(False)
            self.history_export_button.setEnabled(False)
            return
        self.history_preview_status.setText("در حال آماده‌سازی پیش‌نمایش…")
        self.history_preview_status.setProperty("receiptId", "")
        self.history_preview_status.setEnabled(False)
        self.history_export_button.setEnabled(False)
        self.window.run_api(
            lambda: self._load_recent_invoice(record["id"]),
            self._set_history_invoice_preview,
            failure=lambda error: QMessageBox.warning(
                self.history_workspace, "خطای دریافت فاکتور", str(error)
            ),
            busy=self.history_preview_button,
        )

    def _set_history_invoice_preview(self, payload):
        self._history_invoice_payload = payload
        if self._history_preview_collapsed:
            self._set_history_preview_visible(True)
        receipt = payload.get("receipt") or {}
        number = receipt.get("invoice_number") or receipt.get("day_receipt_id") or str(receipt.get("id") or "")[:8] or "—"
        receipt_id = str(receipt.get("id") or "")
        self.history_preview_status.setText("شماره: {}".format(number))
        self.history_preview_status.setProperty("receiptId", receipt_id)
        self.history_preview_status.setToolTip(
            "شناسهٔ کامل: {}\nبرای کپی شناسه کلیک کنید.".format(receipt_id)
        )
        self.history_preview_status.setEnabled(bool(receipt_id))
        self.history_export_button.setEnabled(bool(receipt_id))
        self.history_preview_close_button.setVisible(
            not self._history_preview_collapsed and bool(receipt_id)
        )
        self.history_invoice_preview.set_invoice(
            receipt, payload.get("template") or DEFAULT_TEMPLATE
        )

    def _edit_selected_recent_receipt(self):
        record = self._selected_recent_receipt()
        if not record:
            self.history_preview_status.setText("ابتدا فاکتوری را برای ویرایش انتخاب کنید.")
            return
        self.window.run_api(
            lambda: self._load_recent_invoice(record["id"], include_template=False),
            lambda payload: self._load_invoice_into_editor(payload),
            failure=lambda error: QMessageBox.warning(
                self.history_workspace, "خطای بارگذاری برای ویرایش", str(error)
            ),
            busy=self.history_edit_button,
        )

    def _load_recent_invoice(self, receipt_id, *, include_template=True):
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
        # The POS preview uses exactly the saved "فاکتور فروش" design. Do not
        # silently replace it with a default layout if template retrieval fails.
        template = (
            api.get_invoice_template(kind=SALES_INVOICE_TEMPLATE_KIND)
            if include_template else None
        )
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
                receipt.get("invoice_number") or receipt.get("day_receipt_id") or receipt_id[:8]
            )
        )
        if dialog is not None:
            dialog.accept()
        else:
            self.set_workspace_mode("sales")
        return True

    def _show_recent_invoice(self, payload, dialog=None):
        """Keep callers compatible while previewing inside the recent-invoice workspace."""
        self._set_history_invoice_preview(payload)
