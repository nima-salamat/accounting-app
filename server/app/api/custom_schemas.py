"""Admin API for custom field definitions, values, and custom records."""
from typing import List
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import CustomFieldValue, CustomModelDefinition
from accounting_app.services.schema_definitions import BUILTIN_ENTITIES, get_entity_fields
from accounting_app.services.schema_registry import register_schema_rows
from accounting_app.services.schema_values import (
    delete_custom_record, get_entity_values, list_entity_records, save_entity_values,
)
from server.app.dependencies import get_current_user, require_admin
from server.app.permissions import has_permission, require_permission

router = APIRouter(prefix="/schemas", tags=["custom schemas"])


class SchemaRowsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[dict] = Field(max_length=300)


class ValuesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


def _field_payload(field):
    return {
        "key": field.field_key,
        "label": field.label,
        "type": field.field_type,
        "required": bool(field.is_required),
    }


@router.get("/entities")
def list_entities(user=Depends(require_permission("schemas", "read"))):
    entities = [
        {"key": key, "label": label, "builtin": True}
        for key, (label, _model) in BUILTIN_ENTITIES.items()
    ]
    with DBManager():
        entities.extend(
            {"key": item.model_key, "label": item.label, "builtin": False}
            for item in CustomModelDefinition.select().order_by(CustomModelDefinition.model_key)
        )
    return entities


@router.post("/fields")
def upsert_schema_fields(payload: SchemaRowsInput, user=Depends(require_permission("schemas", "update"))):
    try:
        with DBManager():
            created = register_schema_rows(payload.rows)
        return {"created": created}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/table/{entity_type}")
def custom_table_data(
    entity_type: str,
    record_ids: List[str] = Query(default=[]),
    user=Depends(get_current_user),
):
    """Batch-fetch custom fields for visible base-table rows without N+1 queries."""
    base_resources = {
        "categories": "categories",
        "products": "products",
        "warehouses": "warehouse",
        "check_ins": "checks_in",
        "check_outs": "checks_out",
        "receipts": "receipts",
        "receipt_products": "receipts",
    }
    if entity_type == "users":
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="فقط مدیر می‌تواند اطلاعات تکمیلی کاربران را مشاهده کند.")
    elif entity_type not in BUILTIN_ENTITIES:
        with DBManager():
            known = CustomModelDefinition.get_or_none(
                CustomModelDefinition.model_key == entity_type
            ) is not None
        if not known:
            raise HTTPException(status_code=404, detail="مدل انتخاب‌شده وجود ندارد.")
        if not has_permission(user, "schemas", "read"):
            raise HTTPException(status_code=403, detail="مجوز مشاهدهٔ مدل‌های سفارشی را ندارید.")
    else:
        resource = base_resources.get(entity_type)
        if resource and not has_permission(user, resource, "read"):
            raise HTTPException(status_code=403, detail="مجوز مشاهدهٔ این بخش را ندارید.")

    unique_ids = list(dict.fromkeys(record_ids))
    if len(unique_ids) > 200 or any(not item or len(item) > 64 for item in unique_ids):
        raise HTTPException(status_code=422, detail="حداکثر ۲۰۰ شناسهٔ رکورد معتبر مجاز است.")
    if not has_permission(user, "schemas", "read"):
        return {"fields": [], "values": {}}

    try:
        definitions = get_entity_fields(entity_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    fields = [_field_payload(field) for field in definitions]
    values = {record_id: {} for record_id in unique_ids}
    if unique_ids and fields:
        allowed_keys = {field["key"] for field in fields}
        with DBManager():
            rows = CustomFieldValue.select().where(
                (CustomFieldValue.entity_type == entity_type)
                & (CustomFieldValue.record_id.in_(unique_ids))
                & (CustomFieldValue.field_key.in_(allowed_keys))
            )
            for row in rows:
                try:
                    value = json.loads(row.value) if row.value is not None else None
                except (TypeError, ValueError):
                    value = row.value
                values.setdefault(row.record_id, {})[row.field_key] = value
    return {"fields": fields, "values": values}


@router.get("/fields/{entity_type}")
def schema_fields(entity_type: str, user=Depends(require_permission("schemas", "read"))):
    try:
        return [_field_payload(field) for field in get_entity_fields(entity_type)]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/records/{entity_type}")
def entity_records(
    entity_type: str,
    limit: int = Query(200, ge=1, le=500),
    user=Depends(require_permission("schemas", "read")),
):
    try:
        return [{"id": record_id, "label": label} for record_id, label in list_entity_records(entity_type, limit)]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/records/{entity_type}", status_code=201)
def create_custom_record(entity_type: str, payload: ValuesInput, user=Depends(require_permission("schemas", "create"))):
    if entity_type in BUILTIN_ENTITIES:
        raise HTTPException(status_code=405, detail="رکورد مدل اصلی باید از مسیر CRUD همان مدل ساخته شود.")
    try:
        record_id = save_entity_values(entity_type, None, payload.values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": record_id, "values": get_entity_values(entity_type, record_id)}


@router.get("/values/{entity_type}/{record_id}")
def entity_values(entity_type: str, record_id: str, user=Depends(require_permission("schemas", "read"))):
    try:
        return get_entity_values(entity_type, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/values/{entity_type}/{record_id}")
def update_entity_values(
    entity_type: str, record_id: str, payload: ValuesInput, user=Depends(require_permission("schemas", "update"))
):
    try:
        save_entity_values(entity_type, record_id, payload.values)
        return get_entity_values(entity_type, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/records/{entity_type}/{record_id}", status_code=204)
def remove_custom_record(entity_type: str, record_id: str, user=Depends(require_permission("schemas", "delete"))):
    try:
        deleted = delete_custom_record(entity_type, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="رکورد پیدا نشد.")
