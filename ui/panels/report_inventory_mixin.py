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
    SearchLineEdit, DataLoader, cache, wrap_scrollable,
)






class ReportInventoryMixin:
    def _inventory_tab(self):
        w = QWidget()
        lo = QVBoxLayout(w)

        date_group, dt_from_date, dt_from_time, dt_to_date, dt_to_time = self._make_date_group()
        lo.addWidget(date_group)

        
        btn_load = QPushButton("بارگذاری هزینه")
        btn_refresh = QPushButton("رفرش")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_load)
        btn_layout.addWidget(btn_refresh)
        lo.addLayout(btn_layout)

        table = QTableWidget()
        lo.addWidget(table)
        
        lbl_totals = QLabel()
        lbl_totals.setAlignment(Qt.AlignCenter)
        lo.addWidget(lbl_totals)

        def query_func():
            try:
                start_j = f"{dt_from_date.text()} {dt_from_time.text()}:00".replace("/", "-")
                end_j = f"{dt_to_date.text()} {dt_to_time.text()}:00".replace("/", "-")

                start = from_jalali(start_j, is_datetime=True)
                end = from_jalali(end_j, is_datetime=True)

            except ValueError:
                dlg = QDialog(self)
                dlg.setWindowTitle("خطا")
                lbl = QLabel("فرمت تاریخ یا زمان نادرست است.", dlg)
                QVBoxLayout(dlg).addWidget(lbl)
                dlg.exec_()
                return
            
            q = (Warehouse.select(
                Warehouse.name, Warehouse.price, Warehouse.amount,
                Warehouse.unit, Warehouse.created_at
            ).where(
                    Warehouse.created_at >= start,
    Warehouse.created_at <= end
                 ).order_by(Warehouse.created_at))

            return q

        def on_data_ready(query):
            count = query.count()
            if count == 0:
                dlg = QDialog(self)
                dlg.setWindowTitle("گزارش")
                lbl = QLabel("هیچ دیتایی در این بازه یافت نشد.", dlg)
                QVBoxLayout(dlg).addWidget(lbl)
                dlg.exec_()
                return


            table.clear()
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels([
                "محصول","تاریخ خرید", "تعداد", "مبلغ خرید واحد","مبلغ خرید کل" ,"یکا"
            ])
            
            table.setRowCount(count + 1)

            total_costs = 0.0

            for row, item in enumerate(query):
                date_str = to_jalali(item.created_at)
                
                qty = item.amount
                cost = item.price
            
                
                total_costs += cost * qty
                table.setItem(row, 0, QTableWidgetItem(item.name))
                table.setItem(row, 1, QTableWidgetItem(date_str))
                table.setItem(row, 2, QTableWidgetItem(str(qty)))
                table.setItem(row, 3, QTableWidgetItem(f"{cost:.2f}"))
                table.setItem(row, 4, QTableWidgetItem(f"{cost*qty:.2f}"))
                
                table.setItem(row, 5, QTableWidgetItem(item.unit))
                
                

         
            footer = ["جمع کل:", "", "", "", f"{total_costs:.2f}"]
            for col, text in enumerate(footer):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled)
                table.setItem(count, col, item)

            table.resizeColumnsToContents()
            lbl_totals.setText(
                f"مجموع خرید: {total_costs:.2f}"
                )
                

        def load():
            btn_load.setEnabled(False)
            self._inventory_worker = QueryWorker(query_func)
            self._inventory_worker.dataReady.connect(lambda q: (on_data_ready(q), btn_load.setEnabled(True)))
            self._inventory_worker.error.connect(
                lambda message: (QMessageBox.warning(self, "خطا در گزارش", message), btn_load.setEnabled(True))
            )
            self._inventory_worker.start()
        
        
          
        btn_load.clicked.connect(load)
        btn_refresh.clicked.connect(load)
       
        return w
    
    
    
    
    # -------------------------------------------------------------------------
    def _category_pie_tab(self):
        w = QWidget()
        lo = QVBoxLayout(w)

    
        mode_layout = QHBoxLayout()
        mode_combo = QComboBox()
        mode_combo.addItems(["بر اساس تعداد", "بر اساس مبلغ فروش"])
        btn_report = QPushButton("گزارش")
        btn_refresh = QPushButton("رفرش")

        mode_layout.addWidget(mode_combo)
        mode_layout.addWidget(btn_report)
        mode_layout.addWidget(btn_refresh)
        lo.addLayout(mode_layout)

      
        fig = Figure(figsize=(6, 6))
        canvas = FigureCanvas(fig)
        lo.addWidget(canvas)
        self._add_export_chart_btn(lo, fig)

        def query_func():
            mode = mode_combo.currentIndex()

            if mode == 0:
                q = (
                    ReceiptProduct
                    .select(
                        fn.COALESCE(Category.name, 'سایر').alias('category_name'),
                        fn.SUM(ReceiptProduct.quantity).alias('value')
                    )
                    .join(Receipt)
                    .switch(ReceiptProduct)
                    .join(Product, JOIN.LEFT_OUTER)
                    .join(Category, JOIN.LEFT_OUTER) 
                    .where(Receipt.payed == True)
                    .group_by(Category.name)
                )
            else:
                q = (
                    ReceiptProduct
                    .select(
                        fn.COALESCE(Category.name, 'سایر').alias('category_name'),
                        fn.SUM(ReceiptProduct.quantity * ReceiptProduct.sell_price).alias('value')
                    )
                    .join(Receipt)
                    .switch(ReceiptProduct)
                    .join(Product, JOIN.LEFT_OUTER)
                    .join(Category, JOIN.LEFT_OUTER)  # join دسته
                    .where(Receipt.payed == True)
                    .group_by(Category.name)
                )

            return pd.DataFrame([
                (farsi(r.category_name) or farsi("سایر"), r.value or 0)
                for r in q
            ], columns=["دسته", "مقدار"])


        def on_data_ready(df):
            fig.clf() 
            ax = fig.add_subplot(111) 
            ax.clear()

            if not df.empty:
                ax.pie(df["مقدار"], labels=df["دسته"], autopct='%1.1f%%', startangle=90)

            ax.set_title(farsi("درصد فروش بر حسب دسته"))
            fig.tight_layout()
            canvas.draw()
            w.df = df


        def load():
            btn_report.setEnabled(False)
            self._category_pie_worker = QueryWorker(query_func)
            self._category_pie_worker.dataReady.connect(lambda df: (on_data_ready(df), btn_report.setEnabled(True)))
            self._category_pie_worker.error.connect(
                lambda message: (QMessageBox.warning(self, "خطا در گزارش دسته‌ها", message), btn_report.setEnabled(True))
            )
            self._category_pie_worker.start()

        btn_report.clicked.connect(load)
        btn_refresh.clicked.connect(load)

        return w

    # -------------------------------------------------------------------------
