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

class ReportAllProductsMixin:
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
