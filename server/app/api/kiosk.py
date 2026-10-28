"""Kiosk configuration endpoints for authorized administrators and kiosk clients."""
from fastapi import APIRouter, Depends, HTTPException

from accounting_app.database.connection import DBManager
from accounting_app.database.models import Product
from accounting_app.services.audit import record_audit
from accounting_app.services.kiosk_config import load_kiosk_settings, save_kiosk_settings
from server.app.permissions import require_permission
from server.app.schemas import KioskSettingsUpdate

router = APIRouter(prefix="/kiosk", tags=["kiosk"])


@router.get("/settings")
def read_kiosk_settings(
    user=Depends(require_permission("kiosk", "read")),
    _products=Depends(require_permission("products", "read")),
):
    """Manager-facing configuration; users need an explicit kiosk read grant."""
    with DBManager():
        return load_kiosk_settings()


@router.put("/settings")
def update_kiosk_settings(
    payload: KioskSettingsUpdate,
    user=Depends(require_permission("kiosk", "update")),
    _products=Depends(require_permission("products", "read")),
):
    """Persist allowlisted kiosk products and behaviour with server-side validation."""
    with DBManager():
        selected = [str(item) for item in payload.allowed_product_ids]
        existing = {
            str(row.id)
            for row in Product.select(Product.id).where(Product.id.in_(payload.allowed_product_ids))
        } if payload.allowed_product_ids else set()
        missing = sorted(set(selected) - existing)
        if missing:
            raise HTTPException(status_code=422, detail="یک یا چند محصول انتخاب‌شده وجود ندارد.")
        values = payload.model_dump(mode="json")
        saved = save_kiosk_settings(values)
        record_audit(
            user, "kiosk.settings_updated", "kiosk", None,
            {
                "active": saved["active"],
                "allowed_product_count": len(saved["allowed_product_ids"]),
                "receipt_history_hours": saved["receipt_history_hours"],
                "cafe_seat_selection": saved["cafe_seat_selection"],
                "allow_unpaid_orders": saved["allow_unpaid_orders"],
            },
        )
        return saved


@router.get("/config")
def get_kiosk_runtime_config(
    user=Depends(require_permission("kiosk", "read")),
    _product_access=Depends(require_permission("products", "read")),
):
    """Small policy response consumed by the self-service client."""
    with DBManager():
        config = load_kiosk_settings()
        return {
            "active": config["active"],
            "allowed_product_ids": config["allowed_product_ids"],
            "receipt_history_hours": config["receipt_history_hours"],
            "cafe_seat_selection": config["cafe_seat_selection"],
            "allow_unpaid_orders": config["allow_unpaid_orders"],
            "business_profile": config["business_profile"],
            "company_name": config["company_name"],
        }
