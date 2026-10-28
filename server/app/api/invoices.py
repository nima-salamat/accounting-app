"""Server-persisted invoice template settings, validated at the API boundary."""
import json
import re
from typing import Dict, List, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import AppSetting
from server.app.permissions import require_permission

router = APIRouter(prefix="/invoices", tags=["invoices"])

BLOCK_NAMES = ("company", "metadata", "items", "totals", "footer")
DEFAULT_TEMPLATE = {
    "company_name": "نام کسب‌وکار",
    "legal_id": "",
    "address": "",
    "phone": "",
    "seat_number_label": "شماره صندلی / میز",
    "footer": "از خرید شما سپاسگزاریم.",
    "font_family": "Vazirmatn",
    "font_size": 11,
    "header_font_size": 23,
    "line_height": 1.8,
    "text_direction": "rtl",
    "paper_size": "A4",
    "orientation": "portrait",
    "margin_mm": 12,
    "accent_color": "#3157A4",
    "show_border": True,
    "frame_border_color": "#CBD5E1",
    "layout_order": list(BLOCK_NAMES),
    "block_settings": {
        "company": {"column": "full", "align": "right"},
        "metadata": {"column": "right", "align": "right"},
        "items": {"column": "full", "align": "right"},
        "totals": {"column": "left", "align": "left"},
        "footer": {"column": "full", "align": "center"},
    },
    "table_alignment": {
        "index": "center", "name": "right", "quantity": "center",
        "unit_price": "left", "line_total": "left",
    },
}


class InvoiceBlockSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: Literal["full", "left", "right"] = "full"
    align: Literal["left", "center", "right"] = "right"


class InvoiceTemplateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str = Field(default="نام کسب‌وکار", min_length=1, max_length=160)
    legal_id: str = Field(default="", max_length=80)
    address: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=80)
    seat_number_label: str = Field(default="شماره صندلی / میز", max_length=80)
    footer: str = Field(default="از خرید شما سپاسگزاریم.", max_length=500)
    font_family: str = Field(default="Vazirmatn", min_length=1, max_length=80, pattern=r"^[\\w .()\\-]{1,80}$")
    font_size: int = Field(default=11, ge=8, le=18)
    header_font_size: int = Field(default=23, ge=14, le=32)
    line_height: float = Field(default=1.8, ge=1.2, le=2.4)
    text_direction: Literal["rtl", "ltr"] = "rtl"
    paper_size: Literal["A4", "A5", "A6", "receipt80", "receipt58"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    margin_mm: int = Field(default=12, ge=3, le=30)
    accent_color: str = Field(default="#3157A4", pattern=r"^#[0-9A-Fa-f]{6}$")
    show_border: bool = True
    frame_border_color: str = Field(default="#CBD5E1", pattern=r"^#[0-9A-Fa-f]{6}$")
    layout_order: List[Literal["company", "metadata", "items", "totals", "footer"]] = Field(
        default_factory=lambda: list(BLOCK_NAMES), min_length=1, max_length=5
    )
    block_settings: Dict[
        Literal["company", "metadata", "items", "totals", "footer"], InvoiceBlockSetting
    ] = Field(default_factory=lambda: DEFAULT_TEMPLATE["block_settings"])
    table_alignment: Dict[
        Literal["index", "name", "quantity", "unit_price", "line_total"],
        Literal["left", "center", "right"],
    ] = Field(default_factory=lambda: DEFAULT_TEMPLATE["table_alignment"])

    @model_validator(mode="after")
    def unique_layout_blocks(self):
        if len(self.layout_order) != len(set(self.layout_order)):
            raise ValueError("هر بخش فاکتور فقط یک بار در ترتیب چیدمان قرار می‌گیرد.")
        return self


@router.get("/template")
def get_invoice_template(_user=Depends(require_permission("invoices", "read"))):
    with DBManager():
        setting = AppSetting.get_or_none(AppSetting.key == "invoice_template")
        try:
            stored = json.loads(setting.value or "{}") if setting else {}
        except (TypeError, ValueError):
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        if stored.get("paper_size") == "receipt":
            stored["paper_size"] = "receipt80"
        allowed = set(InvoiceTemplateInput.model_fields)
        stored = {key: value for key, value in stored.items() if key in allowed}
        try:
            validated = InvoiceTemplateInput.model_validate(stored)
            result = validated.model_dump()
        except Exception:
            result = dict(DEFAULT_TEMPLATE)
            for key in ("company_name", "legal_id", "address", "phone", "footer"):
                value = stored.get(key)
                if isinstance(value, str):
                    result[key] = value
        return result


@router.put("/template")
def save_invoice_template(
    payload: InvoiceTemplateInput,
    _user=Depends(require_permission("invoices", "update")),
):
    value = json.dumps(payload.model_dump(), ensure_ascii=False, separators=(",", ":"))
    with DBManager():
        setting = AppSetting.get_or_none(AppSetting.key == "invoice_template")
        if setting is None:
            AppSetting.create(key="invoice_template", value=value)
        else:
            setting.value = value
            setting.save(only=[AppSetting.value, AppSetting.updated_at])
    return payload.model_dump()
