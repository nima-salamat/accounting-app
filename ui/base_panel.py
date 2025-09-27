import os
import shutil
import uuid
from functools import reduce
import operator
from decimal import Decimal
from urllib.parse import urlparse, unquote
import csv

import requests
from peewee import *
from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QPushButton, QLineEdit, QHBoxLayout,
    QTableWidgetItem, QMessageBox, QDialog, QLabel, QCheckBox, QFileDialog,
    QComboBox, QMenu, QApplication, QScrollArea, QGraphicsScene, QGraphicsView,
    QGraphicsPixmapItem, QToolButton, QStyle, QGroupBox, QFrame, QAction
)
from PySide2.QtCore import Qt, QDate, QDateTime, QUrl, QMimeData, QEasingCurve, QPropertyAnimation, Property, Signal, Slot, QObject
from PySide2.QtGui import (
     QDesktopServices, QDoubleValidator,
    QKeySequence, QImage, QPixmap, QDragEnterEvent, QDropEvent
)
from functools import partial
import jdatetime
JalaliDatetime = jdatetime.datetime
JalaliDate = jdatetime.date
from datetime import datetime, date, timedelta
from ui.thread import TrackingQThread
QThread = TrackingQThread
# Helper function to normalize paths
def _normalize_path(path_or_url: str) -> str:
    if path_or_url.startswith("file:///"):
        p = urlparse(path_or_url)
        local = unquote(p.path)
        if os.name == "nt" and local.startswith('/'):
            local = local[1:]
        return local
    return path_or_url

# Date conversion functions
def to_jalali(dt):
    if isinstance(dt, datetime):
        return JalaliDatetime.fromgregorian(datetime=dt).strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(dt, date):
        return JalaliDate.fromgregorian(date=dt).strftime('%Y-%m-%d')
    return dt

def jalali_tomorrow_date():
    j_today = jdatetime.date.today()

    g_today = j_today.togregorian()

    g_tomorrow = g_today + timedelta(days=1)

    j_tomorrow = jdatetime.date.fromgregorian(date=g_tomorrow)
    
    return j_tomorrow
def from_jalali(jalali_str, is_datetime=False):
    try:
        if is_datetime:
            if len(jalali_str.strip()) == 16:  # مثل "1403-04-13 01:05"
                jalali_str += ":00"
            jalali_dt = JalaliDatetime.strptime(jalali_str, '%Y-%m-%d %H:%M:%S')
            return jalali_dt.togregorian()
        else:
            jalali_date = JalaliDate.strptime(jalali_str, '%Y-%m-%d')
            return jalali_date.togregorian()
    except ValueError:
        raise ValueError(f"فرمت تاریخ شمسی نامعتبر است: {jalali_str}")

def parse_jalali_datetime(date_str, time_str):
    if not date_str or not time_str:
        return None
    try:
        year, month, day = map(int, date_str.split('/'))
        parts = list(map(int, time_str.split(':')))
        hour = parts[0]
        minute = parts[1] if len(parts) > 1 else 0
        second = parts[2] if len(parts) > 2 else 0
        jalali_date = JalaliDate(year, month, day)
        g_date = jalali_date.togregorian()
        return datetime(g_date.year, g_date.month, g_date.day, hour, minute, second)
    except Exception as e:
        raise ValueError(f"خطا در تبدیل تاریخ و زمان: {e}")


