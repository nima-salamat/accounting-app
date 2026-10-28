"""API-driven point-of-sale screen with search, quantity selection, and idempotent checkout."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHeaderView,
)


class SalesPage(QFrame):
    def __init__(self,window):
        super().__init__()
        self.window=window;self.products=[]
        self.setObjectName("Card");self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,18,18,18);layout.setSpacing(12)
        header=QHBoxLayout();title_box=QVBoxLayout()
        title=QLabel("فروش جدید");title.setObjectName("PageTitle")
        sub=QLabel("سبد خرید در کلاینت ساخته می‌شود؛ قیمت معتبر، جمع نهایی و ثبت اتمیک همیشه سمت سرور است.")
        sub.setObjectName("PageSubtitle");sub.setWordWrap(True)
        title_box.addWidget(title);title_box.addWidget(sub);header.addLayout(title_box,1)
        self.refresh_button=QPushButton("↻ کالاها")
        self.refresh_button.clicked.connect(self.refresh_products)
        header.addWidget(self.refresh_button);layout.addLayout(header)
        filter_row=QHBoxLayout()
        self.search=QLineEdit();self.search.setPlaceholderText("جست‌وجوی کالا...")
        self.search.returnPressed.connect(self.refresh_products)
        self.search_button=QPushButton("جست‌وجو");self.search_button.clicked.connect(self.refresh_products)
        filter_row.addWidget(self.search,1);filter_row.addWidget(self.search_button);layout.addLayout(filter_row)

        self.table=QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(["شناسه","محصول","قیمت فروش","تعداد"])
        self.table.setColumnHidden(0,True);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True);self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table,1)
        footer_card=QFrame();footer_card.setObjectName("Card")
        footer=QHBoxLayout(footer_card);footer.setContentsMargins(14,12,14,12)
        self.paid=QCheckBox("فاکتور پرداخت شده است")
        self.total_label=QLabel("مبلغ تخمینی: —")
        self.total_label.setObjectName("MetricValue")
        self.submit_button=QPushButton("ثبت امن فروش  ←")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.clicked.connect(self.checkout)
        footer.addWidget(self.paid);footer.addStretch(1);footer.addWidget(self.total_label);footer.addWidget(self.submit_button)
        layout.addWidget(footer_card)
        self.table.cellWidget if False else None

    def refresh_products(self):
        if not self.window.api:return
        query=self.search.text().strip() or None
        self.window.run_api(lambda:self.window.api.list_products(q=query,page_size=200),self.populate,busy=self.refresh_button)

    def populate(self,products):
        self.products=products or [];self.table.setRowCount(0)
        for row,product in enumerate(self.products):
            self.table.insertRow(row)
            values=(product["id"],product["name"],"{:,.2f}".format(float(product["sell_price"])))
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                if col==0:item.setData(Qt.ItemDataRole.UserRole,product)
                self.table.setItem(row,col,item)
            quantity=QSpinBox();quantity.setRange(0,100000);quantity.setValue(0)
            quantity.valueChanged.connect(self.update_estimate)
            self.table.setCellWidget(row,3,quantity)
        self.update_estimate()

    def collect_items(self):
        output=[]
        for row in range(self.table.rowCount()):
            quantity=self.table.cellWidget(row,3).value()
            if quantity>0:
                product=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
                output.append({"product_id":product["id"],"quantity":quantity})
        return output

    def update_estimate(self,*_):
        by_id={p["id"]:p for p in self.products}
        total=0.0
        for item in self.collect_items():
            product=by_id.get(item["product_id"])
            if product:total+=float(product["sell_price"])*item["quantity"]
        self.total_label.setText("جمع تخمینی: {:,.2f}".format(total))

    def checkout(self):
        items=self.collect_items()
        if not items:
            self.window.show_error("برای ثبت فروش حداقل یک تعداد مثبت وارد کنید.");return
        answer=QMessageBox.question(self,"تأیید فروش",
            "فروش با {} نوع کالا ثبت شود؟ مبلغ نهایی در سرور محاسبه می‌شود.".format(len(items)),
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.Yes)
        if answer!=QMessageBox.StandardButton.Yes:return
        paid=self.paid.isChecked()
        self.window.run_api(lambda:self.window.api.create_sale(items,paid=paid),self._sale_created,busy=self.submit_button)

    def _sale_created(self,receipt):
        self.paid.setChecked(False)
        for row in range(self.table.rowCount()):self.table.cellWidget(row,3).setValue(0)
        QMessageBox.information(self,"فروش ثبت شد",
            "شماره رسید روزانه: {}\nمبلغ نهایی: {:,.2f}".format(receipt["day_receipt_id"],float(receipt["total_price"])))
        self.window.set_status("فروش با موفقیت ثبت شد.")
        self.refresh_products();self.window.refresh_dashboard_data()
        self.window.receipts_page.refresh()
