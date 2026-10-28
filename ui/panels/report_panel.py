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

    def __init__(self, query_func):
        super().__init__()
        self.query_func = query_func

    def run(self):
        df = self.query_func()
        self.dataReady.emit(df)


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
            # fetch and serialize
            recs = list(Receipt.select().where(Receipt.created_at.between(self.start_dt, self.end_dt)))
            items = list(ReceiptProduct.select().where(
                ReceiptProduct.receipt.in_([r.id for r in recs])
            ))
            sum_total = sum(r.total_price for r in recs)
            sum_buy = sum(p.buy_price * p.quantity for p in items)

            serial_recs = [ { field.name: getattr(r, field.name)
                              for field in Receipt._meta.fields.values() }
                            for r in recs ]
            for d in serial_recs:
                d['created_at'] = to_jalali(d['created_at'])

            serial_items = [ { field.name: getattr(i, field.name)
                               for field in ReceiptProduct._meta.fields.values() }
                             for i in items ]

            self.dataReady.emit(serial_recs, serial_items, len(recs), sum_total, sum_buy)
        except Exception as e:
            self.error.emit(str(e))


class QueryWorker(QThread):
    dataReady = Signal(pd.DataFrame)
    def __init__(self, query_func):
        super().__init__()
        self.query_func = query_func
    def run(self):
        df = self.query_func()
        self.dataReady.emit(df)


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
        
       
        qs = Product.select(Product.name)\
                    .where(Product.name.contains(text))\
                    .limit(10)
        results = [p.name for p in qs]
        
        
        if results != self.string_model.stringList():
            self.string_model.setStringList(results)
     
        if results:

            self.completer.complete()
        else:
            self.completer.popup().hide()

