"""Background create, update and delete operations for Peewee records."""
import os

from PySide2.QtCore import QObject, Signal, Slot

from accounting_app.services.file_safety import is_managed_image_path
from accounting_app.services.schema_registry import cleanup_builtin_extension_values, entity_key_for_model
from manager.db import DBManager


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
