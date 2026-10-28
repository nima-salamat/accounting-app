from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QDateTimeEdit, QTableView, QHeaderView,
    QFileDialog, QMessageBox, QScrollArea, QSizePolicy, QSplitter
)
from PySide2.QtCore import Qt, QDateTime, QTime
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from peewee import fn
import pandas as pd

from db.models import Product, Receipt, ReceiptProduct, Warehouse
from ui.utils import PandasModel

class DynamicComparisonWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.compare_rows = []
        self._build_ui()

    def _build_ui(self):
       
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

      
        container_widget = QWidget()
        container_layout = QVBoxLayout(container_widget)

        
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)

        scroll_rows = QScrollArea()
        scroll_rows.setWidgetResizable(True)
        scroll_rows.setWidget(self.rows_container)
        scroll_rows.setFixedHeight(200) 

        container_layout.addWidget(scroll_rows)

        btn_add = QPushButton("+ افزودن مقایسه")
        btn_add.clicked.connect(self._add_row)
        container_layout.addWidget(btn_add)

        btn_load = QPushButton("بارگذاری نمودار")
        btn_load.clicked.connect(self._load_chart)
        container_layout.addWidget(btn_load)

        self.fig = Figure(figsize=(12, 6)) 
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


        self.table = QTableView()
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setMinimumHeight(300)

        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setWidget(self.table)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.canvas)
        splitter.addWidget(table_scroll)
        container_layout.addWidget(splitter)

        scroll_area.setWidget(container_widget)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll_area)

    def _add_row(self):
        row = {}
        hl = QHBoxLayout()

        row["kind"] = QComboBox()
        row["kind"].addItems(["فروش", "انبار"])
        hl.addWidget(QLabel("نوع:"))
        hl.addWidget(row["kind"])

        row["product"] = QComboBox()
        for p in Product.select():
            row["product"].addItem(p.name, p.id)
        hl.addWidget(QLabel("محصول:"))
        hl.addWidget(row["product"])

        row["from"] = QDateTimeEdit(QDateTime.currentDateTime().addDays(-7))
        row["from"].setDisplayFormat("yyyy-MM-dd HH:mm")
        row["from"].setTime(QTime(6, 0))
        hl.addWidget(QLabel("از:"))
        hl.addWidget(row["from"])

        row["to"] = QDateTimeEdit(QDateTime.currentDateTime())
        row["to"].setDisplayFormat("yyyy-MM-dd HH:mm")
        hl.addWidget(QLabel("تا:"))
        hl.addWidget(row["to"])

        remove_btn = QPushButton("🗑️")
        remove_btn.clicked.connect(lambda: self._remove_row(row, hl))
        hl.addWidget(remove_btn)

        self.rows_layout.addLayout(hl)
        self.compare_rows.append((row, hl))

    def _remove_row(self, row, layout):
        for widget in row.values():
            widget.deleteLater()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.compare_rows = [(r, l) for r, l in self.compare_rows if l != layout]

    def _load_chart(self):
        if not self.compare_rows:
            QMessageBox.warning(self, "هشدار", "حداقل یک ردیف مقایسه اضافه کنید.")
            return

        self.fig.clear()
        ax = self.fig.subplots()

        df_final = pd.DataFrame()
        for row, _ in self.compare_rows:
            kind = row["kind"].currentText()
            pid = row["product"].currentData()
            name = row["product"].currentText()
            s = row["from"].dateTime().toPython()
            e = row["to"].dateTime().toPython()

            if kind == "فروش":
                qs = (
                    ReceiptProduct
                    .select(fn.strftime('%Y-%m-%d', Receipt.created_at).alias('day'),
                            fn.SUM(ReceiptProduct.quantity).alias('qty'))
                    .join(Receipt)
                    .where(
                        Receipt.payed == True,
                        Receipt.created_at.between(s, e),
                        ReceiptProduct.product == pid
                    )
                    .group_by('day').order_by('day')
                )
                df = pd.DataFrame([(r.day, r.qty) for r in qs], columns=["day", name])
            else: 
                qs = (
                    Warehouse
                    .select(fn.SUM(Warehouse.amount).alias('qty'))
                    .where(Warehouse.name == name)
                )
                total_amount = qs.scalar() or 0
                dates = pd.date_range(s, e, freq='D').strftime("%Y-%m-%d")
                df = pd.DataFrame({"day": dates, name: [total_amount] * len(dates)})

            if not df.empty:
                if df_final.empty:
                    df_final = df
                else:
                    df_final = pd.merge(df_final, df, on="day", how="outer")

                ax.plot(df["day"], df[name], label=f"{kind}: {name}", marker='o')

        if df_final.empty:
            QMessageBox.warning(self, "هشدار", "داده‌ای برای نمایش وجود ندارد.")
            return

        ax.set_title("مقایسه فروش و موجودی انبار در بازه‌های زمانی")
        ax.legend()
        ax.tick_params(axis='x', rotation=45)
        self.fig.tight_layout()
        self.canvas.draw()

        df_final = df_final.fillna(0).sort_values("day")
        model = PandasModel(df_final)
        self.table.setModel(model)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self._export_table(df_final)

    def _export_table(self, df: pd.DataFrame):
        path, _ = QFileDialog.getSaveFileName(self, "خروجی جدول مقایسه", "", "CSV Files (*.csv);;Excel Files (*.xlsx)")
        if path:
            if path.endswith(".csv"):
                df.to_csv(path, index=False, encoding='utf-8-sig')
            else:
                df.to_excel(path, index=False)
            QMessageBox.information(self, "ذخیره شد", f"جدول در\n{path}\nذخیره شد")