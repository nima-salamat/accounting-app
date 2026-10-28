"""Safe metadata registry for built-in extensions and user-defined entities.

Custom fields are stored as typed metadata values, avoiding destructive SQLite
ALTER TABLE operations while keeping existing model tables backwards-compatible.
"""
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

BUILTIN_ENTITIES = {
    "users": ("کاربران", User),
    "categories": ("دسته‌بندی‌ها", Category),
    "products": ("محصولات", Product),
    "receipts": ("رسیدها", Receipt),
    "receipt_products": ("آیتم‌های رسید", ReceiptProduct),
    "warehouses": ("انبار", Warehouse),
    "check_ins": ("چک‌های دریافتی", CheckIn),
    "check_outs": ("چک‌های پرداختی", CheckOut),
}
FIELD_TYPES = ("text", "integer", "decimal", "boolean", "date")
MODEL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
RESERVED_FIELD_KEYS = {"id", "created_at", "updated_at"}


def validate_key(value, *, field_name="کلید", allow_short=False):
    """Validate a storage key independently of display labels."""
    if not isinstance(value, str):
        raise ValueError("{} باید به انگلیسی و با حروف کوچک نوشته شود.".format(field_name))
    value = value.strip()
    pattern = FIELD_KEY_RE if allow_short else MODEL_KEY_RE
    if not pattern.fullmatch(value):
        raise ValueError(
            "{} باید با حرف انگلیسی شروع شود و فقط حروف کوچک، عدد یا زیرخط داشته باشد.".format(field_name)
        )
    return value


def _normalize_schema_rows(rows):
    raw_rows = list(rows or ())
    labels_in_batch = {}
    for row in raw_rows:
        key = str(row.get("model_key", "") or "").strip()
        label = str(row.get("model_label", "") or "").strip()
        if key and label and key not in BUILTIN_ENTITIES:
            previous = labels_in_batch.get(key)
            if previous and previous != label:
                raise ValueError("برای مدل {} چند عنوان متفاوت وارد شده است.".format(key))
            labels_in_batch[key] = label

    normalized = []
    seen = set()
    for row in raw_rows:
        model_key = str(row.get("model_key", "") or "").strip()
        field_key = str(row.get("field_key", "") or "").strip()
        model_label = str(row.get("model_label", "") or "").strip()
        field_label = str(row.get("field_label", "") or "").strip()
        field_type = str(row.get("field_type", "text") or "text").strip()
        if not any((model_key, field_key, model_label, field_label)):
            continue
        model_key = validate_key(model_key, field_name="کلید مدل")
        field_key = validate_key(field_key, field_name="کلید فیلد", allow_short=True)
        if field_key in RESERVED_FIELD_KEYS:
            raise ValueError("نام فیلد {} رزرو شده است.".format(field_key))
        if not field_label:
            raise ValueError("عنوان نمایشی فیلد {} خالی است.".format(field_key))
        if field_type not in FIELD_TYPES:
            raise ValueError("نوع دادهٔ فیلد {} معتبر نیست.".format(field_key))
        if model_key not in BUILTIN_ENTITIES and not model_label:
            model_label = labels_in_batch.get(model_key, "")
            if not model_label:
                existing = CustomModelDefinition.get_or_none(
                    CustomModelDefinition.model_key == model_key
                )
                if existing is not None:
                    model_label = existing.label
            if not model_label:
                raise ValueError("برای مدل سفارشی {} باید عنوان فارسی وارد کنید.".format(model_key))
        marker = (model_key, field_key)
        if marker in seen:
            raise ValueError("فیلد {} در مدل {} تکراری است.".format(field_key, model_key))
        seen.add(marker)
        normalized.append({
            "model_key": model_key,
            "model_label": model_label,
            "field_key": field_key,
            "field_label": field_label,
            "field_type": field_type,
            "is_required": bool(row.get("is_required", False)),
        })
    return normalized
def register_schema_rows(rows, *, allow_existing=False):
    """Register a batch of field definitions atomically."""
    with DBManager():
        normalized = _normalize_schema_rows(rows)
        custom_labels = {}
        for row in normalized:
            key = row["model_key"]
            if key not in BUILTIN_ENTITIES:
                previous = custom_labels.get(key)
                if previous and previous != row["model_label"]:
                    raise ValueError("برای مدل {} چند عنوان متفاوت وارد شده است.".format(key))
                custom_labels[key] = row["model_label"]

        for model_key, label in custom_labels.items():
            model = CustomModelDefinition.get_or_none(
                CustomModelDefinition.model_key == model_key
            )
            if model is None:
                CustomModelDefinition.create(model_key=model_key, label=label)
            elif model.label != label:
                model.label = label
                model.save(only=[CustomModelDefinition.label, CustomModelDefinition.updated_at])

        created = 0
        for row in normalized:
            existing = CustomFieldDefinition.get_or_none(
                (CustomFieldDefinition.entity_type == row["model_key"])
                & (CustomFieldDefinition.field_key == row["field_key"])
            )
            if existing is not None:
                same = (
                    existing.label == row["field_label"]
                    and existing.field_type == row["field_type"]
                    and existing.is_required == row["is_required"]
                )
                if allow_existing and same:
                    continue
                raise ValueError(
                    "فیلد {} از قبل در مدل {} تعریف شده است.".format(
                        row["field_key"], row["model_key"]
                    )
                )
            CustomFieldDefinition.create(
                entity_type=row["model_key"],
                field_key=row["field_key"],
                label=row["field_label"],
                field_type=row["field_type"],
                is_required=row["is_required"],
            )
            created += 1
        return created
def register_field(entity_type, field_key, label, field_type="text",
                   is_required=False, model_label=None):
    """Add a single field to a built-in model or a custom entity."""
    row = {
        "model_key": entity_type,
        "model_label": model_label or "",
        "field_key": field_key,
        "field_label": label,
        "field_type": field_type,
        "is_required": is_required,
    }
    return register_schema_rows([row])


def list_entities():
    """Return built-in and configured custom entities for UI selectors."""
    items = [
        {"key": key, "label": label, "is_custom": False}
        for key, (label, _model) in BUILTIN_ENTITIES.items()
    ]
    with DBManager():
        items.extend(
            {"key": model.model_key, "label": model.label, "is_custom": True}
            for model in CustomModelDefinition.select().order_by(CustomModelDefinition.label)
        )
    return items


def get_entity_fields(entity_type):
    """Return field definitions ordered by their stable field key."""
    if entity_type not in BUILTIN_ENTITIES:
        with DBManager():
            if CustomModelDefinition.get_or_none(
                CustomModelDefinition.model_key == entity_type
            ) is None:
                raise ValueError("مدل انتخاب‌شده وجود ندارد.")
    with DBManager():
        return list(
            CustomFieldDefinition.select()
            .where(CustomFieldDefinition.entity_type == entity_type)
            .order_by(CustomFieldDefinition.id)
        )


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
