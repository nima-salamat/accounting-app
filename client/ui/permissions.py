"""Client-side permission display helpers; server authorization remains authoritative."""

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
ACTION_LABELS = (("r", "مشاهده"), ("c", "ایجاد"), ("u", "ویرایش"), ("d", "حذف"))

LEGACY_CASHIER = {
    "products": "r", "categories": "r", "warehouse": "r",
    "checks_in": "r", "checks_out": "r", "sales": "c",
    "receipts": "rud", "reports": "r", "invoices": "r",
}
ROLE_GRANTS = {
    "cashier": dict(LEGACY_CASHIER),
    "inventory": {
        "products": "ru", "categories": "r", "warehouse": "rcud",
        "checks_in": "r", "checks_out": "r", "sales": "c",
        "receipts": "r", "reports": "r", "invoices": "r",
    },
    "accountant": {
        "products": "rcud", "categories": "rcud", "warehouse": "rcud",
        "checks_in": "rcud", "checks_out": "rcud", "sales": "cu",
        "receipts": "rcud", "reports": "r", "schemas": "r", "invoices": "ru",
    },
    "viewer": {resource: "r" for resource in RESOURCE_LABELS},
    "custom": {},
}
ROLE_LABELS = {
    "cashier": "صندوق‌دار",
    "inventory": "انباردار",
    "accountant": "حسابدار",
    "viewer": "فقط مشاهده",
    "custom": "سفارشی",
}


def parse_grants(raw):
    text = str(raw or "").strip()
    if not text:
        return dict(LEGACY_CASHIER), "cashier"
    grants = {}
    role = "custom"
    if text.lower() == "none":
        return {}, "custom"
    for token in text.replace(",", ";").split(";"):
        token = token.strip()
        if not token:
            continue
        if token.lower().startswith("role:"):
            candidate = token.split(":", 1)[1].strip().lower()
            if candidate in ROLE_GRANTS:
                role = candidate
            continue
        if ":" not in token:
            continue
        resource, actions = token.split(":", 1)
        resource = resource.strip().lower()
        raw_actions = actions.strip().lower()
        if raw_actions in {"read", "create", "update", "delete"}:
            actions = {"read": "r", "create": "c", "update": "u", "delete": "d"}[raw_actions]
        elif any(separator in raw_actions for separator in (" ", "|", "+")):
            parts = raw_actions.replace("|", " ").replace("+", " ").split()
            actions = "".join(
                {"read": "r", "create": "c", "update": "u", "delete": "d"}.get(part, "")
                for part in parts
            )
        else:
            actions = "".join(ch for ch in raw_actions if ch in "rcud")
        if resource in RESOURCE_LABELS and actions:
            grants[resource] = "".join(ch for ch in "rcud" if ch in actions)
    return grants, role


def encode_grants(grants, role="custom"):
    tokens = []
    if role in ROLE_GRANTS:
        tokens.append("role:" + role)
    for resource in RESOURCE_LABELS:
        actions = grants.get(resource, "")
        actions = "".join(ch for ch in "rcud" if ch in str(actions))
        if actions:
            tokens.append("{}:{}".format(resource, actions))
    if not any(":" in item and not item.startswith("role:") for item in tokens):
        tokens.append("none")
    return ";".join(tokens)


def can_access(user, resource, action="read"):
    if not user:
        return False
    if bool(user.get("is_admin")):
        return True
    code = {"read": "r", "create": "c", "update": "u", "delete": "d"}.get(action)
    if not code:
        return False
    grants, _role = parse_grants(user.get("buttons", ""))
    return code in grants.get(resource, "")
