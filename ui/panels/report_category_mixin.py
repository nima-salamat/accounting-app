"""Overview, time series, product sales, inventory and category reports."""
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

class ReportCategoryMixin:
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

        def query_func(mode):
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
            mode = mode_combo.currentIndex()
            self._category_pie_worker = QueryWorker(lambda: query_func(mode))
            self._category_pie_worker.dataReady.connect(lambda df: (on_data_ready(df), btn_report.setEnabled(True)))
            self._category_pie_worker.error.connect(
                lambda message: (QMessageBox.warning(self, "خطا در گزارش دسته‌ها", message), btn_report.setEnabled(True))
            )
            self._category_pie_worker.start()

        btn_report.clicked.connect(load)
        btn_refresh.clicked.connect(load)

        return w

    # -------------------------------------------------------------------------
