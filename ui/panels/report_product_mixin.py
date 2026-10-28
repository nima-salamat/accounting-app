"""Product-level reports, database cleanup exports and cheque reports."""
import sys
import pandas as pd
from datetime import datetime, timedelta
from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QDateTimeEdit, QComboBox, QPushButton, QTableView,
    QFileDialog, QMessageBox, QScrollArea, QHeaderView, QSpinBox, QCheckBox,
    QSlider, QRadioButton, QLineEdit, QListWidget, QListWidgetItem, QCompleter, QTableWidgetItem,
    QTableWidget, QDialog, QSplitter, QSizePolicy, QAction
)
from PySide2.QtCore import Qt, QDateTime, QTime, Signal, QStringListModel
from PySide2.QtGui import  QPalette, QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
# from matplotlib import rcParams
# from matplotlib.font_manager import FontProperties
# font_prop = FontProperties(fname="B-NAZANIN.TTF")
# rcParams['font.family'] = font_prop.get_name()
from peewee import fn, SQL, JOIN
from db.models import Receipt, ReceiptProduct, Product, Warehouse, Category, User, CheckIn, CheckOut
from ui.utils import PandasModel
from ui.base_panel import jalali_tomorrow_date
import cachetools
import asyncio
import jdatetime
from datetime import datetime, date
from manager.db import DBManager
import webbrowser
from ui.thread import TrackingQThread
QThread = TrackingQThread
JalaliDatetime = jdatetime.datetime

import os
import arabic_reshaper
from bidi.algorithm import get_display

from ui.panels.report_support import (
    farsi, to_jalali, from_jalali, ReportWorker, PurgeWorker, QueryWorker,
    SearchLineEdit, DataLoader, cache, wrap_scrollable,
)






