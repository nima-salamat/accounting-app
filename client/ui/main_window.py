"""Main API-first PySide6 application shell with role-aware navigation."""
import os
import uuid

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
try:
    import qtawesome as qta
except ImportError:  # Keep the interface usable before optional icon assets are installed.
    qta = None
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from client.api_client import AccountingApiClient, ApiError
from client.ui.admin_pages import SchemaPage, SessionsPage
from client.ui.auth_page import AuthPage
from client.ui.dashboard_page import DashboardPage
from client.ui.data_pages import (
    CategoriesPage, ChecksPage, ProductsPage, ReceiptsPage, UsersPage,
    WarehousePage,
)
from client.ui.sales_page import SalesPage
from client.ui.settings_page import SettingsPage
from client.ui.permissions_page import PermissionsPage
from client.ui.invoice_templates_page import InvoiceTemplatesPage
from client.ui.inventory_page import InventoryPage
from client.ui.returns_page import ReturnsPage
from client.ui.accounting_pages import JournalsPage, FiscalYearsPage, AccountingReportsPage, AuditPage
from client.ui.global_search import GlobalSearchDialog
from client.ui.stocktakes_page import StocktakesPage
from client.ui.permissions import can_access
from client.ui.theme import stylesheet
from client.ui.worker import ApiWorker


class AdminOverviewPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window=window
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout=QVBoxLayout(self);layout.setContentsMargins(22,22,22,22);layout.setSpacing(18)
        title=QLabel("مرکز مدیریت");title.setObjectName("PageTitle")
        sub=QLabel("وضعیت حساب‌ها و نشست‌های دستگاه‌ها را از سرور کنترل کنید. اعمال این صفحه در سمت API enforce می‌شود.")
        sub.setObjectName("PageSubtitle");sub.setWordWrap(True)
        layout.addWidget(title);layout.addWidget(sub)
        self.metric_layout=QHBoxLayout();self.metric_layout.setSpacing(12)
        self.metric_labels={}
        for key,label in [
            ("users_total","کل حساب‌ها"),("users_active","حساب فعال"),
            ("users_disabled","حساب غیرفعال"),("sessions_pending","در انتظار تأیید"),
            ("sessions_active","نشست فعال")
        ]:
            card=QFrame();card.setObjectName("Card")
            c=QVBoxLayout(card);c.setContentsMargins(14,14,14,14)
            title_label=QLabel(label);title_label.setObjectName("MetricLabel")
            value=QLabel("—");value.setObjectName("MetricValue")
            c.addWidget(title_label);c.addWidget(value)
            self.metric_labels[key]=value;self.metric_layout.addWidget(card,1)
        layout.addLayout(self.metric_layout)
        card=QFrame();card.setObjectName("Card");actions=QVBoxLayout(card)
        actions.setContentsMargins(18,18,18,18);actions.setSpacing(12)
        a=QLabel("کارهای مدیریتی");a.setObjectName("PageTitle");actions.addWidget(a)
        self.sessions_button=QPushButton("مدیریت نشست‌ها و درخواست‌های ورود  →")
        self.sessions_button.setObjectName("PrimaryButton")
        self.sessions_button.clicked.connect(lambda:window.navigate("sessions"))
        self.users_button=QPushButton("مدیریت حساب‌ها، فعال‌سازی و مجوزها  →")
        self.users_button.clicked.connect(lambda:window.navigate("users"))
        self.schemas_button=QPushButton("فیلدها و مدل‌های سفارشی  →")
        self.schemas_button.clicked.connect(lambda:window.navigate("schemas"))
        actions.addWidget(self.sessions_button);actions.addWidget(self.users_button);actions.addWidget(self.schemas_button)
        layout.addWidget(card)
        note=QLabel("حساب جدیدی که گزینهٔ «تأیید مدیر برای هر نشست» دارد، تا فعال‌سازی در بخش نشست‌ها نمی‌تواند به endpointهای محافظت‌شده دسترسی پیدا کند.")
        note.setObjectName("StatusPill");note.setWordWrap(True);layout.addWidget(note);layout.addStretch(1)

    def refresh(self):
        if self.window.api is None:return
        self.window.run_api(self.window.api.admin_overview,self.populate)

    def populate(self,payload):
        for key,label in self.metric_labels.items():label.setText(str(payload.get(key,0)))


