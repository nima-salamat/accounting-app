"""Threaded read-side data loading for searchable, sortable tables."""
import operator
from functools import reduce

from peewee import BooleanField, CharField, TextField
from PySide6.QtCore import QObject, Signal, Slot

from manager.db import DBManager
from ui.panels.date_utils import parse_jalali_datetime


class DataLoader(QObject):
    data_loaded = Signal(list, int)  # Backwards-compatible result signal
    error = Signal(str)  # Backwards-compatible error signal
    result_ready = Signal(list, int, int, int)
    failure = Signal(str, int)
    finished = Signal()
    page_changed = Signal(int)

    def __init__(self, model, search_text, sort_fields, page_size, current_page, cb_enable_date, dt_from_date, dt_from_time, dt_to_date, dt_to_time, lbl2fld, searchable, parent=None, request_id=0):
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
        self.request_id = request_id

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
            self.result_ready.emit(data, total_rows, current_page, self.request_id)
            self.data_loaded.emit(data, total_rows)
        except Exception as exc:
            self.failure.emit(str(exc), self.request_id)
            self.error.emit(str(exc))
        finally:
            self.finished.emit()