class ReportProductMixin:
    def _product_search(self):
        product_name = self.line.line.text().strip()
        if not product_name:
            return  
        
        try:
            start_j = f"{self.dt_from_date.text()} {self.dt_from_time.text()}:00".replace("/", "-")
            end_j = f"{self.dt_to_date.text()} {self.dt_to_time.text()}:00".replace("/", "-")

            start = from_jalali(start_j, is_datetime=True)
            end = from_jalali(end_j, is_datetime=True)

        except ValueError:
            dlg = QDialog(self)
            dlg.setWindowTitle("خطا")
            lbl = QLabel("فرمت تاریخ یا زمان نادرست است.", dlg)
            QVBoxLayout(dlg).addWidget(lbl)
            dlg.exec_()
            return


        
        try:
            product = Product.get(Product.name == product_name)
        except Product.DoesNotExist:
            dlg = QDialog(self)
            dlg.setWindowTitle("گزارش")
            lbl = QLabel("محصول یافت نشد.", dlg)
            QVBoxLayout(dlg).addWidget(lbl)
            dlg.exec_()
            return

        query = (ReceiptProduct
            .select(Receipt.created_at,
                    ReceiptProduct.quantity,
                    ReceiptProduct.sell_price,
                    ReceiptProduct.buy_price)
            .join(Receipt)
            .where(
                (ReceiptProduct.product == product) &
                (Receipt.created_at >= start) &
                (Receipt.created_at <= end)
            )
            .order_by(Receipt.created_at))


        count = query.count()
        if count == 0:
            dlg = QDialog(self)
            dlg.setWindowTitle("گزارش")
            lbl = QLabel("هیچ فروشی در این بازه یافت نشد.", dlg)
            QVBoxLayout(dlg).addWidget(lbl)
            dlg.exec_()
            return

    
        self.table.clear()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "تاریخ فاکتور", "تعداد", "مبلغ فروش", "مبلغ خرید", "سود"
        ])
        self.table.setRowCount(count + 1)

        total_sales = 0.0
        total_profit = 0.0

        for row, item in enumerate(query):
            date_str = to_jalali(item.receipt.created_at)
            qty = item.quantity
            sale = item.sell_price * qty
            cost = item.buy_price * qty
            profit = sale - cost

            total_sales += sale
            total_profit += profit

            self.table.setItem(row, 0, QTableWidgetItem(date_str))
            self.table.setItem(row, 1, QTableWidgetItem(str(qty)))
            self.table.setItem(row, 2, QTableWidgetItem(f"{sale:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{cost:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{profit:.2f}"))


        footer = ["جمع کل:", "", f"{total_sales:.2f}", "", f"{total_profit:.2f}"]
        for col, text in enumerate(footer):
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(count, col, item)

        self.table.resizeColumnsToContents()
        self.lbl_totals.setText(
            f"مجموع فروش: {total_sales:.2f}    سود خالص: {total_profit:.2f}"
            )
        
        


    def _product_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 1. SearchLineEdit 
        self.line = SearchLineEdit()
        layout.addWidget(self.line)

        # Date filter group
        self.date_group = QGroupBox("بازه زمانی")
        date_layout = QVBoxLayout(self.date_group)

        # From section
        from_layout = QHBoxLayout()
        from_layout.addWidget(QLabel("از:"))
        self.dt_from_date = QLineEdit()
        self.dt_from_date.setPlaceholderText("روز/ماه/سال")
        self.dt_from_date.setText(JalaliDatetime.now().strftime('%Y/%m/%d'))
        from_layout.addWidget(self.dt_from_date)
        self.dt_from_time = QLineEdit()
        self.dt_from_time.setPlaceholderText("ساعت:دقیقه")
        self.dt_from_time.setText("00:00")
        from_layout.addWidget(self.dt_from_time)
        date_layout.addLayout(from_layout)


        to_layout = QHBoxLayout()
        to_layout.addWidget(QLabel("تا:"))
        self.dt_to_date = QLineEdit()
        self.dt_to_date.setPlaceholderText("روز/ماه/سال")
        self.dt_to_date.setText(jalali_tomorrow_date().strftime('%Y/%m/%d'))
        to_layout.addWidget(self.dt_to_date)
        self.dt_to_time = QLineEdit()
        self.dt_to_time.setPlaceholderText("ساعت:دقیقه")
        self.dt_to_time.setText("0:0")
        to_layout.addWidget(self.dt_to_time)
        date_layout.addLayout(to_layout)

        layout.addWidget(self.date_group)

        btn_report = QPushButton("گزارش")
        btn_report.clicked.connect(self._product_search)
        layout.addWidget(btn_report)

        # Scrollable table area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.table = QTableWidget()
        self.scroll.setWidget(self.table)
        layout.addWidget(self.scroll)

       
        self.lbl_totals = QLabel()
        self.lbl_totals.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_totals)

        return widget
    
    
    def _all_products_summary_tab(self):
        w = QWidget(); lo = QVBoxLayout(w)
        date_group, dt_from_date, dt_from_time, dt_to_date, dt_to_time = self._make_date_group(); lo.addWidget(date_group)

        btn = QPushButton("محاسبه فروش همه محصولات")
        lo.addWidget(btn)

        table = QTableWidget(); lo.addWidget(table)
        lbl = QLabel(); lo.addWidget(lbl)
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["محصول", "تعداد", "مبلغ فروش", "مبلغ خرید", "سود", "زمان فاکتور"])

        def query_func(snapshot):
            start_j = "{} {}:00".format(snapshot["from_date"], snapshot["from_time"]).replace("/", "-")
            end_j = "{} {}:00".format(snapshot["to_date"], snapshot["to_time"]).replace("/", "-")
            start = from_jalali(start_j, is_datetime=True)
            end = from_jalali(end_j, is_datetime=True)
            if start > end:
                raise ValueError("زمان شروع نباید از زمان پایان بزرگ‌تر باشد.")

            coalesced_name = fn.COALESCE(Product.name, 'سایر')

            q = (
                ReceiptProduct
                .select(
                    coalesced_name.alias('product_name'),
                    fn.SUM(ReceiptProduct.quantity).alias('qty'),
                    fn.SUM(ReceiptProduct.sell_price * ReceiptProduct.quantity).alias('total_sell'),
                    fn.SUM(ReceiptProduct.buy_price * ReceiptProduct.quantity).alias('total_buy'),
                    fn.MAX(Receipt.created_at).alias("created_at"),
                )
                # بعد از select() متد join را صدا می‌زنیم
                .join(Product, JOIN.LEFT_OUTER, on=(ReceiptProduct.product == Product.id))
                .switch(ReceiptProduct)
                .join(Receipt, JOIN.INNER, on=(ReceiptProduct.receipt == Receipt.id))
                .where(
                    Receipt.payed == True,
                    Receipt.created_at >= start,
    Receipt.created_at <= end
                )
                .group_by(coalesced_name)
                .order_by(SQL('total_sell').desc())
            )

            data = []
            for r in q:
                name = r.product_name or 'سایر'
                if not name.strip() or name.strip() in ['-', '—']:
                    name = 'سایر'

                qty = r.qty or 0
                total_sell = r.total_sell or 0
                total_buy = r.total_buy or 0
                profit = total_sell - total_buy
                created_at = to_jalali(r.created_at) or ""

                data.append([name, qty, total_sell, total_buy, profit, created_at])

            return pd.DataFrame(data, columns=["محصول", "تعداد", "مبلغ فروش", "مبلغ خرید", "سود", "زمان فاکتور"])



        def on_data_ready(df: pd.DataFrame):
            table.setRowCount(len(df))
            total_sell = total_profit = 0.0
            for row, record in df.iterrows():
                for col, val in enumerate(record):
                    text = f"{val:,.2f}" if isinstance(val, (int, float)) and col > 0 else str(val)
                    table.setItem(row, col, QTableWidgetItem(text))
                total_sell += record["مبلغ فروش"]
                total_profit += record["سود"]
            lbl.setText(f"<b>مجموع فروش:</b> {total_sell:,.2f}   <b>سود خالص:</b> {total_profit:,.2f}")
            table.resizeColumnsToContents()
            w.df = df

        def run_worker():
            snapshot = {
                "from_date": dt_from_date.text(),
                "from_time": dt_from_time.text(),
                "to_date": dt_to_date.text(),
                "to_time": dt_to_time.text(),
            }
            self._summary_worker = ReportWorker(lambda: query_func(snapshot))
            self._summary_worker.dataReady.connect(on_data_ready)
            self._summary_worker.error.connect(
                lambda message: QMessageBox.warning(self, "خطا در گزارش محصولات", message)
            )
            self._summary_worker.start()

        btn.clicked.connect(run_worker)
       
        return w
