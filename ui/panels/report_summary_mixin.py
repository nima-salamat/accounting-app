"""Overview, time series, product sales, inventory and category reports."""
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
    SearchLineEdit, DataLoader, cache, cache_lock, wrap_scrollable,
)

class ReportSummaryMixin:
    def _overview_tab(self):
        w = QWidget()
        lo = QVBoxLayout(w)

        lbl = QLabel("در حال بارگذاری...")
        lo.addWidget(lbl)

        btn_refresh = QPushButton("رفرش")
        lo.addWidget(btn_refresh)

        def query_func():
            counts = {
                "تعداد کاربران": User.select().count(),
                "تعداد رسیدها": Receipt.select().count(),
                "کل فروش": Receipt.select(fn.SUM(Receipt.total_price)).scalar() or 0,
                "میانگین مبلغ رسید": Receipt.select(fn.AVG(Receipt.total_price)).scalar() or 0,
                "میانگین تعداد آیتم در رسید": (
                    (ReceiptProduct.select(fn.SUM(ReceiptProduct.quantity)).scalar() or 0) /
                    max(Receipt.select().count(), 1)
                )
            }
            df = pd.DataFrame(list(counts.items()), columns=["معیار", "مقدار"])
            return df

        def on_data_ready(df):
            text = ""
            for idx, row in df.iterrows():
                text += f"<b>{row['معیار']}:</b> {row['مقدار']:,}<br>"
            lbl.setText(text)
            w.df = df

        def load_data():
            lbl.setText("در حال بارگذاری...")
            self._overview_worker = QueryWorker(query_func)
            self._overview_worker.dataReady.connect(on_data_ready)
            self._overview_worker.error.connect(
                lambda message: lbl.setText("بارگذاری ناموفق: {}".format(message))
            )
            self._overview_worker.start()

        btn_refresh.clicked.connect(load_data)
        load_data()


        return w

    # -------------------------------------------------------------------------
    def _sales_time_tab(self):
        w = QWidget()
        lo = QVBoxLayout(w)

        date_group, dt_from_date, dt_from_time, dt_to_date, dt_to_time = self._make_date_group()
        lo.addWidget(date_group)

        cb = QComboBox()
        cb.addItems(["ساعت", "روز", "ماه"])
        cb.setCurrentText("ساعت")
        lo.addWidget(QLabel("دقت زمان:"))
        lo.addWidget(cb)

        btn_load = QPushButton("بارگذاری")
        btn_refresh = QPushButton("رفرش")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_load)
        btn_layout.addWidget(btn_refresh)
        lo.addLayout(btn_layout)

        fig = Figure(figsize=(8,4))
        canvas = FigureCanvas(fig)
        lo.addWidget(canvas)
        self._add_export_chart_btn(lo, fig)

        def query_func(snapshot):
            start_j = "{} {}:00".format(snapshot["from_date"], snapshot["from_time"]).replace("/", "-")
            end_j = "{} {}:00".format(snapshot["to_date"], snapshot["to_time"]).replace("/", "-")
            start = from_jalali(start_j, is_datetime=True)
            end = from_jalali(end_j, is_datetime=True)
            if start > end:
                raise ValueError("زمان شروع نباید از زمان پایان بزرگ‌تر باشد.")

            fmt_map = {
                "ساعت": "%Y-%m-%d %H",
                "روز": "%Y-%m-%d",
                "ماه": "%Y-%m"
            }
            fmt = fmt_map[snapshot["granularity"]]

            cache_key = f"sales_time_{fmt}_{start}_{end}"
            with cache_lock:
                cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            qs = (Receipt
                .select(fn.strftime(fmt, Receipt.created_at).alias('t'),
                        fn.COUNT(Receipt.id).alias('cnt'))
                .where(Receipt.payed==True, Receipt.created_at >= start,
                    Receipt.created_at <= end)
                .group_by(SQL('t')).order_by(SQL('t')))
            
            df = pd.DataFrame([{"زمان":to_jalali(r.t), "تعداد":r.cnt} for r in qs])
            with cache_lock:
                cache[cache_key] = df
            return df

        def on_data_ready(df):
            if not hasattr(on_data_ready, 'ax') or on_data_ready.ax is None:
                on_data_ready.ax = fig.add_subplot(111)
            ax = on_data_ready.ax
            ax.clear()

            if not df.empty:
                ax.plot(df["زمان"], df["تعداد"], marker='o')
            ax.set_title(farsi("تعداد فروش بر حسب زمان"))
            ax.tick_params(axis='x', rotation=45)
            fig.tight_layout()
            canvas.draw()
            w.df = df

        def load():
            snapshot = {
                "from_date": dt_from_date.text(),
                "from_time": dt_from_time.text(),
                "to_date": dt_to_date.text(),
                "to_time": dt_to_time.text(),
                "granularity": cb.currentText(),
            }
            btn_load.setEnabled(False)
            self._sales_time_worker = QueryWorker(lambda: query_func(snapshot))
            self._sales_time_worker.dataReady.connect(lambda df: (on_data_ready(df), btn_load.setEnabled(True)))
            self._sales_time_worker.error.connect(
                lambda message: (QMessageBox.warning(self, "خطا در گزارش", message), btn_load.setEnabled(True))
            )
            self._sales_time_worker.start()

        btn_load.clicked.connect(load)
        btn_refresh.clicked.connect(load)

        return w
