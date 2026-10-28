"""Server-persisted invoice template settings, validated at the API boundary."""
import json
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import AppSetting
from server.app.permissions import require_permission

router = APIRouter(prefix="/invoices", tags=["invoices"])

DEFAULT_TEMPLATE = {
    "company_name": "نام کسب‌وکار",
    "legal_id": "",
    "address": "",
    "phone": "",
    "footer": "از خرید شما سپاسگزاریم.",
    "paper_size": "A4",
    "accent_color": "#3157A4",
}


class InvoiceTemplateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str = Field(default="نام کسب‌وکار", min_length=1, max_length=160)
    legal_id: str = Field(default="", max_length=80)
    address: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=80)
    footer: str = Field(default="از خرید شما سپاسگزاریم.", max_length=500)
    paper_size: Literal["A4", "receipt"] = "A4"
    accent_color: str = Field(default="#3157A4", pattern=r"^#[0-9A-Fa-f]{6}$")


@router.get("/template")
def get_invoice_template(_user=Depends(require_permission("invoices", "read"))):
    with DBManager():
        setting = AppSetting.get_or_none(AppSetting.key == "invoice_template")
        if setting is None:
            return dict(DEFAULT_TEMPLATE)
        try:
            stored = json.loads(setting.value or "{}")
        except (TypeError, ValueError):
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        # Only supported fields are exposed; corrupt or old settings fall back safely.
        result = dict(DEFAULT_TEMPLATE)
        for key in DEFAULT_TEMPLATE:
            value = stored.get(key, result[key])
            if isinstance(value, str):
                result[key] = value
        if result["paper_size"] not in ("A4", "receipt"):
            result["paper_size"] = "A4"
        if not __import__("re").fullmatch(r"#[0-9A-Fa-f]{6}", result["accent_color"]):
            result["accent_color"] = DEFAULT_TEMPLATE["accent_color"]
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
