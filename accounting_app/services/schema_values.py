"""Typed storage and CRUD helpers for custom field values."""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from peewee import DoesNotExist

from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import (
    CustomFieldDefinition, CustomFieldValue, CustomModelDefinition, CustomRecord,
)
from accounting_app.database.models import (
    Category, CheckIn, CheckOut, Product, Receipt, ReceiptProduct, User, Warehouse,
)
from accounting_app.services.schema_definitions import BUILTIN_ENTITIES, get_entity_fields


def _missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def normalize_field_value(definition, value):
    """Validate and normalize one field value to a JSON-compatible type."""
    if _missing(value):
        if definition.is_required:
            raise ValueError("وارد کردن «{}» الزامی است.".format(definition.label))
        return None
    try:
        if definition.field_type in ("text",):
            return str(value)
        if definition.field_type == "integer":
            if isinstance(value, bool):
                raise ValueError()
            text = str(value).strip()
            if not re.fullmatch(r"[+-]?\d+", text):
                raise ValueError()
            return int(text)
        if definition.field_type == "decimal":
            amount = Decimal(str(value).strip())
            if not amount.is_finite():
                raise ValueError()
            return format(amount, "f")
        if definition.field_type == "boolean":
            if isinstance(value, bool):
                return value
            if value in (1, "1", "true", "True", "بله", "yes", "Yes"):
                return True
            if value in (0, "0", "false", "False", "خیر", "no", "No"):
                return False
            raise ValueError()
        if definition.field_type == "date":
            return date.fromisoformat(str(value).strip()).isoformat()
    except (ValueError, TypeError, InvalidOperation, OverflowError) as exc:
        raise ValueError("مقدار «{}» با نوع دادهٔ آن سازگار نیست.".format(definition.label)) from exc
    raise ValueError("نوع دادهٔ فیلد {} پشتیبانی نمی‌شود.".format(definition.label))


def _known_entity(entity_type):
    if entity_type in BUILTIN_ENTITIES:
        return False
    with DBManager():
        if CustomModelDefinition.get_or_none(
            CustomModelDefinition.model_key == entity_type
        ) is None:
            raise ValueError("مدل انتخاب‌شده وجود ندارد.")
    return True


def list_entity_records(entity_type, limit=500):
    """Return record identifiers and readable labels for the extension editor."""
    custom = _known_entity(entity_type)
    with DBManager():
        if custom:
            records = list(
                CustomRecord.select()
                .where(CustomRecord.entity_type == entity_type)
                .order_by(CustomRecord.created_at.desc())
                .limit(limit)
            )
            output = []
            for record in records:
                data = json.loads(record.data or "{}")
                preview = next((str(value) for value in data.values() if value not in (None, "")), "")
                output.append((str(record.id), preview or str(record.id)))
            return output

        _label, model = BUILTIN_ENTITIES[entity_type]
        records = list(model.select().order_by(model.created_at.desc()).limit(limit))
        output = []
        for record in records:
            display = None
            for attribute in ("name", "username", "check_id"):
                if hasattr(record, attribute):
                    display = getattr(record, attribute)
                    if display:
                        break
            if not display and hasattr(record, "day_receipt_id"):
                display = "رسید روزانه {}".format(record.day_receipt_id)
            output.append((str(record.id), "{} — {}".format(display or entity_type, record.id)))
        return output


def get_entity_values(entity_type, record_id):
    """Read stored custom values for either a built-in row or custom record."""
    custom = _known_entity(entity_type)
    with DBManager():
        if custom:
            record = CustomRecord.get_or_none(
                (CustomRecord.entity_type == entity_type) & (CustomRecord.id == record_id)
            )
            return json.loads(record.data or "{}") if record is not None else {}
        values = {}
        query = CustomFieldValue.select().where(
            (CustomFieldValue.entity_type == entity_type)
            & (CustomFieldValue.record_id == str(record_id))
        )
        for item in query:
            try:
                values[item.field_key] = json.loads(item.value) if item.value is not None else None
            except (TypeError, ValueError):
                values[item.field_key] = item.value
        return values


def save_entity_values(entity_type, record_id, values):
    """Persist validated extension values; create a custom record when record_id is None."""
    custom = _known_entity(entity_type)
    fields = get_entity_fields(entity_type)
    definitions = {field.field_key: field for field in fields}
    unknown = set(values) - set(definitions)
    if unknown:
        raise ValueError("فیلد تعریف‌نشده‌ای ارسال شده است: {}".format(", ".join(sorted(unknown))))

    with DBManager():
        previous = get_entity_values(entity_type, record_id) if record_id else {}
        normalized = {}
        for key, definition in definitions.items():
            raw = values.get(key, previous.get(key))
            normalized[key] = normalize_field_value(definition, raw)
        if custom:
            if record_id:
                record = CustomRecord.get_or_none(
                    (CustomRecord.entity_type == entity_type)
                    & (CustomRecord.id == record_id)
                )
                if record is None:
                    raise ValueError("رکورد سفارشی موردنظر پیدا نشد.")
                record.data = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
                record.save(only=[CustomRecord.data, CustomRecord.updated_at])
            else:
                record = CustomRecord.create(
                    entity_type=entity_type,
                    data=json.dumps(normalized, ensure_ascii=False, sort_keys=True),
                )
            return str(record.id)

        _label, model = BUILTIN_ENTITIES[entity_type]
        try:
            model.get(model.id == record_id)
        except DoesNotExist as exc:
            raise ValueError("ابتدا یک رکورد موجود را انتخاب کنید.") from exc
        for key, value in normalized.items():
            encoded = json.dumps(value, ensure_ascii=False)
            stored = CustomFieldValue.get_or_none(
                (CustomFieldValue.entity_type == entity_type)
                & (CustomFieldValue.record_id == str(record_id))
                & (CustomFieldValue.field_key == key)
            )
            if stored is None:
                CustomFieldValue.create(
                    entity_type=entity_type, record_id=str(record_id),
                    field_key=key, value=encoded,
                )
            else:
                stored.value = encoded
                stored.save(only=[CustomFieldValue.value, CustomFieldValue.updated_at])
        return str(record_id)


def delete_custom_record(entity_type, record_id):
    """Delete only a generic custom record, never a built-in accounting record."""
    if not _known_entity(entity_type):
        raise ValueError("حذف رکوردهای مدل‌های اصلی از این بخش مجاز نیست.")
    with DBManager():
        return CustomRecord.delete().where(
            (CustomRecord.entity_type == entity_type)
            & (CustomRecord.id == record_id)
        ).execute()


def entity_key_for_model(model):
    """Resolve a built-in Peewee model class to its stable extension key."""
    for entity_key, (_label, model_class) in BUILTIN_ENTITIES.items():
        if model_class is model:
            return entity_key
    return None


def cleanup_builtin_extension_values(entity_type, record_id):
    """Remove extension values when their owning built-in record is deleted."""
    return cleanup_builtin_extension_values_many(entity_type, [record_id])


def cleanup_builtin_extension_values_many(entity_type, record_ids):
    """Delete extension metadata in one query for a batch of built-in records."""
    if entity_type not in BUILTIN_ENTITIES:
        raise ValueError("مدل اصلی معتبر نیست.")
    normalized_ids = [str(record_id) for record_id in record_ids if record_id is not None]
    if not normalized_ids:
        return 0
    with DBManager():
        return CustomFieldValue.delete().where(
            (CustomFieldValue.entity_type == entity_type)
            & (CustomFieldValue.record_id.in_(normalized_ids))
        ).execute()
