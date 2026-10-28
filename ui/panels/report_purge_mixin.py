"""Product-level reports, database cleanup exports and cheque reports."""
import sys
import pandas as pd
from datetime import datetime, timedelta
from PySide2.QtCore import QUrl
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

from accounting_app.services.schema_registry import cleanup_builtin_extension_values
from ui.panels.report_support import (
    farsi, to_jalali, from_jalali, ReportWorker, PurgeWorker, QueryWorker,
    SearchLineEdit, DataLoader, cache, wrap_scrollable,
)

class ReportPurgeMixin:
    def _purge_tab(self):


        # main widget
        w = QWidget()
        lo = QVBoxLayout(w)

        date_group, dt_from_date, dt_from_time, dt_to_date, dt_to_time = self._make_date_group()
        lo.addWidget(date_group)

        btn = QPushButton("صدور و پاک‌سازی")
        lo.addWidget(btn, alignment=Qt.AlignCenter)

        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        lo.addWidget(lbl)

        def on_data(recs, items, count, sum_total, sum_buy):
            if not recs:
                QMessageBox.information(self, "بدون داده", "در این بازه فاکتوری برای پاک‌سازی وجود ندارد.")
                btn.setEnabled(True)
                return

            # select save path
            path_r, _ = QFileDialog.getSaveFileName(self, "ذخیره فاکتورها", filter="CSV Files (*.csv)")
            if not path_r:
                btn.setEnabled(True)
                return
            btn.setEnabled(False)
            self.purge_finalize_worker = PurgeFinalizeWorker(
                recs, items, path_r, count, sum_total, sum_buy
            )
            self.purge_finalize_worker.completed.connect(on_finalize_complete)
            self.purge_finalize_worker.error.connect(on_error)
            self.purge_finalize_worker.start()

        def on_finalize_complete(path_r, path_i, path_w, count, sum_total, sum_buy):
            lbl.setTextFormat(Qt.RichText)
            lbl.setOpenExternalLinks(True)
            receipt_url = QUrl.fromLocalFile(path_r).toString()
            items_url = QUrl.fromLocalFile(path_i).toString()
            warehouse_url = QUrl.fromLocalFile(path_w).toString()
            lbl.setText(
                f"<b>تعداد:</b> {count}<br>"
                f"<b>مجموع فروش:</b> {sum_total:,.2f}<br>"
                f"<b>مجموع خرید:</b> {sum_buy:,.2f}<br><br>"
                f"<a href='{receipt_url}'>📄 مشاهده فاکتورها</a><br>"
                f"<a href='{items_url}'>📄 مشاهده آیتم‌ها</a><br>"
                f"<a href='{warehouse_url}'>📄 مشاهده بک‌آپ انبار</a>"
            )
            QMessageBox.information(self, "موفق", "پشتیبان‌گیری و پاک‌سازی با موفقیت انجام شد.")
            btn.setEnabled(True)

        def on_error(msg):
            QMessageBox.critical(self, "خطا در پردازش", msg)
            lbl.setText("عملیات ناموفق؛ داده‌ها حذف نشدند.")
            btn.setEnabled(True)

        def start_purge():
            try:
                start_j = f"{dt_from_date.text()} {dt_from_time.text()}:00".replace('/', '-')
                end_j = f"{dt_to_date.text()} {dt_to_time.text()}:00".replace('/', '-')
                start_dt = from_jalali(start_j, is_datetime=True)
                end_dt = from_jalali(end_j, is_datetime=True)
                if start_dt > end_dt:
                    raise ValueError("زمان شروع نباید از زمان پایان بزرگ‌تر باشد.")
            except ValueError as e:
                QMessageBox.critical(self, "خطا", f"فرمت تاریخ/زمان نادرست:\n{e}")
                return

            btn.setEnabled(False)
            self.worker = PurgeWorker(start_dt, end_dt)
            self.worker.dataReady.connect(on_data)
            self.worker.error.connect(on_error)
            self.worker.start()

        btn.clicked.connect(start_purge)
        return w
