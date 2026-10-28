"""Product-level reports, database cleanup exports and cheque reports."""
import sys
import pandas as pd
from datetime import datetime, timedelta
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QDateTimeEdit, QComboBox, QPushButton, QTableView,
    QFileDialog, QMessageBox, QScrollArea, QHeaderView, QSpinBox, QCheckBox,
    QSlider, QRadioButton, QLineEdit, QListWidget, QListWidgetItem, QCompleter, QTableWidgetItem,
    QTableWidget, QDialog, QSplitter, QSizePolicy
)
from PySide6.QtCore import Qt, QDateTime, QTime, Signal, QStringListModel
from PySide6.QtGui import  QPalette, QColor
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
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

class ReportProductSearchMixin:
    def _product_search(self):
        product_name = self.line.line.text().strip()
        if not product_name:
            QMessageBox.information(self, "گزارش محصول", "ابتدا نام محصول را وارد کنید.")
            return

        try:
            start_j = "{} {}:00".format(
                self.dt_from_date.text(), self.dt_from_time.text()
            ).replace("/", "-")
            end_j = "{} {}:00".format(
                self.dt_to_date.text(), self.dt_to_time.text()
            ).replace("/", "-")
            start = from_jalali(start_j, is_datetime=True)
            end = from_jalali(end_j, is_datetime=True)
            if start > end:
                raise ValueError("زمان شروع نباید از زمان پایان بزرگ‌تر باشد.")
        except ValueError as exc:
            QMessageBox.warning(self, "بازهٔ نامعتبر", str(exc))
            return

        snapshot = {"product_name": product_name, "start": start, "end": end}

        def query_func(filters):
            product = Product.get_or_none(Product.name == filters["product_name"])
            if product is None:
                raise ValueError("محصول موردنظر پیدا نشد.")

            query = (
                ReceiptProduct
                .select(
                    Receipt.created_at,
                    ReceiptProduct.quantity,
                    ReceiptProduct.sell_price,
                    ReceiptProduct.buy_price,
                )
                .join(Receipt)
                .where(
                    (ReceiptProduct.product == product)
                    & (Receipt.created_at >= filters["start"])
                    & (Receipt.created_at <= filters["end"])
                )
                .order_by(Receipt.created_at)
            )

            rows = []
            for item in query:
                quantity = item.quantity
                sales = item.sell_price * quantity
                cost = item.buy_price * quantity
                rows.append({
                    "date": to_jalali(item.receipt.created_at),
                    "quantity": quantity,
                    "sales": sales,
                    "cost": cost,
                    "profit": sales - cost,
                })
            return pd.DataFrame(
                rows, columns=["date", "quantity", "sales", "cost", "profit"]
            )

        def on_data_ready(data):
            if data.empty:
                self.table.setRowCount(0)
                self.lbl_totals.setText("")
                QMessageBox.information(self, "گزارش محصول", "در این بازه فروشی برای این محصول یافت نشد.")
                return

            self.table.clear()
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels([
                "تاریخ فاکتور", "تعداد", "مبلغ فروش", "مبلغ خرید", "سود"
            ])
            self.table.setRowCount(len(data) + 1)

            total_sales = float(data["sales"].sum())
            total_profit = float(data["profit"].sum())
            for row_index, record in data.iterrows():
                values = (
                    record["date"], record["quantity"], record["sales"],
                    record["cost"], record["profit"],
                )
                for column, value in enumerate(values):
                    text = "{:.2f}".format(value) if column >= 2 else str(value)
                    self.table.setItem(row_index, column, QTableWidgetItem(text))

            footer = ["جمع کل:", "", "{:.2f}".format(total_sales), "", "{:.2f}".format(total_profit)]
            for column, value in enumerate(footer):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(len(data), column, item)

            self.table.resizeColumnsToContents()
            self.lbl_totals.setText(
                "مجموع فروش: {:.2f}    سود خالص: {:.2f}".format(total_sales, total_profit)
            )

        self._product_search_worker = QueryWorker(lambda: query_func(snapshot))
        self._product_search_worker.dataReady.connect(on_data_ready)
        self._product_search_worker.error.connect(
            lambda message: QMessageBox.warning(self, "خطا در گزارش محصول", message)
        )
        self._product_search_worker.start()

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
