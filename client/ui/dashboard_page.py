"""Professional overview dashboard driven only by aggregated API endpoints."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QHeaderView, QWidget,
)
from client.ui.data_pages import display_value
from client.ui.permissions import can_access


class MetricCard(QFrame):
    def __init__(self, title, accent="#4169E1", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout=QVBoxLayout(self);layout.setContentsMargins(18,16,18,16);layout.setSpacing(7)
        top=QHBoxLayout();label=QLabel(title);label.setObjectName("MetricLabel")
        dot=QLabel("●");dot.setStyleSheet("color:{};font-size:15px;".format(accent))
        top.addWidget(label);top.addStretch(1);top.addWidget(dot);layout.addLayout(top)
        self.value=QLabel("—");self.value.setObjectName("MetricValue");layout.addWidget(self.value)
        self.hint=QLabel("به‌روزرسانی از سرور");self.hint.setObjectName("PageSubtitle");layout.addWidget(self.hint)

    def set_value(self,value,hint=None):
        self.value.setText(str(value))
        if hint is not None:self.hint.setText(str(hint))


class DashboardPage(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(16)
        heading=QHBoxLayout();titles=QVBoxLayout()
        title=QLabel("نمای کلی");title.setObjectName("PageTitle")
        subtitle=QLabel("وضعیت فروش، رسیدها و محصولات؛ داده‌ها از API سرور حسابداری دریافت می‌شوند.")
        subtitle.setObjectName("PageSubtitle");subtitle.setWordWrap(True)
        titles.addWidget(title);titles.addWidget(subtitle);heading.addLayout(titles,1)
        self.refresh_button=QPushButton("↻ به‌روزرسانی")
        self.refresh_button.setObjectName("PrimaryButton")
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button,0,Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(heading)

        grid=QGridLayout();grid.setSpacing(12)
        self.metrics={}
        for index,(key,title,accent) in enumerate([
            ("sales_total","جمع فروش","#4169E1"),("receipt_count","تعداد رسیدها","#0F9D83"),
            ("paid_count","پرداخت‌شده","#8B5CF6"),("unpaid_count","پرداخت‌نشده","#D97706"),
            ("item_count","تعداد اقلام فروخته‌شده","#0891B2")
        ]):
            card=MetricCard(title,accent)
            self.metrics[key]=card
            grid.addWidget(card,index//3,index%3)
        layout.addLayout(grid)

        charts=QHBoxLayout();charts.setSpacing(12)
        self.trend_card=QFrame();self.trend_card.setObjectName("Card")
        trend_layout=QVBoxLayout(self.trend_card);trend_layout.setContentsMargins(16,15,16,15)
        trend_title=QLabel("روند فروش روزانه");trend_title.setObjectName("PageTitle")
        trend_sub=QLabel("نمایش تجمیعی از endpoint گزارش؛ بدون انتقال تمام تراکنش‌ها به کلاینت.")
        trend_sub.setObjectName("PageSubtitle");trend_sub.setWordWrap(True)
        trend_layout.addWidget(trend_title);trend_layout.addWidget(trend_sub)
        self.trend_table=QTableWidget(0,3)
        self.trend_table.setHorizontalHeaderLabels(["تاریخ","فروش","رسید"])
        self.trend_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trend_table.verticalHeader().setVisible(False)
        self.trend_table.setMaximumHeight(260)
        trend_layout.addWidget(self.trend_table,1)
        charts.addWidget(self.trend_card,3)

        self.top_card=QFrame();self.top_card.setObjectName("Card")
        top_layout=QVBoxLayout(self.top_card);top_layout.setContentsMargins(16,15,16,15)
        top_title=QLabel("محصولات پرفروش");top_title.setObjectName("PageTitle")
        top_sub=QLabel("بر اساس تعداد و درآمد ثبت‌شده در رسیدها.")
        top_sub.setObjectName("PageSubtitle")
        top_layout.addWidget(top_title);top_layout.addWidget(top_sub)
        self.products_table=QTableWidget(0,3)
        self.products_table.setHorizontalHeaderLabels(["محصول","تعداد","درآمد"])
        self.products_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.products_table.verticalHeader().setVisible(False)
        self.products_table.setMaximumHeight(260)
        top_layout.addWidget(self.products_table,1)
        charts.addWidget(self.top_card,2)
        layout.addLayout(charts,1)
        footer=QHBoxLayout()
        self.role_label=QLabel("دسترسی‌ها طبق مجوزهای سرور اعمال می‌شوند.")
        self.role_label.setObjectName("PageSubtitle")
        footer.addWidget(self.role_label,1)
        self.kiosk_button=QPushButton("مدیریت کیوسک  →")
        self.kiosk_button.setObjectName("PrimaryButton")
        self.kiosk_button.clicked.connect(lambda: self.window.navigate("kiosk"))
        footer.addWidget(self.kiosk_button)
        layout.addLayout(footer)

    def set_user(self,user):
        self.role_label.setText("کاربر: {}  ·  نقش: {}".format(
            user.get("username","—"),"مدیر" if user.get("is_admin") else "کاربر"
        ))
        self.kiosk_button.setVisible(
            can_access(user, "kiosk", "read") or can_access(user, "kiosk", "update")
        )

    def refresh(self):
        if not self.window.api:return
        api=self.window.api
        self.window.run_api(lambda:{
            "summary":api.sales_summary(),
            "trend":api.sales_trend(days=30),
            "products":api.product_performance(limit=10),
        },self.populate,busy=self.refresh_button)

    def populate(self,payload):
        summary=payload["summary"]
        self.metrics["sales_total"].set_value(display_value("sales_total",summary.get("sales_total")))
        for key in ("receipt_count","paid_count","unpaid_count","item_count"):
            self.metrics[key].set_value(summary.get(key,0))
        self.trend_table.setRowCount(0)
        trend=payload.get("trend",[])
        for row,point in enumerate(trend[-10:]):
            self.trend_table.insertRow(row)
            values=(point.get("date"),display_value("total_price",point.get("total")),point.get("receipt_count"))
            for col,value in enumerate(values):self.trend_table.setItem(row,col,QTableWidgetItem(str(value)))
        self.products_table.setRowCount(0)
        for row,item in enumerate(payload.get("products",[])):
            self.products_table.insertRow(row)
            values=(item.get("name"),item.get("quantity"),display_value("revenue",item.get("revenue")))
            for col,value in enumerate(values):self.products_table.setItem(row,col,QTableWidgetItem(str(value)))
        if not trend:
            self.window.set_status("گزارش بارگذاری شد؛ در بازهٔ انتخاب‌شده فروشی وجود ندارد.")