# Worker thread for async data loading
class DataLoader(QThread):
    dataLoaded = Signal(pd.DataFrame)
    def __init__(self, query_func):
        super().__init__()
        self.query_func = query_func
    def run(self):
        df = self.query_func()
        self.dataLoaded.emit(df)

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
class ProductSalesChartPanel(QMainWindow):
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
        
            fmt_map = {
                "ساعت": "%Y-%m-%d %H",
                "روز":   "%Y-%m-%d",
                "ماه":   "%Y-%m"
            }
            fmt = fmt_map[cb.currentText()]

            cache_key = f"sales_time_{fmt}_{start}_{end}"
            if cache_key in cache:
                return cache[cache_key]
            qs = (Receipt
                .select(fn.strftime(fmt, Receipt.created_at).alias('t'),
                        fn.COUNT(Receipt.id).alias('cnt'))
                .where(Receipt.payed==True, Receipt.created_at >= start,
                    Receipt.created_at <= end)
                .group_by(SQL('t')).order_by(SQL('t')))
            
            df = pd.DataFrame([{"زمان":to_jalali(r.t), "تعداد":r.cnt} for r in qs])
            print(df)
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
            btn_load.setEnabled(False)
            self._sales_time_worker = QueryWorker(query_func)
            self._sales_time_worker.dataReady.connect(lambda df: (on_data_ready(df), btn_load.setEnabled(True)))
            self._sales_time_worker.start()

        btn_load.clicked.connect(load)
        btn_refresh.clicked.connect(load)

        return w


    def _sales_product_tab(self):


        splitter = QSplitter(Qt.Vertical)
        top_widget = QWidget()
        bottom_widget = QWidget()

        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setSizes([300, 300])


        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(6, 6, 6, 6)
        top_layout.setSpacing(4)

        date_group, dt_from_date, dt_from_time, dt_to_date, dt_to_time = self._make_date_group()
        top_layout.addWidget(date_group)

        filters_layout = QHBoxLayout()
        filters_layout.setSpacing(6)

        payed_cb = QComboBox(); payed_cb.addItems(["همه", "پرداخت شده", "پرداخت نشده"])
        user_cb = QComboBox(); user_cb.addItem("همه کاربران"); user_cb.addItems([u.username for u in User.select()])
        cat_cb = QComboBox(); cat_cb.addItem("همه دسته‌ها"); cat_cb.addItems([c.name for c in Category.select()])
        price_cb = QComboBox(); price_cb.addItems(["قیمت فروش", "قیمت خرید"])

        filters_layout.addWidget(QLabel("پرداخت:")); filters_layout.addWidget(payed_cb)
        filters_layout.addWidget(QLabel("کاربر:")); filters_layout.addWidget(user_cb)
        filters_layout.addWidget(QLabel("دسته:")); filters_layout.addWidget(cat_cb)
        filters_layout.addWidget(QLabel("قیمت:")); filters_layout.addWidget(price_cb)

        top_layout.addLayout(filters_layout)

        btn_bar = QPushButton("بارگذاری")
        btn_refresh = QPushButton("رفرش")
        btn_export_table = QPushButton("خروجی جدول")
        btn_show_table = QPushButton("نمایش جدول")

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.addWidget(btn_bar)
        btn_layout.addWidget(btn_refresh)
        btn_layout.addWidget(btn_export_table)
        btn_layout.addWidget(btn_show_table)
        top_layout.addLayout(btn_layout)


        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(4, 4, 4, 4)
        fig = Figure(figsize=(8, 4))
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        bottom_layout.addWidget(canvas)


        def export_table():
            path, _ = QFileDialog.getSaveFileName(self, "ذخیره جدول", filter="CSV Files (*.csv)")
            if path and hasattr(splitter, 'df'):
                splitter.df.to_csv(path, index=False)


        def show_table_dialog():
            if not hasattr(splitter, 'df') or splitter.df.empty:
                QMessageBox.warning(self, "هشدار", "داده‌ای برای نمایش وجود ندارد.")
                return
            dlg = QDialog(self)
            dlg.setWindowTitle("جدول فروش محصولات")
            dlg.resize(600, 400)
            layout = QVBoxLayout(dlg)

            view = QTableView()
            model = PandasModel(splitter.df)
            view.setModel(model)
            view.setSortingEnabled(True)
            view.setAlternatingRowColors(True)
            view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(view)

            dlg.exec_()

  
        def query_func():
            try:
                start_j = f"{dt_from_date.text()} {dt_from_time.text()}:00".replace("/", "-")
                end_j = f"{dt_to_date.text()} {dt_to_time.text()}:00".replace("/", "-")
                start = from_jalali(start_j, is_datetime=True)
                end = from_jalali(end_j, is_datetime=True)
            except Exception as e:
                dlg = QDialog(self)
                dlg.setWindowTitle("خطا در تبدیل تاریخ")
                QVBoxLayout(dlg).addWidget(QLabel(f"فرمت تاریخ یا زمان نادرست است.\n{e}", dlg))
                dlg.exec_()
                return pd.DataFrame()

            q = ReceiptProduct.select(
                    ReceiptProduct.product,
                    fn.SUM(ReceiptProduct.quantity).alias('sold'),
                    fn.SUM(ReceiptProduct.quantity * getattr(
                        ReceiptProduct,
                        'sell_price' if price_cb.currentText() == 'قیمت فروش' else 'buy_price'
                    )).alias('amount')
                ).join(Receipt).where(Receipt.created_at >= start,
    Receipt.created_at <= end)

            if payed_cb.currentText() == 'پرداخت شده':
                q = q.where(Receipt.payed == True)
            elif payed_cb.currentText() == 'پرداخت نشده':
                q = q.where(Receipt.payed == False)

            if user_cb.currentIndex() > 0:
                usr = User.get(User.username == user_cb.currentText())
                q = q.where(Receipt.user == usr)

            if cat_cb.currentIndex() > 0:
                cat = Category.get(Category.name == cat_cb.currentText())
                q = q.join(Product, on=(ReceiptProduct.product == Product.id)).where(Product.category == cat)

            q = q.group_by(ReceiptProduct.product).order_by(fn.SUM(ReceiptProduct.quantity).desc())

            data = []
            for r in q:
                prod = getattr(r, 'product', None)
                name = prod.name if prod and getattr(prod, 'name', None) else "—"
                data.append({
                    "product": farsi(name),
                    "quantity": r.sold or 0,
                    "price": r.amount or 0
                })
            return pd.DataFrame(data)

        def on_data_ready(df):
            fig.clf()
            ax = fig.add_subplot(111)
            if df is not None and not df.empty:
                ax.bar(df["product"], df["quantity"])
            ax.set_title(farsi("فروش بر حسب محصول"))
            ax.tick_params(axis='x', rotation=45)
            fig.tight_layout()
            canvas.draw()

            if df is not None and not df.empty:
                splitter.df = df


        def load():
            btn_bar.setEnabled(False)
            self._sales_product_worker = QueryWorker(query_func)
            self._sales_product_worker.dataReady.connect(lambda df: (on_data_ready(df), btn_bar.setEnabled(True)))
            self._sales_product_worker.start()

        btn_bar.clicked.connect(load)
        btn_refresh.clicked.connect(load)
        btn_export_table.clicked.connect(export_table)
        btn_show_table.clicked.connect(show_table_dialog)

        return splitter



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
            self._category_pie_worker.start()

        btn_report.clicked.connect(load)
        btn_refresh.clicked.connect(load)

        return w

    # -------------------------------------------------------------------------



    
    def _product_search(self):
        product_name = self.line.line.text().strip()
        if not product_name:
            return  
        from jalali_core import JalaliToGregorian
       
        try:
            start_j = f"{self.dt_from_date.text()} {self.dt_from_time.text()}:00".replace("/", "-")
            end_j = f"{self.dt_to_date.text()} {self.dt_to_time.text()}:00".replace("/", "-")

            start = from_jalali(start_j, is_datetime=True)
            end = from_jalali(end_j, is_datetime=True)

        except ValueError:
            dlg = QDialog(self)
            dlg.setWindowTitle("خطا")
            lbl = QLabel("فرمت تاریخ یا زمان نادرست است.", dlg)
            QVBoxLayout(dlg).addWidget(lbl)
            dlg.exec_()
            return


        
        try:
            product = Product.get(Product.name == product_name)
        except Product.DoesNotExist:
            dlg = QDialog(self)
            dlg.setWindowTitle("گزارش")
            lbl = QLabel("محصول یافت نشد.", dlg)
            QVBoxLayout(dlg).addWidget(lbl)
            dlg.exec_()
            return

        query = (ReceiptProduct
            .select(Receipt.created_at,
                    ReceiptProduct.quantity,
                    ReceiptProduct.sell_price,
                    ReceiptProduct.buy_price)
            .join(Receipt)
            .where(
                (ReceiptProduct.product == product) &
                (Receipt.created_at >= start) &
                (Receipt.created_at <= end)
            )
            .order_by(Receipt.created_at))


        count = query.count()
        if count == 0:
            dlg = QDialog(self)
            dlg.setWindowTitle("گزارش")
            lbl = QLabel("هیچ فروشی در این بازه یافت نشد.", dlg)
            QVBoxLayout(dlg).addWidget(lbl)
            dlg.exec_()
            return

    
        self.table.clear()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "تاریخ فاکتور", "تعداد", "مبلغ فروش", "مبلغ خرید", "سود"
        ])
        self.table.setRowCount(count + 1)

        total_sales = 0.0
        total_profit = 0.0

        for row, item in enumerate(query):
            date_str = to_jalali(item.receipt.created_at)
            qty = item.quantity
            sale = item.sell_price * qty
            cost = item.buy_price * qty
            profit = sale - cost

            total_sales += sale
            total_profit += profit

            self.table.setItem(row, 0, QTableWidgetItem(date_str))
            self.table.setItem(row, 1, QTableWidgetItem(str(qty)))
            self.table.setItem(row, 2, QTableWidgetItem(f"{sale:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{cost:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{profit:.2f}"))


        footer = ["جمع کل:", "", f"{total_sales:.2f}", "", f"{total_profit:.2f}"]
        for col, text in enumerate(footer):
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(count, col, item)

        self.table.resizeColumnsToContents()
        self.lbl_totals.setText(
            f"مجموع فروش: {total_sales:.2f}    سود خالص: {total_profit:.2f}"
            )
        
        


    def _product_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 1. SearchLineEdit 
        self.line = SearchLineEdit()
        layout.addWidget(self.line)

        # Date filter group
        self.date_group = QGroupBox("بازه زمانی")
        date_layout = QVBoxLayout(self.date_group)

        # From section
        from_layout = QHBoxLayout()
        from_layout.addWidget(QLabel("از:"))
        self.dt_from_date = QLineEdit()
        self.dt_from_date.setPlaceholderText("روز/ماه/سال")
        self.dt_from_date.setText(JalaliDatetime.now().strftime('%Y/%m/%d'))
        from_layout.addWidget(self.dt_from_date)
        self.dt_from_time = QLineEdit()
        self.dt_from_time.setPlaceholderText("ساعت:دقیقه")
        self.dt_from_time.setText("00:00")
        from_layout.addWidget(self.dt_from_time)
        date_layout.addLayout(from_layout)


        to_layout = QHBoxLayout()
        to_layout.addWidget(QLabel("تا:"))
        self.dt_to_date = QLineEdit()
        self.dt_to_date.setPlaceholderText("روز/ماه/سال")
        self.dt_to_date.setText(jalali_tomorrow_date().strftime('%Y/%m/%d'))
        to_layout.addWidget(self.dt_to_date)
        self.dt_to_time = QLineEdit()
        self.dt_to_time.setPlaceholderText("ساعت:دقیقه")
        self.dt_to_time.setText("0:0")
        to_layout.addWidget(self.dt_to_time)
        date_layout.addLayout(to_layout)

        layout.addWidget(self.date_group)

        btn_report = QPushButton("گزارش")
        btn_report.clicked.connect(self._product_search)
        layout.addWidget(btn_report)

        # Scrollable table area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.table = QTableWidget()
        self.scroll.setWidget(self.table)
        layout.addWidget(self.scroll)

       
        self.lbl_totals = QLabel()
        self.lbl_totals.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_totals)

        return widget
    
    
    def _all_products_summary_tab(self):
        w = QWidget(); lo = QVBoxLayout(w)
        date_group, dt_from_date, dt_from_time, dt_to_date, dt_to_time = self._make_date_group(); lo.addWidget(date_group)

        btn = QPushButton("محاسبه فروش همه محصولات")
        lo.addWidget(btn)

        table = QTableWidget(); lo.addWidget(table)
        lbl = QLabel(); lo.addWidget(lbl)
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["محصول", "تعداد", "مبلغ فروش", "مبلغ خرید", "سود", "زمان فاکتور"])

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
            self._summary_worker = ReportWorker(query_func)
            self._summary_worker.dataReady.connect(on_data_ready)
            self._summary_worker.start()

        btn.clicked.connect(run_worker)
       
        return w


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