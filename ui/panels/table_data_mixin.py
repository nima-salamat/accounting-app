"""Filtering, pagination, rendering and read-side table actions."""
from functools import partial

from peewee import DateField, DateTimeField, DecimalField, FloatField, ForeignKeyField, IntegerField
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QAction, QMenu, QMessageBox, QPushButton, QTableWidgetItem,
)

from ui.thread import TrackingQThread as QThread
from ui.panels.data_workers import DataLoader
from ui.panels.date_utils import to_jalali
from ui.panels.image_widgets import PreviewDialog


class TableDataMixin:
    def _toggle_sidebar(self):
        if self.toggle_btn.isChecked():
            self.sidebar.show()
            self.toggle_btn.setText("❮")
        else:
            self.sidebar.hide()
            self.toggle_btn.setText("❯")

    def _toggle_date_group(self, state):
        self.date_group.setVisible(state == Qt.Checked)

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
        max_page = max(1, (self.total_rows - 1) // self.page_size + 1)
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
        self._load_generation = getattr(self, "_load_generation", 0) + 1
        request_id = self._load_generation
        loader = DataLoader(
            self.model, self.search_input.text(), list(self.sort_fields), self.page_size, self.current_page,
            self.cb_enable_date.isChecked(), self.dt_from_date.text(), self.dt_from_time.text(),
            self.dt_to_date.text(), self.dt_to_time.text(), dict(self.lbl2fld), list(self._searchable),
            request_id=request_id,
        )
        self.loader = loader
        thread = QThread(self)
        loader.moveToThread(thread)
        thread.started.connect(loader.load_data, Qt.QueuedConnection)
        loader.result_ready.connect(self._on_query_result, Qt.QueuedConnection)
        loader.failure.connect(self._on_query_error, Qt.QueuedConnection)
        loader.finished.connect(thread.quit)
        loader.finished.connect(loader.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        self.search_input.setEnabled(False)
        self.sort_field_combo.setEnabled(False)
        self.data_table.setEnabled(False)

    def _on_query_result(self, data, total_rows, page, request_id):
        if request_id != getattr(self, "_load_generation", 0):
            return
        self.current_page = max(1, int(page))
        self.page_input.setText(str(self.current_page))
        self._on_data_loaded(data, total_rows)

    def _on_query_error(self, message, request_id):
        if request_id != getattr(self, "_load_generation", 0):
            return
        self._on_load_error(message)

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
