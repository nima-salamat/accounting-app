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

from accounting_app.services.schema_registry import cleanup_builtin_extension_values
from ui.panels.report_support import (
    farsi, to_jalali, from_jalali, ReportWorker, PurgeWorker, QueryWorker,
    SearchLineEdit, DataLoader, cache, wrap_scrollable,
)

class ReportChequeMixin:
    def _check_tab(self):
      
        widget = QWidget()
        layout = QVBoxLayout(widget)


        date_group = QGroupBox("بازه زمانی")
        date_layout = QHBoxLayout(date_group)
        date_layout.addWidget(QLabel("از:"))
        dt_from_date = QLineEdit()
        dt_from_date.setPlaceholderText("روز/ماه/سال")
        dt_from_date.setText(JalaliDatetime.now().strftime('%Y/%m/%d'))
        date_layout.addWidget(dt_from_date)
        date_layout.addWidget(QLabel("تا:"))
        dt_to_date = QLineEdit()
        dt_to_date.setPlaceholderText("روز/ماه/سال")
        dt_to_date.setText(JalaliDatetime.now().strftime('%Y/%m/%d'))
        date_layout.addWidget(dt_to_date)
        layout.addWidget(date_group)

        type_box = QGroupBox("نوع چک")
        type_layout = QHBoxLayout(type_box)
        rb_in = QRadioButton("طلبکاری")
        rb_out = QRadioButton("بدهکاری")
        rb_in.setChecked(True)
        type_layout.addWidget(rb_in)
        type_layout.addWidget(rb_out)
        layout.addWidget(type_box)

       
        payed_box = QGroupBox("وضعیت پاس شده")
        payed_layout = QHBoxLayout(payed_box)
        cb_payed = QCheckBox("پاس شده")
        cb_unpayed = QCheckBox("پاس نشده")
        cb_payed.setChecked(True)
        cb_unpayed.setChecked(True)
        payed_layout.addWidget(cb_payed)
        payed_layout.addWidget(cb_unpayed)
        layout.addWidget(payed_box)

        btn_run = QPushButton("نمایش چک‌ها")
        layout.addWidget(btn_run)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["نام", "شماره چک", "مبلغ", "تاریخ", "وضعیت پاس"])
        layout.addWidget(table)

        lbl_total = QLabel()
        lbl_total.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_total)


        import re
        def normalize_jalali_date(date_str):
            s = re.sub(r'[^0-9/]', '', date_str)
            s = re.sub(r'/+', '/', s).strip('/')
            return s.replace('/', '-')

        def query_func(snapshot):
            raw_from = normalize_jalali_date(snapshot["from_date"])
            raw_to = normalize_jalali_date(snapshot["to_date"])
            if not raw_from or not raw_to:
                raise ValueError("تاریخ شروع و پایان را وارد کنید.")

            from_year, from_month, from_day = map(int, raw_from.split("-"))
            to_year, to_month, to_day = map(int, raw_to.split("-"))
            start_jalali = jdatetime.date(from_year, from_month, from_day)
            end_jalali = jdatetime.date(to_year, to_month, to_day)
            if start_jalali > end_jalali:
                raise ValueError("تاریخ شروع نباید پس از تاریخ پایان باشد.")

            start = from_jalali("{} 00:00:00".format(raw_from), is_datetime=True)
            end_gregorian = end_jalali.togregorian() + timedelta(days=1)
            end_jalali_exclusive = jdatetime.date.fromgregorian(date=end_gregorian).strftime("%Y-%m-%d")
            end = from_jalali("{} 00:00:00".format(end_jalali_exclusive), is_datetime=True)

            Model = CheckIn if snapshot["incoming"] else CheckOut
            conds = []
            if snapshot["payed"]:
                conds.append(Model.payed == True)
            if snapshot["unpayed"]:
                conds.append(Model.payed == False)
            if not conds:
                raise ValueError("حداقل یکی از وضعیت‌های چک را انتخاب کنید.")
            condition = conds[0]
            for extra_condition in conds[1:]:
                condition |= extra_condition

            query = Model.select(Model.name, Model.check_id, Model.price, Model.date, Model.payed).where(condition)

            rows = []
            for r in query:
                raw_date = normalize_jalali_date(r.date)
                dt = from_jalali("{} 00:00:00".format(raw_date), is_datetime=True)
                if start <= dt < end:
                    rows.append({
                        "name": r.name,
                        "check_id": r.check_id,
                        "price": r.price,
                        "date": raw_date,
                        "payed": "بله" if r.payed else "خیر"
                    })
            df = pd.DataFrame(rows)
            return df

        def on_data_ready(df: pd.DataFrame):
            table.setRowCount(len(df))
            total = df['price'].sum() if not df.empty else 0.0
            for i, row in df.iterrows():
                table.setItem(i, 0, QTableWidgetItem(row["name"]))
                table.setItem(i, 1, QTableWidgetItem(row["check_id"]))
                table.setItem(i, 2, QTableWidgetItem(f"{row['price']:.2f}"))
                table.setItem(i, 3, QTableWidgetItem(row["date"]))
                table.setItem(i, 4, QTableWidgetItem(row["payed"]))
            lbl_total.setText(f"مجموع مبلغ: {total:,.2f}")
            table.resizeColumnsToContents()

        def run():
            snapshot = {
                "from_date": dt_from_date.text(),
                "to_date": dt_to_date.text(),
                "incoming": rb_in.isChecked(),
                "payed": cb_payed.isChecked(),
                "unpayed": cb_unpayed.isChecked(),
            }
            self.worker = QueryWorker(lambda: query_func(snapshot))
            self.worker.dataReady.connect(on_data_ready)
            self.worker.error.connect(
                lambda message: QMessageBox.warning(self, "خطا در گزارش چک", message)
            )
            self.worker.start()

        btn_run.clicked.connect(run)
        return widget
