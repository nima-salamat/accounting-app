"""Fine-grained, server-enforced permissions for accounting resources.

The compact User.buttons field remains the storage format for compatibility with
existing databases. New grants use `resource:rcud` tokens separated by semicolons
(read/create/update/delete). A blank legacy value retains the historical cashier
access; the explicit token `none` denies every non-admin permission.
"""
from fastapi import Depends, HTTPException, status

from server.app.dependencies import get_current_user

_ACTION_CODES = {"read": "r", "create": "c", "update": "u", "delete": "d"}

# Least-surprise compatibility for users created before granular permission
# policies existed: they can perform their former cashier/read-only workflow.
_LEGACY_CASHIER = {
    "products": "r",
    "categories": "r",
    "warehouse": "r",
    "checks_in": "r",
    "checks_out": "r",
    "sales": "c",
    "receipts": "rud",
    "reports": "r",
    "invoices": "r",
}

RESOURCE_LABELS = {
    "dashboard": "نمای کلی",
    "sales": "فروش",
    "products": "محصولات",
    "categories": "دسته‌بندی‌ها",
    "warehouse": "انبار",
    "checks_in": "چک‌های دریافتی",
    "checks_out": "چک‌های پرداختی",
    "receipts": "رسیدها و فاکتورها",
    "reports": "گزارش‌ها",
    "schemas": "مدل‌ها و فیلدهای سفارشی",
    "invoices": "قالب فاکتور",
}


def parse_grants(raw):
    """Parse compact grants without ever treating malformed text as a grant."""
    text = str(raw or "").strip()
    if not text:
        return dict(_LEGACY_CASHIER)
    if text.lower() == "none":
        return {}
    grants = {}
    for token in text.replace(",", ";").split(";"):
        token = token.strip()
        if not token or token.startswith("role:"):
            continue
        if ":" not in token:
            continue
        resource, actions = token.split(":", 1)
        resource = resource.strip().lower()
        actions = actions.strip().lower()
        if resource not in RESOURCE_LABELS:
            continue
        compact = set()
        for part in actions.replace("|", " ").split():
            if part in _ACTION_CODES:
                compact.add(_ACTION_CODES[part])
            else:
                compact.update(ch for ch in part if ch in "rcud")
        if compact:
            grants[resource] = "".join(ch for ch in "rcud" if ch in compact)
    return grants


def encode_grants(grants, role=None):
    """Serialize an allow-list in a deterministic, length-efficient format."""
    tokens = []
    if role:
        safe_role = str(role).strip().lower()
        if safe_role.replace("_", "").isalnum():
            tokens.append("role:" + safe_role)
    for resource in RESOURCE_LABELS:
        actions = grants.get(resource, "")
        if isinstance(actions, (set, list, tuple)):
            actions = "".join(ch for ch in "rcud" if ch in set(actions))
        else:
            actions = "".join(ch for ch in "rcud" if ch in str(actions))
        if actions:
            tokens.append("{}:{}".format(resource, actions))
    return ";".join(tokens) if len(tokens) > (1 if role else 0) else "none"


def has_permission(user, resource, action):
    if user is None:
        return False
    if bool(getattr(user, "is_admin", False)):
        return True
    code = _ACTION_CODES.get(action)
    if code is None or resource not in RESOURCE_LABELS:
        return False
    return code in parse_grants(getattr(user, "buttons", "")).get(resource, "")


def require_permission(resource, action):
    """Create a FastAPI dependency that denies unauthorized server requests."""
    def dependency(user=Depends(get_current_user)):
        if not has_permission(user, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="برای این عملیات مجوز «{} / {}» ندارید.".format(
                    RESOURCE_LABELS.get(resource, resource), action
                ),
            )
        return user
    dependency.__name__ = "require_{}_{}_permission".format(resource, action)
    return dependency
