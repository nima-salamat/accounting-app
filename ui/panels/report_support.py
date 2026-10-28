"""Shared report helpers, caches and reusable background workers."""
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
from peewee import fn, SQL, JOIN, ForeignKeyField
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


def farsi(text: str) -> str:
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def to_jalali(dt):
    if isinstance(dt, datetime):
        jdt = jdatetime.datetime.fromgregorian(datetime=dt)
        return jdt.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(dt, date):
        jdt = jdatetime.date.fromgregorian(date=dt)
        return jdt.strftime('%Y-%m-%d')
    return dt

def from_jalali(jalali_str, is_datetime=False):
    try:
        if is_datetime:
            jdt = jdatetime.datetime.strptime(jalali_str, '%Y-%m-%d %H:%M:%S')
            return jdt.togregorian()
        else:
            jdt = jdatetime.date.strptime(jalali_str, '%Y-%m-%d')
            return jdt.togregorian()
    except ValueError as e:
        raise ValueError(f"فرمت تاریخ شمسی نامعتبر است: {jalali_str}")


class ReportWorker(QThread):
    dataReady = Signal(pd.DataFrame)
    error = Signal(str)

    def __init__(self, query_func):
        super().__init__()
        self.query_func = query_func

    def run(self):
        try:
            with DBManager():
                result = self.query_func()
            self.dataReady.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class PurgeWorker(QThread):
    # emit raw data: list of dicts for receipts and items, plus sums
    dataReady = Signal(list, list, int, float, float)
    error = Signal(str)

    def __init__(self, start_dt, end_dt):
        super().__init__()
        self.start_dt = start_dt
        self.end_dt = end_dt

    def run(self):
        try:
            with DBManager():
                recs = list(
                    Receipt.select().where(
                        Receipt.created_at.between(self.start_dt, self.end_dt)
                    )
                )
                receipt_ids = [record.id for record in recs]
                items = list(
                    ReceiptProduct.select().where(
                        ReceiptProduct.receipt.in_(receipt_ids)
                    )
                ) if receipt_ids else []
                sum_total = sum(record.total_price for record in recs)
                sum_buy = sum(item.buy_price * item.quantity for item in items)

                def serialize(record, model):
                    row = {}
                    for field in model._meta.fields.values():
                        if isinstance(field, ForeignKeyField):
                            row[field.name] = getattr(record, field.name + "_id")
                        else:
                            row[field.name] = getattr(record, field.name)
                    return row

                serial_recs = [serialize(record, Receipt) for record in recs]
                for row in serial_recs:
                    row["created_at"] = to_jalali(row["created_at"])
                serial_items = [serialize(item, ReceiptProduct) for item in items]
            self.dataReady.emit(serial_recs, serial_items, len(recs), sum_total, sum_buy)
        except Exception as exc:
            self.error.emit(str(exc))


class QueryWorker(QThread):
    dataReady = Signal(pd.DataFrame)
    error = Signal(str)

    def __init__(self, query_func):
        super().__init__()
        self.query_func = query_func

    def run(self):
        try:
            with DBManager():
                result = self.query_func()
            self.dataReady.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class SearchLineEdit(QWidget):
    def __init__(self):
        super().__init__()
        self.line = QLineEdit(self)
        self.line.setPlaceholderText("نام محصول را بنویس...")
        
       
        self.string_model = QStringListModel(self)
        

        self.completer = QCompleter(self.string_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.line.setCompleter(self.completer)
        
        
        self.line.textEdited.connect(self.update_suggestions)
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.line)
        self.setLayout(layout)

    def update_suggestions(self, text: str):
        text = text.strip()
        if not text:
            self.string_model.setStringList([])
            return
        try:
            with DBManager():
                query = (
                    Product.select(Product.name)
                    .where(Product.name.contains(text))
                    .limit(10)
                )
                results = [product.name for product in query]
        except Exception:
            self.string_model.setStringList([])
            return
        if results != self.string_model.stringList():
            self.string_model.setStringList(results)
        if results:
            self.completer.complete()
        else:
            self.completer.popup().hide()


# Worker thread for async data loading
class DataLoader(QThread):
    dataLoaded = Signal(pd.DataFrame)
    error = Signal(str)

    def __init__(self, query_func):
        super().__init__()
        self.query_func = query_func

    def run(self):
        try:
            with DBManager():
                result = self.query_func()
            self.dataLoaded.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# Cache setup
cache = cachetools.TTLCache(maxsize=100, ttl=300)  # 5-minute cache

# -------------------------------------------------------------------------
def wrap_scrollable(inner: QWidget) -> QWidget:
    outer = QWidget()
    lo = QVBoxLayout(outer)
    lo.setContentsMargins(0,0,0,0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(inner)
    lo.addWidget(scroll)
    return outer

# -------------------------------------------------------------------------
