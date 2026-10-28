"""Shared kiosk policy storage and server-side enforcement."""
import json

from fastapi import HTTPException

from accounting_app.database.extension_models import AppSetting
from accounting_app.database.models import Product


KIOSK_SETTINGS_KEY = "kiosk_settings"
COMPANY_PROFILE_KEY = "company_profile"


def _json_setting(key):
    setting = AppSetting.get_or_none(AppSetting.key == key)
    try:
        value = json.loads(setting.value or "{}") if setting else {}
    except (TypeError, ValueError):
        value = {}
    return value if isinstance(value, dict) else {}


def load_kiosk_settings():
    """Return defaults overlaid by persistent kiosk policy."""
    company = _json_setting(COMPANY_PROFILE_KEY)
    profile = str(company.get("business_profile") or "general")
    stored = _json_setting(KIOSK_SETTINGS_KEY)
    product_ids = stored.get("allowed_product_ids")
    if not isinstance(product_ids, list):
        product_ids = []
    try:
        hours = max(0, min(720, int(stored.get("receipt_history_hours", 48))))
    except (TypeError, ValueError):
        hours = 48
    return {
        "active": bool(stored.get("active", False)),
        "allowed_product_ids": [str(value) for value in product_ids if isinstance(value, (str, int))],
        "receipt_history_hours": hours,
        "cafe_seat_selection": bool(stored.get("cafe_seat_selection", profile == "cafe")),
        "allow_unpaid_orders": bool(stored.get("allow_unpaid_orders", False)),
        "business_profile": profile,
        "company_name": str(company.get("company_name") or "کسب‌وکار من"),
    }


def save_kiosk_settings(values):
    serialized = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    setting = AppSetting.get_or_none(AppSetting.key == KIOSK_SETTINGS_KEY)
    if setting is None:
        AppSetting.create(key=KIOSK_SETTINGS_KEY, value=serialized)
    else:
        setting.value = serialized
        setting.save(only=[AppSetting.value, AppSetting.updated_at])
    return load_kiosk_settings()


def is_kiosk_user(user):
    raw = str(getattr(user, "buttons", "") or "")
    return any(token.strip().lower() == "role:kiosk" for token in raw.split(";"))


def kiosk_product_ids_for_user(user):
    """Return None for ordinary users; enforce active policy and return allowed IDs for kiosk accounts."""
    if not is_kiosk_user(user):
        return None
    config = load_kiosk_settings()
    if not config["active"]:
        raise HTTPException(status_code=403, detail="کیوسک در پنل مدیر غیرفعال است.")
    return set(config["allowed_product_ids"])


def enforce_kiosk_products(user, product_ids):
    allowed = kiosk_product_ids_for_user(user)
    if allowed is None:
        return
    forbidden = [str(product_id) for product_id in product_ids if str(product_id) not in allowed]
    if forbidden:
        raise HTTPException(
            status_code=403,
            detail="یکی از کالاهای این سفارش برای کیوسک مجاز نیست؛ فهرست محصولات را بازخوانی کنید.",
        )


def validate_kiosk_seat(user, seat_number):
    """Require a seat when cafe service has seat selection enabled, regardless of the client UI."""
    config = load_kiosk_settings()
    if config["cafe_seat_selection"] and (is_kiosk_user(user) or config["business_profile"] == "cafe"):
        if not str(seat_number or "").strip():
            raise HTTPException(status_code=422, detail="برای فروش کافه، شماره صندلی الزامی است.")