# Worker classes for threading
class DataLoader(QObject):
    data_loaded = Signal(list, int)  # Emits data and total_rows
    error = Signal(str)

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
            qs = self.model.select()
            if self.search_text:
                conds = []
                for part in self.search_text.split(","):
                    if ":" in part:
                        k, v = part.split(":", 1)
                        k, v = k.strip(), v.strip()
                        if k in self.lbl2fld:
                            k = self.lbl2fld[k]
                        if k in self._searchable:
                            fld = self.model._meta.fields[k]
                            if isinstance(fld, BooleanField):
                                if v in ["هست", "آره", "اره", "yes", "True", "true", "شده", "است", "می باشد", "میباشد"]:
                                    conds.append(fld == True)
                                elif v in ["نیست", "نه", "no", "False", "false", "نشده", "نمی باشد", "نمیباشد"]:
                                    conds.append(fld == False)
                            else:
                                conds.append(fld.contains(v) if isinstance(fld, (CharField, TextField)) else fld == v)
                if conds:
                    qs = qs.where(reduce(operator.and_, conds))
            if self.cb_enable_date and hasattr(self.model, 'created_at'):
                start_date = self.dt_from_date.strip()
                start_time = self.dt_from_time.strip()
                end_date = self.dt_to_date.strip()
                end_time = self.dt_to_time.strip()
                if start_date and start_time and end_date and end_time:
                    try:
                        start_dt = parse_jalali_datetime(start_date, start_time)
                        end_dt = parse_jalali_datetime(end_date, end_time)
                        qs = qs.where(self.model.created_at.between(start_dt, end_dt))
                    except ValueError as e:
                        self.error.emit(str(e))
                        return
            if self.sort_fields:
                order_by = []
                for field, asc in self.sort_fields:
                    fld = getattr(self.model, field)
                    order_by.append(fld.asc() if asc else fld.desc())
                qs = qs.order_by(*order_by)
            total_rows = qs.count()
            offset = (self.current_page - 1) * self.page_size
            data = list(qs.limit(self.page_size).offset(offset))
            self.data_loaded.emit(data, total_rows)
        except Exception as e:
            self.error.emit(str(e))

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
            # create and save the record
            rec = self.model.create(**self.data)

            # handle password if present
            if 'password' in self.data and self.data['password']:
                if hasattr(rec, "set_password"):
                    rec.set_password(self.data['password'])
                    rec.save()

            # emit the new instance back to the UI thread
            self.added.emit(rec)

        except Exception as e:
            # on failure, clean up any temp images
            for img_field in self.image_fields:
                img_path = self.data.get(img_field)
                if img_path and os.path.isfile(img_path):
                    try:
                        os.remove(img_path)
                    except Exception:
                        pass
            self.error.emit(str(e))

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
            rec = self.model.get_by_id(self.pk_val)
            for field, value in self.data.items():
                setattr(rec, field, value)

            fields_to_save = list(self.data.keys())
            if 'password' in self.data and self.data['password']:
                if hasattr(rec, "set_password"):
                    rec.set_password(self.data['password'])
                    fields_to_save.append("password")

            rec.save(only=fields_to_save)

          
            for img_field in getattr(self, 'image_fields', []):
                old_path = self.old_images.get(img_field)
                new_path = getattr(rec, img_field)
                if old_path and old_path != new_path and os.path.isfile(old_path):
                    os.remove(old_path)

            self.edited.emit()

        except Exception as e:
            self.error.emit(str(e))

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
            rec = self.model.get_by_id(self.pk_val)
            for img in self.image_fields:
                f = getattr(rec, img)
                if f and os.path.isfile(f):
                    try:
                        os.remove(f)
                    except:
                        pass
            self.model.delete().where(self.model._meta.primary_key == self.pk_val).execute()
            self.deleted.emit()
        except Exception as e:
            self.error.emit(str(e))

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

                sum_row = ["مجموع"]
                for key in self.display_fields[1:]:
                    if key in self.numeric_fields:
                        total = sum(float(getattr(rec, key) or 0) for rec in self.data)
                        sum_row.append(f"{total:.2f}")
                    else:
                        sum_row.append("")
                writer.writerow(sum_row)

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

# Image input management class
class ImageLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.image_data = None

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Paste):
            cb = QApplication.clipboard()
            md = cb.mimeData()
            if md.hasImage():
                self._set_image(md.imageData())
                return
            elif md.hasText():
                self._handle_text(md.text())
                return
        super().keyPressEvent(e)

    def insertFromMimeData(self, source: QMimeData):
        if source.hasImage():
            self._set_image(source.imageData())
        elif source.hasUrls():
            u = source.urls()[0]
            local = u.toLocalFile() or u.toString()
            self._handle_url(local)
        elif source.hasText():
            self._handle_text(source.text())
        else:
            super().insertFromMimeData(source)

    def dragEnterEvent(self, e: QDragEnterEvent):
        md = e.mimeData()
        if md.hasImage() or md.hasUrls() or md.hasText():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dropEvent(self, e: QDropEvent):
        md = e.mimeData()
        if md.hasImage():
            self._set_image(md.imageData())
            e.acceptProposedAction()
        elif md.hasUrls():
            u = md.urls()[0]
            local = u.toLocalFile() or u.toString()
            self._handle_url(local)
            e.acceptProposedAction()
        elif md.hasText():
            self._handle_text(md.text())
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    def _handle_url(self, url):
        if url.startswith("file:///"):
            path = _normalize_path(url)
            img = QImage(path)
            if not img.isNull():
                self._set_image(img)
            else:
                self.setText(url)
        elif url.startswith("http://") or url.startswith("https://"):
            try:
                response = requests.get(url)
                response.raise_for_status()
                img = QImage()
                img.loadFromData(response.content)
                if not img.isNull():
                    self._set_image(img)
                else:
                    self.setText(url)
            except Exception as e:
                QMessageBox.warning(self, "خطا", f"خطا در بارگذاری تصویر از URL: {e}")
                self.setText(url)
        else:
            self.setText(url)

    def _handle_text(self, text):
        if text.startswith("file:///") or text.startswith("http://") or text.startswith("https://"):
            self._handle_url(text)
        else:
            self.setText(text)

    def _set_image(self, img: QImage):
        self.image_data = img
        self.setText("[تصویر]")
        if isinstance(self.parent(), QWidget):
            parent = self.parent()
            while parent and not isinstance(parent, RecordDialog):
                parent = parent.parent()
            if parent:
                parent.set_thumbnail(self, img)

