"""Registration and lookup of built-in extensions and user-defined schemas."""
from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import CustomFieldDefinition, CustomModelDefinition
from accounting_app.services.schema_definitions import (
    BUILTIN_ENTITIES, FIELD_TYPES, _normalize_schema_rows, get_entity_fields, validate_key,
)
from accounting_app.services.schema_values import (
    cleanup_builtin_extension_values, delete_custom_record, entity_key_for_model,
    get_entity_values, list_entity_records, normalize_field_value, save_entity_values,
)


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
