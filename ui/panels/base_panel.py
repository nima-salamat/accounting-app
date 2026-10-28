"""Generic CRUD table with filtering, pagination and background operations."""
from functools import partial

from peewee import *
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


class TableManagement(QWidget):
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

    def _toggle_sidebar(self):
        if self.toggle_btn.isChecked():
            self.sidebar.show()
            self.toggle_btn.setText("❮")
        else:
            self.sidebar.hide()
            self.toggle_btn.setText("❯")

    def _toggle_date_group(self, state):
        should_enable = state == Qt.Checked
        self.date_group.setVisible(not self.date_group.isVisible())

    def setModel(self, model):
        self.model = model
        self._all_fields = {n: f for n, f in model._meta.fields.items() if n not in self._exclude}
        if not self._display:
            self._display = list(self._all_fields)
        self.fields = {n: self._all_fields[n] for n in self._display if n in self._all_fields}
        if not self._create:
            self._create = list(self.fields)
        if not self._searchable:
            self._searchable = list(self.fields)

        self.numeric_fields = [
            name for name, field in self.fields.items()
            if isinstance(field, (IntegerField, FloatField, DecimalField))
        ]

        headers = [self._labels.get(n, n) for n in self._display] + ["ویرایش", "حذف"]
        self.data_table.setColumnCount(len(headers))
        self.data_table.setHorizontalHeaderLabels(headers)

        for field in self.fields:
            label = self._labels.get(field, field)
            self.sort_field_combo.addItem(label, field)
        self.sort_order_combo.addItem("صعودی", True)
        self.sort_order_combo.addItem("نزولی", False)

        if self.sort_fields:
            field, asc = self.sort_fields[0]
            index = self.sort_field_combo.findData(field)
            if index >= 0:
                self.sort_field_combo.setCurrentIndex(index)
            else:
                self.sort_field_combo.setCurrentIndex(0)
                first_field = list(self.fields.keys())[0]
                self.sort_fields = [(first_field, asc)]
            order_index = 0 if asc else 1
            self.sort_order_combo.setCurrentIndex(order_index)
        else:
            if self.fields:
                first_field = list(self.fields.keys())[0]
                self.sort_fields = [(first_field, True)]
                self.sort_field_combo.setCurrentIndex(0)
                self.sort_order_combo.setCurrentIndex(0)

        self.load_data()

    def _on_sort_change(self):
        field = self.sort_field_combo.currentData()
        if field:
            order = self.sort_order_combo.currentData()
            self.sort_fields = [(field, order)]
            self.load_data()

    def _on_search(self):
        self.current_page = 1
        self.load_data()

    def _on_page_input_change(self):
        try:
            page = int(self.page_input.text())
            max_page = max(1, (self.total_rows - 1) // self.page_size + 1)
            if 1 <= page <= max_page:
                self.current_page = page
                self.load_data()
            else:
                QMessageBox.warning(self, "صفحه نامعتبر", f"شماره صفحه باید بین 1 و {max_page} باشد.")
                self.page_input.setText(str(self.current_page))
        except ValueError:
            QMessageBox.warning(self, "ورودی نامعتبر", "شماره صفحه باید یک عدد صحیح باشد.")
            self.page_input.setText(str(self.current_page))

    def _on_page_size_change(self):
        try:
            val = int(self.le_page_size.text())
            if val > 0:
                self.page_size = val
                self.current_page = 1
                self.load_data()
        except ValueError:
            pass

    def _go_prev(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def _go_next(self):
        max_page = (self.total_rows - 1) // self.page_size + 1
        if self.current_page < max_page:
            self.current_page += 1
            self.load_data()

    def _on_context_menu(self, pos):
        item = self.data_table.itemAt(pos)
        if not item:
            return
        r, c = item.row(), item.column()
        key = list(self.fields)[c] if c < len(self.fields) else None
        menu = QMenu()

        if key in self._image_fields:
            img = self.data_table.item(r, c).text()
            if img:
                act = QAction("پیش‌نمایش", self)
                act.triggered.connect(lambda: self._preview_image(img))
                menu.addAction(act)

        if key in self.numeric_fields:
            sum_action = QAction("محاسبه مجموع", self)
            sum_action.triggered.connect(lambda: self._calculate_sum(c))
            menu.addAction(sum_action)

        if not menu.isEmpty():
            menu.exec_(self.data_table.viewport().mapToGlobal(pos))

    def _calculate_sum(self, column):
        selected_items = self.data_table.selectedItems()
        if not selected_items:
            return
        total = 0
        for item in selected_items:
            if item.column() == column:
                try:
                    total += float(item.text())
                except ValueError:
                    pass
        QMessageBox.information(self, "مجموع", f"مجموع مقادیر انتخاب شده: {total}")

    def _preview_image(self, path):
        dlg = PreviewDialog(path, self)
        dlg.exec_()

    def load_data(self):
        self.loader = DataLoader(
            self.model, self.search_input.text(), self.sort_fields, self.page_size, self.current_page,
            self.cb_enable_date.isChecked(), self.dt_from_date.text(), self.dt_from_time.text(),
            self.dt_to_date.text(), self.dt_to_time.text(), self.lbl2fld, self._searchable
        )
        thread = QThread(self)
        self.loader.moveToThread(thread)
        thread.started.connect(self.loader.load_data, Qt.QueuedConnection)
        self.loader.data_loaded.connect(self._on_data_loaded, Qt.QueuedConnection)
        self.loader.error.connect(self._on_load_error, Qt.QueuedConnection)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        self.search_input.setEnabled(False)
        self.sort_field_combo.setEnabled(False)
        self.data_table.setEnabled(False)

    def _on_data_loaded(self, data, total_rows):
        self.data = data
        self.total_rows = total_rows
        self._render_table()
        # Re-enable UI elements
        self.search_input.setEnabled(True)
        self.sort_field_combo.setEnabled(True)
        self.data_table.setEnabled(True)

    def _on_load_error(self, error_msg):
        QMessageBox.critical(self, "خطا در بارگذاری", error_msg)
        # Re-enable UI elements even on error
        self.search_input.setEnabled(True)
        self.sort_field_combo.setEnabled(True)
        self.data_table.setEnabled(True)

    def _render_table(self):
        self.data_table.setRowCount(len(self.data))
        for r, rec in enumerate(self.data):
            print(r, rec)
            for c, key in enumerate(self.fields):
                val = getattr(rec, key)
                f = self._all_fields[key]
                if isinstance(f, (DateField, DateTimeField)):
                    val = to_jalali(val) if val else ""
                elif isinstance(f, (DecimalField, FloatField)):
                    val = f"{val:.2f}" if val is not None else ""
                elif isinstance(f, ForeignKeyField):
                    val = str(val) if val else "— "
                else:
                    val = str(val) if val is not None else ""
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.data_table.setItem(r, c, item)

            btn_e = QPushButton("ویرایش")
            btn_e.setProperty("class", "flat")

            self.data_table.setCellWidget(r, len(self.fields), btn_e)

            btn_d = QPushButton("حذف")
            btn_d.setProperty("class", "flat")
            self.data_table.setCellWidget(r, len(self.fields) + 1, btn_d)
            
            btn_e.clicked.connect(partial(self._on_edit, r))
            btn_d.clicked.connect(partial(self._on_delete, r))

        max_page = max(1, (self.total_rows - 1) // self.page_size + 1)
        self.lbl_page.setText(f"صفحه {self.current_page} / {max_page}")
        self.page_input.setText(str(self.current_page))
        self.lbl_total.setText(str(self.total_rows))

    def _on_add(self):
        dlg = RecordDialog(
            fields={n: self._all_fields[n] for n in self._create},
            model=self.model,
            image_fields=self._image_fields,
            labels=self._labels,
            parent=self
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        data = dlg.data.copy()
        raw_pw = data.get("password", "").strip()
        if "password" in self._create and not raw_pw:
            raw_pw = "12345"
        data['password'] = raw_pw

        self.adder = RecordAdder(self.model, data, self._image_fields)
        self.thread = QThread(self)
        self.adder.moveToThread(self.thread)

        self.thread.started.connect(self.adder.add_record)
        self.adder.added.connect(self._on_record_added)
        self.adder.error.connect(self._on_record_error)

        self.adder.added.connect(self.thread.quit)
        self.adder.error.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        self.data_table.setEnabled(False)


    def _on_record_added(self):
        self.load_data()
        self.data_table.setEnabled(True)

    def _on_record_error(self, error_msg):
        QMessageBox.critical(self, "خطا در افزودن", error_msg)
        self.data_table.setEnabled(True)

    def _on_edit(self, row):
        print(row)
        rec = self.data[row]
        pk_name = self.model._meta.primary_key.name
        pk_val = getattr(rec, pk_name)

        old_images = {img: getattr(rec, img) for img in self._image_fields}

        dlg = RecordDialog(
            fields={n: self._all_fields[n] for n in self._create},
            model=self.model,
            image_fields=self._image_fields,
            labels=self._labels,
            initial={n: getattr(rec, n) for n in self._create},
            parent=self
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        data = dlg.data.copy()
        raw_pw = data.pop("password", "").strip()
        if raw_pw:
            data['password'] = raw_pw

        self.editor = RecordEditor(self.model, pk_val, data, self._image_fields, old_images)
        self.thread = QThread(self)
        self.editor.moveToThread(self.thread)

        self.thread.started.connect(self.editor.edit_record)
        self.editor.edited.connect(self._on_record_edited)
        self.editor.error.connect(self._on_record_error)

        self.editor.edited.connect(self.thread.quit)
        self.editor.error.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        self.data_table.setEnabled(False)


    def _on_record_edited(self):
        self.load_data()
        self.data_table.setEnabled(True)

    def _on_delete(self, row):
        if QMessageBox.question(self, "حذف", "آیا می‌خواهید این را حذف کنید؟") == QMessageBox.Yes:
            rec = self.data[row]
            pk_name = self.model._meta.primary_key.name
            pk_val = getattr(rec, pk_name)

            self.deleter = RecordDeleter(self.model, pk_val, self._image_fields)
            self.thread = QThread(self)
            self.deleter.moveToThread(self.thread)

            self.thread.started.connect(self.deleter.delete_record)
            self.deleter.deleted.connect(self._on_record_deleted)
            self.deleter.error.connect(self._on_record_error)

            # وقتی عملیات تموم شد thread رو ببند
            self.deleter.deleted.connect(self.thread.quit)
            self.deleter.error.connect(self.thread.quit)
            self.thread.finished.connect(self.thread.deleteLater)

            self.thread.start()
            self.data_table.setEnabled(False)


    def _on_record_deleted(self):
        self.load_data()
        self.data_table.setEnabled(True)

    def _on_export(self):
        if not self.data:
            QMessageBox.information(self, "بدون داده", "هیچ داده‌ای برای خروجی گرفتن وجود ندارد.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "ذخیره به عنوان", "", "CSV files (*.csv)")
        if not path:
            return

        self.exporter = Exporter(self.data, path, self._display, self._all_fields, self._labels, self.numeric_fields)
        self.thread = QThread(self)
        self.exporter.moveToThread(self.thread)

        self.thread.started.connect(self.exporter.export)
        self.exporter.finished.connect(self._on_export_finished)
        self.exporter.error.connect(self._on_export_error)

        # وقتی عملیات تمام شد، thread را ببند
        self.exporter.finished.connect(self.thread.quit)
        self.exporter.error.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        self.data_table.setEnabled(False)


    def _on_export_finished(self):
        QMessageBox.information(self, "موفقیت", "داده‌ها با موفقیت ذخیره شدند.")
        self.data_table.setEnabled(True)

    def _on_export_error(self, error_msg):
        QMessageBox.critical(self, "خطا در ذخیره", error_msg)
        self.data_table.setEnabled(True)
