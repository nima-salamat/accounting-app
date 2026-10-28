"""Create, update, delete and export actions for the generic CRUD table."""
from PySide2.QtWidgets import QDialog, QFileDialog, QMessageBox
from ui.thread import TrackingQThread as QThread
from ui.panels.data_workers import RecordAdder, RecordEditor, RecordDeleter, Exporter
from ui.panels.record_dialog import RecordDialog


class TableCrudMixin:
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
        if "password" in self._create:
            raw_pw = data.get("password", "")
            if not raw_pw:
                QMessageBox.warning(self, "رمز عبور لازم است", "برای ساخت کاربر جدید باید رمز عبور تعیین کنید.")
                return
            data["password"] = raw_pw
        else:
            data.pop("password", None)

        self.adder = RecordAdder(self.model, data, self._image_fields)
        self.thread = QThread(self)
        self.adder.moveToThread(self.thread)

        self.thread.started.connect(self.adder.add_record)
        self.adder.added.connect(self._on_record_added)
        self.adder.error.connect(self._on_record_error)

        self.adder.added.connect(self.thread.quit)
        self.adder.error.connect(self.thread.quit)
        self.thread.finished.connect(self.adder.deleteLater)
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
        raw_pw = data.pop("password", "")
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
        self.thread.finished.connect(self.editor.deleteLater)
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
            self.thread.finished.connect(self.deleter.deleteLater)
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
        self.thread.finished.connect(self.exporter.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        self.data_table.setEnabled(False)


    def _on_export_finished(self):
        QMessageBox.information(self, "موفقیت", "داده‌ها با موفقیت ذخیره شدند.")
        self.data_table.setEnabled(True)

    def _on_export_error(self, error_msg):
        QMessageBox.critical(self, "خطا در ذخیره", error_msg)
        self.data_table.setEnabled(True)
