import os
from PySide2.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QMessageBox, QScrollArea, QSizePolicy, QTableWidget, QCompleter,
    QTableWidgetItem, QTabWidget, QHeaderView, QCheckBox, QSizeGrip, QLayout, QSplitter, QLineEdit, QFrame
)
from PySide2.QtGui import QPixmap, Qt, QRegion, QFont
from PySide2.QtCore import QTimer, QEasingCurve, QPropertyAnimation, QSize, QPoint, QRect, Property, Signal
from PySide2.QtCore import QParallelAnimationGroup, QStringListModel
from collections import defaultdict
from datetime import datetime, date
from db.models import Product, Receipt, ReceiptProduct, Category
from accounting_app.services.sales import record_sale
from manager.db import DBManager
from ui.base_panel import RecordDialog, RecordAdder, QDialog, to_jalali
from functools import partial
from PySide2.QtCore import QVariantAnimation
import random
import hashlib

from ui.thread import TrackingQThread
QThread = TrackingQThread

class CategoryProductFetcher(QThread):
    data_fetched = Signal(list, list)
    error = Signal(str)

    def run(self):
        try:
            with DBManager():
                products = list(
                    Product.select()
                    .where(Product.custom_product == False)
                    .prefetch(Category)
                )
                categories = list(Category.select())
            self.data_fetched.emit(products, categories)
        except Exception as exc:
            self.error.emit(str(exc))

class ReceiptFetcher(QThread):
    receipts_fetched = Signal(list)
    error = Signal(str)

    def run(self):
        try:
            with DBManager():
                receipts = list(
                    Receipt.select().order_by(Receipt.created_at.desc()).limit(25)
                )
            self.receipts_fetched.emit(receipts)
        except Exception as exc:
            self.error.emit(str(exc))

class CheckoutWorker(QThread):
    checkout_done = Signal(bool, str)

    def __init__(self, cart, user, payed: bool, edit_mode: bool = False, receipt_to_delete=None):
        super().__init__()
        self.cart = cart
        self.user = user
        self.payed = payed
        self.edit_mode = edit_mode
        self.receipt_to_delete = receipt_to_delete

    def run(self):
        try:
            record_sale(
                self.cart,
                self.user,
                self.payed,
                edit_mode=self.edit_mode,
                receipt_to_edit=self.receipt_to_delete,
            )
            self.checkout_done.emit(True, "فروش با موفقیت ثبت شد.")
        except ValueError as exc:
            self.checkout_done.emit(False, str(exc))
        except Exception:
            import logging
            logging.exception("Unable to persist checkout")
            self.checkout_done.emit(False, "خطایی در ثبت فروش رخ داد.")
