"""Admin API for custom field definitions, values, and custom records."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import CustomModelDefinition
from accounting_app.services.schema_definitions import BUILTIN_ENTITIES, get_entity_fields
from accounting_app.services.schema_registry import register_schema_rows
from accounting_app.services.schema_values import (
    delete_custom_record, get_entity_values, list_entity_records, save_entity_values,
)
from server.app.dependencies import get_current_user, require_admin

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
def list_entities(_user=Depends(get_current_user)):
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
def upsert_schema_fields(payload: SchemaRowsInput, _admin=Depends(require_admin)):
    try:
        with DBManager():
            created = register_schema_rows(payload.rows)
        return {"created": created}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/fields/{entity_type}")
def schema_fields(entity_type: str, _admin=Depends(require_admin)):
    try:
        return [_field_payload(field) for field in get_entity_fields(entity_type)]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/records/{entity_type}")
def entity_records(
    entity_type: str,
    limit: int = Query(200, ge=1, le=500),
    _admin=Depends(require_admin),
):
    try:
        return [{"id": record_id, "label": label} for record_id, label in list_entity_records(entity_type, limit)]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/records/{entity_type}", status_code=201)
def create_custom_record(entity_type: str, payload: ValuesInput, _admin=Depends(require_admin)):
    if entity_type in BUILTIN_ENTITIES:
        raise HTTPException(status_code=405, detail="رکورد مدل اصلی باید از مسیر CRUD همان مدل ساخته شود.")
    try:
        record_id = save_entity_values(entity_type, None, payload.values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": record_id, "values": get_entity_values(entity_type, record_id)}


@router.get("/values/{entity_type}/{record_id}")
def entity_values(entity_type: str, record_id: str, _admin=Depends(require_admin)):
    try:
        return get_entity_values(entity_type, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/values/{entity_type}/{record_id}")
def update_entity_values(
    entity_type: str, record_id: str, payload: ValuesInput, _admin=Depends(require_admin)
):
    try:
        save_entity_values(entity_type, record_id, payload.values)
        return get_entity_values(entity_type, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/records/{entity_type}/{record_id}", status_code=204)
def remove_custom_record(entity_type: str, record_id: str, _admin=Depends(require_admin)):
    try:
        deleted = delete_custom_record(entity_type, record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="رکورد پیدا نشد.")
