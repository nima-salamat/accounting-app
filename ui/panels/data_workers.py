"""Database workers for CRUD, filtering and CSV export."""
import csv
import os
import operator
from functools import reduce

from peewee import (
    BooleanField, CharField, DateField, DateTimeField, DecimalField, FloatField,
    ForeignKeyField, TextField,
)
from PySide2.QtCore import QObject, Signal, Slot

from accounting_app.services.schema_registry import (
    cleanup_builtin_extension_values, entity_key_for_model,
)
from manager.db import DBManager
from ui.panels.date_utils import parse_jalali_datetime, to_jalali
from accounting_app.services.file_safety import is_managed_image_path


class DataLoader(QObject):
    data_loaded = Signal(list, int)  # Emits data and total_rows
    error = Signal(str)
    finished = Signal()
    page_changed = Signal(int)

    def __init__(self, model, search_text, sort_fields, page_size, current_page, cb_enable_date, dt_from_date, dt_from_time, dt_to_date, dt_to_time, lbl2fld, searchable, parent=None):
        super().__init__(parent)
        self.model = model
        self.search_text = search_text
        self.sort_fields = sort_fields
        self.page_size = page_size
        self.current_page = current_page
        self.cb_enable_date = cb_enable_date
        self.dt_from_date = dt_from_date
        self.dt_from_time = dt_from_time
        self.dt_to_date = dt_to_date
        self.dt_to_time = dt_to_time
        self.lbl2fld = lbl2fld
        self._searchable = searchable

    @Slot()
    def load_data(self):
        try:
            with DBManager():
                page_size = max(1, int(self.page_size))
                current_page = max(1, int(self.current_page))
                qs = self.model.select()
                fields = self.model._meta.fields
                searchable = set(self._searchable)

                if self.search_text:
                    conditions = []
                    for part in self.search_text.split(","):
                        if ":" not in part:
                            continue
                        key, value = (item.strip() for item in part.split(":", 1))
                        key = self.lbl2fld.get(key, key)
                        if key not in searchable or key not in fields:
                            continue
                        field = fields[key]
                        if isinstance(field, BooleanField):
                            if value in ("هست", "آره", "اره", "yes", "True", "true", "شده", "است", "می باشد", "میباشد"):
                                conditions.append(field == True)
                            elif value in ("نیست", "نه", "no", "False", "false", "نشده", "نمی باشد", "نمیباشد"):
                                conditions.append(field == False)
                        elif isinstance(field, (CharField, TextField)):
                            conditions.append(field.contains(value))
                        else:
                            conditions.append(field == value)
                    if conditions:
                        qs = qs.where(reduce(operator.and_, conditions))

                if self.cb_enable_date and hasattr(self.model, "created_at"):
                    values = (
                        self.dt_from_date.strip(), self.dt_from_time.strip(),
                        self.dt_to_date.strip(), self.dt_to_time.strip(),
                    )
                    if all(values):
                        start_dt = parse_jalali_datetime(values[0], values[1])
                        end_dt = parse_jalali_datetime(values[2], values[3])
                        if start_dt > end_dt:
                            raise ValueError("زمان شروع نباید از زمان پایان بزرگ‌تر باشد.")
                        qs = qs.where(self.model.created_at.between(start_dt, end_dt))

                order_by = []
                for field_name, ascending in self.sort_fields or ():
                    if field_name not in fields:
                        continue
                    field = fields[field_name]
                    order_by.append(field.asc() if ascending else field.desc())
                if order_by:
                    qs = qs.order_by(*order_by)

                total_rows = qs.count()
                max_page = max(1, (total_rows - 1) // page_size + 1)
                current_page = min(current_page, max_page)
                self.page_changed.emit(current_page)
                data = list(qs.limit(page_size).offset((current_page - 1) * page_size))
            self.data_loaded.emit(data, total_rows)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class RecordAdder(QObject):
    # now carries the created model instance
    added = Signal(object)
    error = Signal(str)

    def __init__(self, model, data, image_fields, parent=None):
        super().__init__(parent)
        self.model = model
        self.data = data
        self.image_fields = image_fields

    @Slot()
    def add_record(self):
        try:
            with DBManager():
                data = dict(self.data)
                raw_password = data.get("password")
                if "password" in data and hasattr(self.model, "set_password") and not raw_password:
                    raise ValueError("رمز عبور نمی‌تواند خالی باشد.")
                if raw_password and hasattr(self.model, "set_password"):
                    # Hash credentials before the first insert; never persist plaintext.
                    data["password"] = ""
                    record = self.model(**data)
                    record.set_password(raw_password)
                    record.save(force_insert=True)
                else:
                    record = self.model.create(**data)
            self.added.emit(record)
        except Exception as exc:
            for image_field in self.image_fields:
                image_path = self.data.get(image_field)
                if is_managed_image_path(image_path) and os.path.isfile(image_path):
                    try:
                        os.remove(image_path)
                    except OSError:
                        pass
            self.error.emit(str(exc))

class RecordEditor(QObject):
    edited = Signal()
    error = Signal(str)

    def __init__(self, model, pk_val, data, image_fields, old_images, parent=None):
        super().__init__(parent)
        self.model = model
        self.pk_val = pk_val
        self.data = data
        self.image_fields = image_fields
        self.old_images = old_images

    @Slot()
    def edit_record(self):
        try:
            with DBManager():
                record = self.model.get_by_id(self.pk_val)
                fields_to_save = []
                for field, value in self.data.items():
                    if field == "password" and hasattr(record, "set_password"):
                        # An empty password means the existing password is unchanged.
                        if value:
                            record.set_password(value)
                            fields_to_save.append("password")
                        continue
                    setattr(record, field, value)
                    fields_to_save.append(field)
                if fields_to_save:
                    record.save(only=list(dict.fromkeys(fields_to_save + ["updated_at"])))
            for image_field in self.image_fields:
                old_path = self.old_images.get(image_field)
                new_path = getattr(record, image_field)
                if old_path and old_path != new_path and is_managed_image_path(old_path) and os.path.isfile(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass
            self.edited.emit()
        except Exception as exc:
            self.error.emit(str(exc))

class RecordDeleter(QObject):
    deleted = Signal()
    error = Signal(str)

    def __init__(self, model, pk_val, image_fields, parent=None):
        super().__init__(parent)
        self.model = model
        self.pk_val = pk_val
        self.image_fields = image_fields

    @Slot()
    def delete_record(self):
        try:
            with DBManager():
                record = self.model.get_by_id(self.pk_val)
                image_paths = [
                    getattr(record, field)
                    for field in self.image_fields
                    if getattr(record, field, None)
                ]
                self.model.delete().where(self.model._meta.primary_key == self.pk_val).execute()
                entity_key = entity_key_for_model(self.model)
                if entity_key:
                    cleanup_builtin_extension_values(entity_key, self.pk_val)
            # Commit database deletion before removing associated files.
            for image_path in image_paths:
                if is_managed_image_path(image_path) and os.path.isfile(image_path):
                    try:
                        os.remove(image_path)
                    except OSError:
                        pass
            self.deleted.emit()
        except Exception as exc:
            self.error.emit(str(exc))

class Exporter(QObject):
    finished = Signal()
    error = Signal(str)

    def __init__(self, data, path, display_fields, all_fields, labels, numeric_fields, parent=None):
        super().__init__(parent)
        self.data = data
        self.path = path
        self.display_fields = display_fields
        self.all_fields = all_fields
        self.labels = labels
        self.numeric_fields = numeric_fields

    @Slot()
    def export(self):
        try:
            with open(self.path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                headers = [self.labels.get(n, n) for n in self.display_fields]
                writer.writerow(headers)
                for rec in self.data:
                    row = []
                    for key in self.display_fields:
                        val = getattr(rec, key)
                        field_type = self.all_fields.get(key)
                        if isinstance(field_type, (DateField, DateTimeField)):
                            val = to_jalali(val) if val else ""
                        elif isinstance(field_type, (DecimalField, FloatField)):
                            val = f"{val:.2f}" if val is not None else ""
                        elif isinstance(field_type, ForeignKeyField):
                            val = str(val) if val else ""
                        else:
                            val = str(val) if val is not None else ""
                        row.append(val)
                    writer.writerow(row)

                sum_row = []
                for index, key in enumerate(self.display_fields):
                    if index == 0:
                        sum_row.append("مجموع")
                    elif key in self.numeric_fields:
                        total = sum(float(getattr(rec, key) or 0) for rec in self.data)
                        sum_row.append("{:.2f}".format(total))
                    else:
                        sum_row.append("")
                writer.writerow(sum_row)

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))
