"""Advanced report window assembled from focused analytics mixins."""
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

from ui.panels.report_analytics_mixin import ReportAnalyticsMixin
from ui.panels.report_operations_mixin import ReportOperationsMixin


class ProductSalesChartPanel(ReportAnalyticsMixin, ReportOperationsMixin, QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("پنل گزارش‌گیری پیشرفته (V2)")
        self.resize(1600, 1000)

        # Apply a light theme
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(245, 245, 245))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        self.setPalette(palette)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Adding tabs with scroll
        self.tabs.addTab(wrap_scrollable(self._overview_tab()), "نمای کلی")
        self.tabs.addTab(wrap_scrollable(self._sales_time_tab()), "فروش بر حسب زمان")
        self.tabs.addTab(wrap_scrollable(self._sales_product_tab()), "فروش بر حسب محصول")
        self.tabs.addTab(wrap_scrollable(self._category_pie_tab()), "درصد فروش بر حسب دسته")
        self.tabs.addTab(wrap_scrollable(self._inventory_tab()), "گزارش خرید")
        self.tabs.addTab(wrap_scrollable(self._product_tab()), "گزارش فروش محصولات")
        self.tabs.addTab(wrap_scrollable(self._all_products_summary_tab()), "فروش همه محصولات")
        self.tabs.addTab(wrap_scrollable(self._purge_tab()), "پاکسازی پایگاه داده")
        self.tabs.addTab(wrap_scrollable(self._check_tab()), "گزارش چک")
        
        

        

        # Menu bar with additional options
        menubar = self.menuBar()


    # -------------------------------------------------------------------------
    def _make_date_group(self):
          # Date filter group
        date_group = QGroupBox("بازه زمانی")
        date_layout = QVBoxLayout(date_group)

        # From section
        from_layout = QHBoxLayout()
        from_layout.addWidget(QLabel("از:"))
        dt_from_date = QLineEdit()
        dt_from_date.setPlaceholderText("روز/ماه/سال")
        dt_from_date.setText(JalaliDatetime.now().strftime('%Y/%m/%d'))
        from_layout.addWidget(dt_from_date)
        dt_from_time = QLineEdit()
        dt_from_time.setPlaceholderText("ساعت:دقیقه")
        dt_from_time.setText("0:0")
        from_layout.addWidget(dt_from_time)
        date_layout.addLayout(from_layout)

        # To section
        to_layout = QHBoxLayout()
        to_layout.addWidget(QLabel("تا:"))
        dt_to_date = QLineEdit()
        dt_to_date.setPlaceholderText("روز/ماه/سال")
        dt_to_date.setText(jalali_tomorrow_date().strftime('%Y/%m/%d'))
        to_layout.addWidget(dt_to_date)
        dt_to_time = QLineEdit()
        dt_to_time.setPlaceholderText("ساعت:دقیقه")
        dt_to_time.setText("0:0")
        to_layout.addWidget(dt_to_time)
        date_layout.addLayout(to_layout)
        return date_group, dt_from_date, dt_from_time, dt_to_date, dt_to_time

    def _add_export_chart_btn(self, layout, fig: Figure):
        btn = QPushButton("ذخیره نمودار (PNG/PDF)")
        btn.clicked.connect(lambda: self._export_chart(fig))
        layout.addWidget(btn, alignment=Qt.AlignRight)

    def _export_chart(self, fig: Figure):
        path, _ = QFileDialog.getSaveFileName(self, "ذخیره نمودار", "", "PNG Files (*.png);;PDF Files (*.pdf)")
        if path:
            fig.savefig(path)
            QMessageBox.information(self, "ذخیره شد", f"نمودار در:\n{path}\nذخیره شد")

    def _export_table(self, df: pd.DataFrame):
        path, _ = QFileDialog.getSaveFileName(self, "ذخیره جدول", "", "CSV (*.csv);;Excel (*.xlsx);;PDF (*.pdf)")
        if path:
            if path.endswith(".csv"):
                df.to_csv(path, index=False, encoding='utf-8-sig')
            elif path.endswith(".xlsx"):
                df.to_excel(path, index=False)
            else:
                df.to_html(path, index=False)  # Simple PDF export via HTML
            QMessageBox.information(self, "ذخیره شد", f"جدول در:\n{path}\nذخیره شد")


    # -------------------------------------------------------------------------
