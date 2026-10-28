"""Schema keys and field-definition validation, separate from value persistence."""
import re

from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import CustomFieldDefinition, CustomModelDefinition
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
