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






class ReportMaintenanceMixin:
    def _purge_tab(self):


        # Worker thread to load, filter, and emit data
        class PurgeWorker(QThread):
            dataReady = Signal(list, list, int, float, float)
            error = Signal(str)

            def __init__(self, start_dt, end_dt):
                super().__init__()
                self.start_dt = start_dt
                self.end_dt = end_dt

            def run(self):
                try:
                    # 1) select receipts in date range by created_at
                    rec_q = Receipt.select().where(
                        (Receipt.created_at >= self.start_dt) &
                        (Receipt.created_at <= self.end_dt)
                    )
                    recs = [r.__data__ for r in rec_q]
                    rec_ids = [r['id'] for r in recs]

                    # 2) related items
                    items_q = ReceiptProduct.select().where(
                        ReceiptProduct.receipt.in_(rec_ids)
                    )
                    items = [i.__data__ for i in items_q]

                    # compute summaries
                    count = len(recs)
                    sum_total = sum(r.get('total', 0) for r in recs)
                    sum_buy = sum(r.get('buy_total', 0) for r in recs)

                    # emit for saving
                    self.dataReady.emit(recs, items, count, sum_total, sum_buy)
                except Exception as e:
                    self.error.emit(str(e))

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
            # select save path
            path_r, _ = QFileDialog.getSaveFileName(self, "ذخیره فاکتورها", filter="CSV Files (*.csv)")
            if not path_r:
                btn.setEnabled(True)
                return
            base = os.path.splitext(path_r)[0]
            path_i = base + "_items.csv"
            path_w = base + "_warehouse_backup.csv"

            # save CSVs
            try:
                pd.DataFrame(recs).to_csv(path_r, index=False, encoding='utf-8-sig')
                pd.DataFrame(items).to_csv(path_i, index=False, encoding='utf-8-sig')
                backup = [w.__data__ for w in Warehouse.select()]
                pd.DataFrame(backup).to_csv(path_w, index=False, encoding='utf-8-sig')
            except Exception as e:
                QMessageBox.critical(self, "خطا در ذخیره CSV", str(e))
                btn.setEnabled(True)
                return

            # deletion in transaction
            try:
                with DBManager():
                    ReceiptProduct.delete().where(
                        ReceiptProduct.receipt.in_([r['id'] for r in recs])
                    ).execute()
                    Receipt.delete().where(
                        Receipt.id.in_([r['id'] for r in recs])
                    ).execute()
            except Exception as e:
                QMessageBox.critical(self, "خطا هنگام حذف", str(e))
                btn.setEnabled(True)
                return

            # show links
            lbl.setTextFormat(Qt.RichText)
            lbl.setOpenExternalLinks(True)
            lbl.setText(
                f"<b>تعداد:</b> {count}<br>"
                f"<b>مجموع فروش:</b> {sum_total:,.2f}<br>"
                f"<b>مجموع خرید:</b> {sum_buy:,.2f}<br><br>"
                f"<a href='file:///{path_r}'>📄 مشاهده فاکتورها</a><br>"
                f"<a href='file:///{path_i}'>📄 مشاهده آیتم‌ها</a><br>"
                f"<a href='file:///{path_w}'>📄 مشاهده بک‌آپ انبار</a>"
            )
            QMessageBox.information(self, "موفق", "عملیات با موفقیت انجام شد.")
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

        def query_func():
            raw_from = normalize_jalali_date(dt_from_date.text())
            raw_to   = normalize_jalali_date(dt_to_date.text())

            year, month, day = map(int, raw_to.split('-'))

            j_date = jdatetime.date(year, month, day)
            g_today = j_date.togregorian()

            g_tomorrow = g_today + timedelta(days=1)

            j_tomorrow = jdatetime.date.fromgregorian(date=g_tomorrow).strftime('%Y-%m-%d')
            start = from_jalali(f"{raw_from} 00:00:00", is_datetime=True)
            end   = from_jalali(f"{j_tomorrow} 00:00:00", is_datetime=True)

            Model = CheckIn if rb_in.isChecked() else CheckOut

            conds = []
            if cb_payed.isChecked(): conds.append(Model.payed == True)
            if cb_unpayed.isChecked(): conds.append(Model.payed == False)
            condition = conds[0] if conds else SQL('1=1')
            for c in conds[1:]: condition |= c

            query = Model.select(Model.name, Model.check_id, Model.price, Model.date, Model.payed).where(condition)

            rows = []
            for r in query:
                raw_date = normalize_jalali_date(r.date)
                dt = from_jalali(f"{raw_date} 00:00:00", is_datetime=True)
                if start <= dt <= end:
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
            self.worker = QueryWorker(query_func)
            self.worker.dataReady.connect(on_data_ready)
            self.worker.start()

        btn_run.clicked.connect(run)
        return widget
