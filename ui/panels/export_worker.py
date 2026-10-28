"""Background CSV export worker for table views."""
import csv

from peewee import DateField, DateTimeField, DecimalField, FloatField, ForeignKeyField
from PySide2.QtCore import QObject, Signal, Slot

from ui.panels.date_utils import to_jalali


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
