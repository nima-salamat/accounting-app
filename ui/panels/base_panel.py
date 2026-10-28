"""Generic CRUD table layout with behavior delegated to focused mixins."""
from peewee import DateField, DateTimeField, DecimalField, FloatField, ForeignKeyField, IntegerField
from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QPushButton, QLineEdit, QHBoxLayout,
    QTableWidgetItem, QMessageBox, QDialog, QLabel, QCheckBox, QComboBox, QMenu,
    QFileDialog, QGroupBox, QFrame, QAction,
)
from PySide2.QtCore import Qt

from ui.panels.date_utils import to_jalali, jalali_tomorrow_date, from_jalali, parse_jalali_datetime
from ui.panels.data_workers import DataLoader, RecordAdder, RecordEditor, RecordDeleter, Exporter
from ui.panels.image_widgets import ImageLineEdit, PreviewDialog
from ui.panels.record_dialog import RecordDialog
from ui.thread import TrackingQThread as QThread
from ui.panels.table_data_mixin import TableDataMixin
from ui.panels.table_crud_mixin import TableCrudMixin


class TableManagement(TableDataMixin, TableCrudMixin, QWidget):
    def __init__(self, parent=None,
                 *, display_fields=None, create_fields=None,
                 searchable_fields=None, exclude_fields=None,
                 field_labels=None, image_fields=None,
                 initial_sort=None):
        super().__init__(parent)


        self._display = display_fields or []
        self._create = create_fields or []
        self._searchable = searchable_fields or []
        self._exclude = exclude_fields or []
        self._labels = field_labels or {}
        self._image_fields = image_fields or []
        self.initial_sort = initial_sort or []
        self.lbl2fld = {v: k for k, v in self._labels.items()}

        self.sort_fields = []
        for item in self.initial_sort:
            if isinstance(item, tuple) and len(item) == 2:
                field, asc = item
                field = self.lbl2fld.get(field, field)
                self.sort_fields.append((field, asc))
            elif isinstance(item, str):
                field = self.lbl2fld.get(item, item)
                self.sort_fields.append((field, True))

        self.page_size = 10
        self.current_page = 1
        self.total_rows = 0

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setFrameShape(QFrame.StyledPanel)
        self.sidebar.setMinimumWidth(250)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(12)

        self.cb_enable_date = QCheckBox("فعال کردن فیلتر تاریخ")
        self.cb_enable_date.setChecked(False)
        self.cb_enable_date.stateChanged.connect(self._toggle_date_group)
        sidebar_layout.addWidget(self.cb_enable_date)

        self.date_group = QGroupBox("بازه زمانی")
        self.date_group.setVisible(False)
        date_layout = QVBoxLayout(self.date_group)

        from_layout = QHBoxLayout()
        from_layout.addWidget(QLabel("از:"))
        self.dt_from_date = QLineEdit()
        self.dt_from_date.setPlaceholderText("روز/ماه/سال")
        self.dt_from_date.setText(JalaliDatetime.now().strftime('%Y/%m/%d'))
        from_layout.addWidget(self.dt_from_date)
        self.dt_from_time = QLineEdit()
        self.dt_from_time.setText("0:0")
        self.dt_from_time.setPlaceholderText("دقیقه:ساعت")
        from_layout.addWidget(self.dt_from_time)
        date_layout.addLayout(from_layout)

        to_layout = QHBoxLayout()
        to_layout.addWidget(QLabel("تا:"))
        self.dt_to_date = QLineEdit()
        self.dt_to_date.setPlaceholderText("روز/ماه/سال")
        
        self.dt_to_date.setText(jalali_tomorrow_date().strftime('%Y/%m/%d'))
        to_layout.addWidget(self.dt_to_date)
        self.dt_to_time = QLineEdit()
        self.dt_to_time.setPlaceholderText("دقیقه:ساعت")
        self.dt_to_time.setText("0:0")
        to_layout.addWidget(self.dt_to_time)
        date_layout.addLayout(to_layout)

        sidebar_layout.addWidget(self.date_group)

        self.dt_from_date.editingFinished.connect(self.load_data)
        self.dt_from_time.editingFinished.connect(self.load_data)
        self.dt_to_date.editingFinished.connect(self.load_data)
        self.dt_to_time.editingFinished.connect(self.load_data)
        self.cb_enable_date.stateChanged.connect(self.load_data)

        search_group = QGroupBox("جستجو")
        search_layout = QVBoxLayout(search_group)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("نام فیلد:مقدار,…")
        btn_search = QPushButton("🔍")
        btn_search.clicked.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(btn_search)
        sidebar_layout.addWidget(search_group)

        sort_group = QGroupBox("مرتب‌سازی")
        sort_layout = QVBoxLayout(sort_group)
        sort_layout.addWidget(QLabel("فیلد:"))
        self.sort_field_combo = QComboBox()
        sort_layout.addWidget(self.sort_field_combo)
        sort_layout.addWidget(QLabel("ترتیب:"))
        self.sort_order_combo = QComboBox()
        sort_layout.addWidget(self.sort_order_combo)
        sidebar_layout.addWidget(sort_group)

        sidebar_layout.addStretch()
        main_layout.addWidget(self.sidebar)

        self.toggle_btn = QPushButton("❮")
        self.toggle_btn.setProperty("class", "flat")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(True)
        self.toggle_btn.clicked.connect(self._toggle_sidebar)
        main_layout.addWidget(self.toggle_btn)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(12)

        self.data_table = QTableWidget()
        self.data_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self._on_context_menu)
        content_layout.addWidget(self.data_table)

        pg = QHBoxLayout()
        pg.addStretch()
        for txt, slot in [("◀", self._go_prev), ("▶", self._go_next)]:
            btn = QPushButton(txt)
            btn.clicked.connect(slot)
            pg.addWidget(btn)
        pg.addStretch()
        pg.addWidget(QLabel("دیتا در صفحه:"))
        self.le_page_size = QLineEdit(str(self.page_size))
        self.le_page_size.setFixedWidth(50)
        self.le_page_size.editingFinished.connect(self._on_page_size_change)
        pg.addWidget(self.le_page_size)
        pg.addWidget(QLabel("صفحه:"))
        self.page_input = QLineEdit(str(self.current_page))
        self.page_input.setFixedWidth(50)
        self.page_input.editingFinished.connect(self._on_page_input_change)
        pg.addWidget(self.page_input)
        pg.addWidget(QLabel("کل:"))
        self.lbl_total = QLabel(str(self.total_rows))
        pg.addWidget(self.lbl_total)
        self.lbl_page = QLabel(f"صفحه {self.current_page} / 1")
        pg.addWidget(self.lbl_page)
        pg.addStretch()
        content_layout.addLayout(pg)

        content_layout.addWidget(QFrame(frameShape=QFrame.HLine))
        self.sort_field_combo.currentIndexChanged.connect(self._on_sort_change)
        self.sort_order_combo.currentIndexChanged.connect(self._on_sort_change)

        btns = QHBoxLayout()
        for text, slot in [("➕", self._on_add), ("📤", self._on_export)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btns.addWidget(btn)
        btns.addStretch()
        content_layout.addLayout(btns)

        main_layout.addLayout(content_layout, 1)