# Image preview dialog class
class PreviewDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("پیش‌نمایش تصویر")
        self.setModal(True)
        self._zoom = 1.0

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "خطا در نمایش", f"نمی‌توان تصویر را بارگذاری کرد:\n{image_path}")
            self.reject()
            return

        self.scene = QGraphicsScene(self)
        self.item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.item)

        self.view = QGraphicsView(self.scene)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)

        btn_zoom_in = QToolButton()
        btn_zoom_in.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
        btn_zoom_in.clicked.connect(self.zoom_in)

        btn_zoom_out = QToolButton()
        btn_zoom_out.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        btn_zoom_out.clicked.connect(self.zoom_out)

        btn_close = QPushButton("بستن")
        btn_close.clicked.connect(self.close)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_zoom_in)
        btn_layout.addWidget(btn_zoom_out)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.view)
        main_layout.addLayout(btn_layout)
        self.resize(800, 600)

    def zoom_in(self):
        self._zoom *= 1.25
        self._apply_zoom()

    def zoom_out(self):
        self._zoom /= 1.25
        self._apply_zoom()

    def _apply_zoom(self):
        self.view.resetTransform()
        self.view.scale(self._zoom, self._zoom)

# Data entry dialog class
class RecordDialog(QDialog):
    def __init__(self, fields, model, image_fields=None, labels=None, initial=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("رکورد")
        self.fields = fields
        self.image_fields = image_fields or []
        self.labels = labels or {}
        self.initial = initial or {}
        self.data = {}
        self.image_data = {}

        layout = QVBoxLayout(self)
        self.widgets = {}
        for name, field in fields.items():
            lbl = QLabel(self.labels.get(name, name))
            widget = self._make_widget(name, field)
            self.widgets[name] = widget
            row = QHBoxLayout()
            row.addWidget(lbl)
            row.addWidget(widget)
            layout.addLayout(row)

        btn_ok = QPushButton("تأیید")
        btn_ok.clicked.connect(self.accept_data)
        layout.addWidget(btn_ok)

    def _make_widget(self, name, field):
        val = self.initial.get(name)
        if hasattr(field, "choices") and field.choices:
            w = QComboBox()
            for choice in field.choices:
                if isinstance(choice, (list, tuple)) and len(choice) == 2:
                    w.addItem(str(choice[1]), choice[0])
                else:
                    w.addItem(str(choice), choice)
            if val is not None:
                idx = w.findData(val)
                if idx >= 0:
                    w.setCurrentIndex(idx)
            return w

        if isinstance(field, ForeignKeyField):
            w = QComboBox()
            w.addItem("—", None)
            for obj in field.rel_model.select():
                w.addItem(str(obj), obj)
            if val is not None:
                for i in range(w.count()):
                    data = w.itemData(i)
                    if data and ((isinstance(val, Model) and data.get_id() == val.get_id()) or data == val):
                        w.setCurrentIndex(i)
                        break
            return w

        if isinstance(field, BooleanField):
            w = QCheckBox()
            w.setChecked(bool(val))
            return w

        if isinstance(field, DateField):
            w = QLineEdit()
            w.setPlaceholderText("YYYY-MM-DD (شمسی)")
            if val:
                w.setText(to_jalali(val))
            return w

        if isinstance(field, DateTimeField):
            w = QLineEdit()
            w.setPlaceholderText("YYYY-MM-DD HH:MM:SS (شمسی)")
            if val:
                w.setText(to_jalali(val))
            return w

        if isinstance(field, (DecimalField, FloatField)):
            w = QLineEdit()
            w.setValidator(QDoubleValidator())
            if val is not None:
                w.setText(str(val))
            return w

        if name in self.image_fields:
            w = ImageLineEdit()
            w.setReadOnly(True)
            if val:
                w.setText(str(val))
            btn = QPushButton("جستجو…")
            btn.setMaximumWidth(30)
            btn.clicked.connect(lambda: self._select_image(w))
            thumbnail = QLabel()
            thumbnail.setFixedSize(100, 100)
            thumbnail.setAlignment(Qt.AlignCenter)
            container = QWidget()
            row = QHBoxLayout(container)
            row.addWidget(w)
            row.addWidget(btn)
            row.addWidget(thumbnail)
            self.image_data[name] = None
            if val:
                img = QImage(str(val))
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img).scaled(100, 100, Qt.KeepAspectRatio)
                    thumbnail.setPixmap(pixmap)
            return container

        w = QLineEdit()
        if val:
            w.setText(str(val))
        return w

    def _select_image(self, le):
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب تصویر")
        if path:
            le.setText(path)
            img = QImage(path)
            if not img.isNull():
                le.image_data = img
                self.set_thumbnail(le, img)

    def set_thumbnail(self, le, img):
        container = le.parent()
        if container is not None:
            thumbnail = container.layout().itemAt(2).widget()
            pixmap = QPixmap.fromImage(img).scaled(100, 100, Qt.KeepAspectRatio)
            thumbnail.setPixmap(pixmap)

    def accept_data(self):
        for name, field in self.fields.items():
            w = self.widgets[name]
            try:
                if hasattr(field, "choices") and field.choices:
                    self.data[name] = w.currentData()
                    continue
                if isinstance(field, ForeignKeyField):
                    self.data[name] = w.currentData()
                elif isinstance(field, BooleanField):
                    self.data[name] = w.isChecked()
                elif isinstance(field, DateField):
                    jalali_str = w.text().strip()
                    self.data[name] = from_jalali(jalali_str) if jalali_str else None
                elif isinstance(field, DateTimeField):
                    jalali_str = w.text().strip()
                    self.data[name] = from_jalali(jalali_str, is_datetime=True) if jalali_str else None
                elif isinstance(field, (DecimalField, FloatField)):
                    txt = w.text().strip()
                    self.data[name] = Decimal(txt) if isinstance(field, DecimalField) else float(txt) if txt else None
                elif name in self.image_fields:
                    container = w
                    le = container.layout().itemAt(0).widget()
                    if le.image_data:
                        fname = f"{uuid.uuid4()}.png"
                        dst = os.path.join("images", fname)
                        os.makedirs("images", exist_ok=True)
                        if le.image_data.save(dst, "PNG"):
                            self.data[name] = dst
                        else:
                            QMessageBox.warning(self, "خطا در ذخیره", f"نمی‌توان تصویر را در:\n{dst} ذخیره کرد")
                            self.data[name] = None
                    else:
                        path = le.text().strip()
                        if path:
                            if path.startswith("file:///"):
                                path = _normalize_path()
                            if os.path.isfile(path):
                                ext = os.path.splitext(path)[1]
                                dst = os.path.join("images", f"{uuid.uuid4()}{ext}")
                                os.makedirs("images", exist_ok=True)
                                shutil.copy(path, dst)
                                self.data[name] = dst
                            elif path.startswith("http://") or path.startswith("https://"):
                                try:
                                    response = requests.get(path)
                                    response.raise_for_status()
                                    img = QImage()
                                    img.loadFromData(response.content)
                                    if not img.isNull():
                                        fname = f"{uuid.uuid4()}.png"
                                        dst = os.path.join("images", fname)
                                        os.makedirs("images", exist_ok=True)
                                        img.save(dst, "PNG")
                                        self.data[name] = dst
                                    else:
                                        self.data[name] = None
                                except Exception as e:
                                    QMessageBox.warning(self, "خطا", f"خطا در دانلود تصویر: {e}")
                                    self.data[name] = None
                            else:
                                self.data[name] = path
                        else:
                            self.data[name] = None
                else:
                    self.data[name] = w.text().strip()
            except Exception as e:
                QMessageBox.critical(self, "ورودی نامعتبر", f"خطا در '{name}': {e}")
                return
        self.accept()

# Main table management class
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