class AccountingMainWindow(QMainWindow):
    """The primary UI has no direct ORM/database access; all business data uses HTTP API."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Accounting App")
        self.resize(1420,900)
        self.setMinimumSize(1040,680)
        self.mode=os.environ.get("ACCOUNTING_APP_THEME","light").lower()
        if self.mode not in ("light","dark"):self.mode="light"
        self.api=None
        self.current_user=None
        self._workers={}
        self._callbacks={}
        self._nav={}
        self._pages={}
        self.company_profile = {}
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.root=QWidget(self);self.root.setObjectName("AppRoot")
        outer=QHBoxLayout(self.root);outer.setContentsMargins(14,14,14,14);outer.setSpacing(14)
        self.sidebar=self._build_sidebar()
        outer.addWidget(self.sidebar)
        main_area=QWidget()
        main_layout=QVBoxLayout(main_area);main_layout.setContentsMargins(0,0,0,0);main_layout.setSpacing(14)
        self.topbar=self._build_topbar()
        main_layout.addWidget(self.topbar)
        self.page_stack=QStackedWidget()
        main_layout.addWidget(self.page_stack,1)
        self.status_bar_frame=QFrame();self.status_bar_frame.setObjectName("Card")
        status_layout=QHBoxLayout(self.status_bar_frame);status_layout.setContentsMargins(14,8,14,8)
        self.status_icon=QLabel("●");self.status_icon.setStyleSheet("color:#0F9D83;")
        self.status_label=QLabel("آماده")
        self.status_label.setObjectName("PageSubtitle")
        status_layout.addWidget(self.status_icon);status_layout.addWidget(self.status_label,1)
        self.user_status=QLabel("بدون ورود");user_status= self.user_status
        user_status.setObjectName("PageSubtitle");status_layout.addWidget(user_status)
        main_layout.addWidget(self.status_bar_frame)
        outer.addWidget(main_area,1)
        self.auth_page=AuthPage(self.mode)
        self.auth_page.api_changed.connect(self._api_changed)
        self.auth_page.authenticated.connect(self._authenticated)
        self.auth_page.theme_changed.connect(self.change_theme)
        self.api = self.auth_page.api
        self.central_stack = QStackedWidget(self)
        self.central_stack.addWidget(self.auth_page)
        self.central_stack.addWidget(self.root)
        self.setCentralWidget(self.central_stack)
        self._build_pages()
        self._apply_theme()
        self._show_auth()
        self.search_shortcut=QShortcut(QKeySequence("Ctrl+K"), self)
        self.search_shortcut.activated.connect(self.open_global_search)
        self.refresh_shortcut=QShortcut(QKeySequence("F5"), self)
        self.refresh_shortcut.activated.connect(self.refresh_current_page)
        self.sale_shortcut=QShortcut(QKeySequence("F2"), self)
        self.sale_shortcut.activated.connect(lambda: self.navigate("sales"))

    def _build_sidebar(self):
        side=QFrame();side.setObjectName("Sidebar");side.setMinimumWidth(218);side.setMaximumWidth(252)
        layout=QVBoxLayout(side);layout.setContentsMargins(13,20,13,17);layout.setSpacing(5)
        brand=QLabel("A");brand.setAlignment(Qt.AlignmentFlag.AlignCenter);brand.setFixedSize(45,45)
        brand.setStyleSheet("background:#4169E1;color:white;border-radius:13px;font-size:23px;font-weight:900;")
        layout.addWidget(brand,0,Qt.AlignmentFlag.AlignRight)
        name=QLabel("Accounting App");name.setObjectName("SidebarBrand");layout.addWidget(name)
        sub=QLabel("SECURE  ·  API EDITION");sub.setObjectName("SidebarSub");layout.addWidget(sub)
        layout.addSpacing(12)
        section=QLabel("محیط کار");section.setObjectName("SidebarSection");layout.addWidget(section)
        nav_specs=[
            ("dashboard","نمای کلی","◫",False),("sales","صندوق فروش","＋",False),
            ("products","محصولات","▦",False),("categories","دسته‌بندی‌ها","◇",False),
            ("warehouse","اقلام انبار","▤",False),("inventory","موجودی کالا","▧",False),("stocktakes","انبارگردانی","☷",False),("checks_in","چک‌های دریافتی","↙",False),
            ("checks_out","چک‌های پرداختی","↗",False),("receipts","رسیدها و فاکتورها","▧",False),
            ("returns","مرجوعی‌ها و استرداد","↩",False),("journals","اسناد حسابداری","≡",False),
            ("fiscal_years","سال مالی","◷",False),("accounting_reports","گزارش‌های مالی","▥",False),
            ("audit","سوابق فعالیت کارکنان","◉",False),
        ]
        for key,label,icon,admin in nav_specs:self._make_nav(layout,key,label,icon,admin)
        self.admin_section=QLabel("مدیریت و تنظیمات");self.admin_section.setObjectName("SidebarSection")
        layout.addWidget(self.admin_section)
        for key,label,icon in [
            ("admin","پنل مدیریت","✦"),("sessions","نشست‌ها و فعال‌سازی","◉"),
            ("users","کاربران","♙"),("permissions","نقش‌ها و مجوزها","♢"),
        ]:self._make_nav(layout,key,label,icon,True)
        self._make_nav(layout,"schemas","مدل‌ها و فیلدهای سفارشی","⌘",False)
        self._make_nav(layout,"invoices","قالب فاکتور","▤",False)
        layout.addStretch(1)
        self.sidebar_user=QLabel("وارد نشده");self.sidebar_user.setObjectName("SidebarSub")
        layout.addWidget(self.sidebar_user)
        self.logout_sidebar=QPushButton("↪  خروج از حساب");self.logout_sidebar.setObjectName("NavigationButton")
        self.logout_sidebar.clicked.connect(self.logout);layout.addWidget(self.logout_sidebar)
        return side

    def _make_nav(self,parent_layout,key,label,icon,admin_only):
        icon_names = {
            "dashboard":"fa5s.chart-pie", "sales":"fa5s.cash-register",
            "products":"fa5s.boxes", "categories":"fa5s.tags",
            "warehouse":"fa5s.warehouse", "inventory":"fa5s.boxes-stacked", "stocktakes":"fa5s.clipboard-check", "checks_in":"fa5s.file-import",
            "checks_out":"fa5s.file-export", "receipts":"fa5s.receipt",
            "returns":"fa5s.rotate-left", "journals":"fa5s.book-open", "fiscal_years":"fa5s.calendar-check",
            "accounting_reports":"fa5s.chart-column", "audit":"fa5s.clipboard-list",
            "admin":"fa5s.chart-line", "sessions":"fa5s.laptop",
            "users":"fa5s.users", "permissions":"fa5s.user-shield",
            "schemas":"fa5s.sliders-h", "invoices":"fa5s.file-invoice",
        }
        button=QPushButton(label if qta else "{}   {}".format(icon,label))
        button.setObjectName("NavigationButton")
        if qta:
            try:
                button.setIcon(qta.icon(icon_names.get(key,"fa5s.circle"),color="#D5DEEF"))
            except Exception:
                button.setText("{}   {}".format(icon,label))
        button.setProperty("active",False);button.setMinimumHeight(41)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False,k=key:self.navigate(k))
        parent_layout.addWidget(button)
        self._nav[key]=(button,admin_only)

    def _build_topbar(self):
        frame=QFrame();frame.setObjectName("Card")
        layout=QHBoxLayout(frame);layout.setContentsMargins(18,12,18,12)
        self.breadcrumb=QLabel("نمای کلی");self.breadcrumb.setObjectName("PageTitle")
        self.page_subtitle=QLabel("مدیریت روزانهٔ حسابداری");self.page_subtitle.setObjectName("PageSubtitle")
        text=QVBoxLayout();text.addWidget(self.breadcrumb);text.addWidget(self.page_subtitle)
        layout.addLayout(text,1)
        self.connection_badge=QLabel("● API");self.connection_badge.setObjectName("StatusPill")
        layout.addWidget(self.connection_badge)
        self.theme_button=QPushButton("☾ تم تاریک" if self.mode=="light" else "☀ تم روشن")
        self.theme_button.clicked.connect(lambda:self.change_theme("dark" if self.mode=="light" else "light"))
        layout.addWidget(self.theme_button)
        self.search_button=QPushButton("جست‌وجوی سریع  Ctrl+K")
        self.search_button.clicked.connect(self.open_global_search)
        layout.addWidget(self.search_button)
        self.settings_button=QPushButton("تنظیمات")
        self.settings_button.clicked.connect(lambda:self.navigate("settings"))
        layout.addWidget(self.settings_button)
        self.logout_button=QPushButton("خروج")
        self.logout_button.setObjectName("DangerButton");self.logout_button.clicked.connect(self.logout)
        layout.addWidget(self.logout_button)
        return frame

    def _build_pages(self):
        self.dashboard=DashboardPage(self)
        self.sales_page=SalesPage(self)
        self.products_page=ProductsPage(self)
        self.categories_page=CategoriesPage(self)
        self.warehouse_page=WarehousePage(self)
        self.inventory_page=InventoryPage(self)
        self.stocktakes_page=StocktakesPage(self)
        self.checks_in_page=ChecksPage(self,"in")
        self.checks_out_page=ChecksPage(self,"out")
        self.receipts_page=ReceiptsPage(self)
        self.users_page=UsersPage(self)
        self.sessions_page=SessionsPage(self)
        self.schemas_page=SchemaPage(self)
        self.permissions_page=PermissionsPage(self)
        self.invoice_templates_page=InvoiceTemplatesPage(self)
        self.returns_page=ReturnsPage(self)
        self.journals_page=JournalsPage(self)
        self.fiscal_years_page=FiscalYearsPage(self)
        self.accounting_reports_page=AccountingReportsPage(self)
        self.audit_page=AuditPage(self)
        self.admin_page=AdminOverviewPage(self)
        self.settings_page=SettingsPage(self)
        definitions=[
            ("dashboard","نمای کلی",self.dashboard),("sales","ثبت فروش",self.sales_page),
            ("products","محصولات",self.products_page),("categories","دسته‌بندی‌ها",self.categories_page),
            ("warehouse","اقلام انبار",self.warehouse_page),("inventory","موجودی کالا",self.inventory_page),("stocktakes","انبارگردانی",self.stocktakes_page),("checks_in","چک‌های دریافتی",self.checks_in_page),
            ("checks_out","چک‌های پرداختی",self.checks_out_page),("receipts","رسیدها",self.receipts_page),
            ("returns","مرجوعی‌ها",self.returns_page),("journals","اسناد حسابداری",self.journals_page),
            ("fiscal_years","سال مالی",self.fiscal_years_page),
            ("accounting_reports","گزارش‌های مالی",self.accounting_reports_page),("audit","سوابق فعالیت",self.audit_page),
            ("admin","پنل مدیریت",self.admin_page),("sessions","نشست‌ها و فعال‌سازی",self.sessions_page),
            ("users","کاربران و دسترسی‌ها",self.users_page),("permissions","نقش‌ها و مجوزها",self.permissions_page),
            ("schemas","فیلدهای سفارشی",self.schemas_page),("invoices","قالب فاکتور",self.invoice_templates_page),
            ("settings","تنظیمات",self.settings_page),
        ]
        for key,title,page in definitions:
            self._pages[key]=page;self.page_stack.addWidget(page)
            if key in self._nav:
                self._nav[key][0].setVisible(key in {"dashboard","sales","products","receipts"})
        self.page_meta={
            "dashboard":("نمای کلی","نمای سریع از فروش و وضعیت عملیات"),
            "sales":("ثبت فروش","ثبت تراکنش از طریق API سرور"),
            "products":("محصولات","مدیریت کاتالوگ محصولات"),
            "categories":("دسته‌بندی‌ها","سازمان‌دهی کالاها"),
            "warehouse":("اقلام انبار","مدیریت اقلام و مواد انبار"),
            "inventory":("موجودی کالا","رهگیری موجودی، حد سفارش و سوابق ورود و خروج"),
            "stocktakes":("انبارگردانی","شمارش فیزیکی، مشاهده اختلاف و اعمال کنترل‌شدهٔ موجودی"),
            "checks_in":("چک‌های دریافتی","مدیریت چک‌های دریافتی"),
            "checks_out":("چک‌های پرداختی","مدیریت چک‌های پرداختی"),
            "receipts":("رسیدها و فاکتورها","جزئیات، چاپ، مرجوعی و خروجی رسیدها"),
            "returns":("مرجوعی‌ها و استرداد","سند مرجوعی مرتبط با فاکتور اصلی و گردش موجودی"),
            "journals":("اسناد حسابداری","ثبت سند دوطرفه و مشاهدهٔ دفتر روزنامه"),
            "fiscal_years":("سال مالی","ایجاد، بستن و بازگشایی کنترل‌شدهٔ دوره‌ها"),
            "accounting_reports":("گزارش‌های مالی","تراز آزمایشی، سود و زیان و ترازنامه"),
            "audit":("سوابق فعالیت کارکنان","ردیابی تغییرات فروش، موجودی و حسابداری"),
            "admin":("پنل مدیریت","کنترل حساب‌ها و وضعیت نشست‌ها"),
            "sessions":("نشست‌ها و فعال‌سازی","تأیید یا لغو دسترسی دستگاه‌ها"),
            "users":("کاربران","فعال‌سازی حساب و سیاست ورود"),
            "permissions":("نقش‌ها و مجوزها","تعیین مجوز مشاهده، ایجاد، ویرایش و حذف هر منبع"),
            "schemas":("مدل‌ها و فیلدهای سفارشی","مدیریت مدل‌ها و فیلدهای توسعه‌پذیر"),
            "invoices":("قالب فاکتور","طراحی قالب چاپ مشترک کلاینت و صندوق فروش"),
            "settings":("تنظیمات","تنظیم اتصال و ظاهر برنامه"),
        }

    def _api_changed(self,api):
        self.api=api

    def _company_profile_loaded(self, profile):
        self.company_profile = dict(profile or {})
        self.set_status("تنظیمات کسب‌وکار بارگذاری شد.")

    def _show_auth(self):
        self.central_stack.setCurrentWidget(self.auth_page)
        self.auth_page.set_mode(self.mode)
        self.setStyleSheet(stylesheet(self.mode))

    def _authenticated(self,user):
        self.current_user=user
        self.api=self.auth_page.api
        self.company_profile = {}
        if self.api is not None:
            self.run_api(
                self.api.get_company_profile,
                self._company_profile_loaded,
                failure=lambda error: self.set_status("تنظیمات کسب‌وکار بارگذاری نشد: {}".format(error)),
            )
        self.central_stack.setCurrentWidget(self.root)
        self.sidebar_user.setText("{}  ·  {}".format(user.get("username"),"مدیر" if user.get("is_admin") else "کاربر"))
        self.user_status.setText("{}  ·  {}".format(user.get("username"),"مدیر" if user.get("is_admin") else "کاربر"))
        admin=bool(user.get("is_admin"))
        nav_permissions = {
            "dashboard": ("reports", "read"), "sales": ("sales", "create"),
            "products": ("products", "read"), "categories": ("categories", "read"),
            "warehouse": ("warehouse", "read"), "inventory": ("warehouse", "read"), "stocktakes": ("warehouse", "read"),
            "checks_in": ("checks_in", "read"),
            "checks_out": ("checks_out", "read"), "receipts": ("receipts", "read"),
            "invoices": ("invoices", "read"), "schemas": ("schemas", "read"),
            "returns": ("returns", "read"), "journals": ("journals", "read"),
            "fiscal_years": ("fiscal_years", "read"),
            "accounting_reports": ("reports", "read"), "audit": ("audit", "read"),
        }
        for key,(button,admin_only) in self._nav.items():
            if admin_only:
                button.setVisible(admin)
            elif key in nav_permissions:
                resource, action = nav_permissions[key]
                allowed = can_access(user, resource, action)
                if key == "sales":
                    allowed = allowed and can_access(user, "products", "read")
                button.setVisible(allowed)
            else:
                button.setVisible(True)
        for page, resource in (
            (self.products_page, "products"), (self.categories_page, "categories"),
            (self.warehouse_page, "warehouse"), (self.checks_in_page, "checks_in"),
            (self.checks_out_page, "checks_out"),
        ):
            page.set_permissions(user, resource)
        self.users_page.set_admin(admin)
        self.permissions_page.set_permissions(user)
        self.invoice_templates_page.set_permissions(user)
        self.inventory_page.set_permissions(user)
        self.stocktakes_page.set_permissions(user)
        self.schemas_page.set_permissions(user)
        self.returns_page.set_permissions(user)
        self.journals_page.set_permissions(user)
        self.fiscal_years_page.set_permissions(user)
        self.accounting_reports_page.set_permissions(user)
        self.audit_page.set_permissions(user)
        self.settings_button.setVisible(True)
        self.dashboard.set_user(user)
        self._apply_theme()
        sales_allowed = can_access(user, "sales", "create") and can_access(user, "products", "read")
        start_page = "dashboard" if can_access(user, "reports", "read") else (
            "sales" if sales_allowed else next(
                (key for key in ("products", "inventory", "warehouse", "receipts", "invoices", "schemas")
                 if key in self._nav and self._nav[key][0].isVisible()),
                "settings",
            )
        )
        self.navigate(start_page)
        self.refresh_dashboard_data()

    def open_global_search(self):
        if self.current_user is None or self.api is None:
            return
        dialog = GlobalSearchDialog(self)
        dialog.exec()

    def refresh_current_page(self):
        if self.current_user is None:
            return
        page = self.page_stack.currentWidget()
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()
        elif hasattr(page, "refresh_products"):
            page.refresh_products()

    def navigate(self,key):
        if key not in self._pages:return
        if self.current_user is None:return
        if key in self._nav and not self._nav[key][0].isVisible():return
        page=self._pages[key]
        self.page_stack.setCurrentWidget(page)
        title,subtitle=self.page_meta[key]
        self.breadcrumb.setText(title);self.page_subtitle.setText(subtitle)
        for nav_key,(button,_admin) in self._nav.items():
            button.setProperty("active",nav_key==key)
            button.style().unpolish(button);button.style().polish(button)
        refresh=getattr(page,"refresh",None)
        if callable(refresh):refresh()
        elif hasattr(page,"refresh_products"):page.refresh_products()
        if key=="admin":page.refresh()
        if key=="sessions":page.refresh()
        if key=="schemas":page.refresh_entities()

    def refresh_dashboard_data(self):
        if self.current_user is None or self.api is None:return
        if can_access(self.current_user, "reports", "read"):
            self.dashboard.refresh()
        if self.current_user.get("is_admin"):
            self.admin_page.refresh()

    def set_status(self,message):
        self.status_label.setText(str(message))
        self.status_icon.setStyleSheet("color:#0F9D83;" if "خطا" not in str(message) else "color:#D64045;")

    def change_theme(self,mode):
        if mode not in ("light","dark"):return
        self.mode=mode
        os.environ["ACCOUNTING_APP_THEME"]=mode
        self._apply_theme()
        if hasattr(self,"auth_page"):self.auth_page.set_mode(mode)
        if hasattr(self,"settings_page") and self.settings_page.theme.currentData()!=mode:
            idx=self.settings_page.theme.findData(mode)
            if idx>=0:self.settings_page.theme.blockSignals(True);self.settings_page.theme.setCurrentIndex(idx);self.settings_page.theme.blockSignals(False)

    def _apply_theme(self):
        self.setStyleSheet(stylesheet(self.mode))
        if hasattr(self,"theme_button"):
            self.theme_button.setText("☀ تم روشن" if self.mode=="dark" else "☾ تم تاریک")

    def connect_to_api(self,url):
        try:
            api=AccountingApiClient(url)
        except ValueError as exc:
            self.show_error(exc);return
        self.api=api
        self.auth_page.server_url.setText(url)
        self.force_logout()
        self.auth_page.connect_server()

    def run_api(self,operation,on_success,*,failure=None,busy=None):
        ticket=uuid.uuid4().hex
        worker=ApiWorker(operation,ticket,parent=self)
        self._workers[ticket]=worker
        self._callbacks[ticket]=(on_success,failure,busy)
        worker.succeeded.connect(self._worker_success)
        worker.failed.connect(self._worker_failure)
        worker.finished.connect(lambda:self._cleanup_worker(ticket))
        if busy:busy.setEnabled(False)
        worker.start()

    @Slot(str,object)
    def _worker_success(self,ticket,result):
        callback=self._callbacks.pop(ticket,None)
        if callback:
            success,_failure,busy=callback
            if busy:busy.setEnabled(True)
            success(result)

    @Slot(str,object)
    def _worker_failure(self,ticket,error):
        callback=self._callbacks.pop(ticket,None)
        if callback:
            _success,failure,busy=callback
            if busy:busy.setEnabled(True)
            if failure:failure(error)
            else:self.show_error(error)

    def _cleanup_worker(self,ticket):
        worker=self._workers.pop(ticket,None)
        if worker:worker.deleteLater()

    def show_error(self,error):
        if getattr(error,"status_code",None)==401:
            self.force_logout()
        QMessageBox.warning(self,"خطای برنامه",str(error))

    def logout(self):
        if self.api is None:
            self.force_logout();return
        api=self.api
        self.run_api(api.logout,lambda _result:self.force_logout(),failure=lambda _err:self.force_logout())

    def force_logout(self):
        if self.api is not None:self.api.clear_session()
        self.current_user=None
        if hasattr(self,"auth_page"):
            self.auth_page.api=self.api
            self.auth_page.setup_required=False
            self.auth_page.server_url.setText(self.api.base_url if self.api else "")
            self.auth_page.connect_server()
        self.central_stack.setCurrentWidget(self.auth_page)
        self.auth_page.set_mode(self.mode)
        self.setStyleSheet(stylesheet(self.mode))

    def closeEvent(self,event):
        for worker in list(self._workers.values()):
            if worker.isRunning():worker.wait(35000)
        event.accept()
