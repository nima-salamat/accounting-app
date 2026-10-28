"""Industry starter packs for common small-business workflows.

These packs add optional custom columns and strongly named custom entities. They
do not silently create fake inventory, prices, accounting balances or customers.
"""
from copy import deepcopy

PROFILES = {
    "general": {
        "label": "کسب‌وکار عمومی",
        "description": "کالا، مشتری، هزینه، سند حسابداری و گزارش‌های پایه",
        "rows": [
            ("products", "", "sku", "کد کالا / SKU", "text", False),
            ("products", "", "barcode", "بارکد", "text", False),
            ("products", "", "unit", "واحد شمارش", "text", False),
            ("receipts", "", "customer_name", "نام مشتری", "text", False),
            ("receipts", "", "customer_phone", "تلفن مشتری", "text", False),
            ("receipts", "", "invoice_note", "توضیحات فاکتور", "text", False),
            ("expense_records", "هزینه‌ها", "expense_date", "تاریخ هزینه", "date", True),
            ("expense_records", "هزینه‌ها", "category", "دسته هزینه", "text", True),
            ("expense_records", "هزینه‌ها", "amount", "مبلغ", "decimal", True),
            ("expense_records", "هزینه‌ها", "description", "شرح", "text", True),
            ("customers", "مشتریان", "name", "نام مشتری", "text", True),
            ("customers", "مشتریان", "phone", "تلفن", "text", False),
            ("customers", "مشتریان", "email", "ایمیل", "text", False),
            ("customers", "مشتریان", "credit_limit", "سقف اعتبار", "decimal", False),
            ("suppliers", "تأمین‌کنندگان", "name", "نام تأمین‌کننده", "text", True),
            ("suppliers", "تأمین‌کنندگان", "phone", "تلفن", "text", False),
            ("suppliers", "تأمین‌کنندگان", "tax_id", "شناسه مالیاتی", "text", False),
        ],
    },
    "supermarket": {
        "label": "سوپرمارکت / خرده‌فروشی",
        "description": "بارکد، واحد و بسته، انقضا، تأمین‌کننده، خرید و شمارش موجودی",
        "rows": [
            ("products", "", "sku", "کد کالا", "text", False),
            ("products", "", "barcode", "بارکد / GTIN", "text", False),
            ("products", "", "brand", "برند", "text", False),
            ("products", "", "unit", "واحد فروش", "text", True),
            ("products", "", "package_size", "اندازه بسته", "decimal", False),
            ("products", "", "expiry_date", "تاریخ انقضا", "date", False),
            ("products", "", "minimum_stock", "حداقل موجودی", "decimal", False),
            ("receipts", "", "customer_name", "مشتری", "text", False),
            ("receipts", "", "cashier_note", "یادداشت صندوق", "text", False),
            ("suppliers", "تأمین‌کنندگان", "name", "نام تأمین‌کننده", "text", True),
            ("suppliers", "تأمین‌کنندگان", "phone", "تلفن", "text", False),
            ("suppliers", "تأمین‌کنندگان", "payment_terms", "مهلت پرداخت", "text", False),
            ("suppliers", "تأمین‌کنندگان", "tax_id", "شناسه مالیاتی", "text", False),
            ("purchase_orders", "سفارش‌های خرید", "supplier", "تأمین‌کننده", "text", True),
            ("purchase_orders", "سفارش‌های خرید", "order_date", "تاریخ سفارش", "date", True),
            ("purchase_orders", "سفارش‌های خرید", "expected_date", "تاریخ تحویل", "date", False),
            ("purchase_orders", "سفارش‌های خرید", "status", "وضعیت", "text", True),
            ("purchase_orders", "سفارش‌های خرید", "total_amount", "مبلغ کل", "decimal", True),
            ("stocktakes", "شمارش موجودی", "count_date", "تاریخ شمارش", "date", True),
            ("stocktakes", "شمارش موجودی", "aisle", "راهرو / بخش", "text", False),
            ("stocktakes", "شمارش موجودی", "reviewed_by", "تأییدکننده", "text", False),
        ],
    },
    "cafe": {
        "label": "کافه / رستوران",
        "description": "منوی غذا و نوشیدنی، میز، سفارش، مواد اولیه و هزینه‌های روزانه",
        "rows": [
            ("products", "", "menu_section", "گروه منو", "text", False),
            ("products", "", "prep_minutes", "زمان آماده‌سازی (دقیقه)", "integer", False),
            ("products", "", "allergens", "مواد حساسیت‌زا", "text", False),
            ("products", "", "serving_size", "اندازه سرو", "text", False),
            ("receipts", "", "table_number", "شماره میز", "text", False),
            ("receipts", "", "order_type", "نوع سفارش", "text", False),
            ("receipts", "", "customer_note", "یادداشت سفارش", "text", False),
            ("cafe_tables", "میزهای کافه", "table_number", "شماره میز", "text", True),
            ("cafe_tables", "میزهای کافه", "seats", "تعداد صندلی", "integer", True),
            ("cafe_tables", "میزهای کافه", "section", "بخش سالن", "text", False),
            ("reservations", "رزروها", "customer_name", "نام مشتری", "text", True),
            ("reservations", "رزروها", "reservation_date", "تاریخ رزرو", "date", True),
            ("reservations", "رزروها", "party_size", "تعداد نفرات", "integer", True),
            ("reservations", "رزروها", "status", "وضعیت رزرو", "text", True),
            ("recipes", "رسپی و مواد اولیه", "menu_item", "نام آیتم منو", "text", True),
            ("recipes", "رسپی و مواد اولیه", "ingredient", "ماده اولیه", "text", True),
            ("recipes", "رسپی و مواد اولیه", "quantity", "مقدار مصرف", "decimal", True),
            ("recipes", "رسپی و مواد اولیه", "unit", "واحد", "text", True),
        ],
    },
    "service": {
        "label": "خدمات / کسب‌وکار آزاد",
        "description": "مشتری، پروژه، قرارداد، زمان کار، هزینه و صورت‌حساب خدمات",
        "rows": [
            ("receipts", "", "customer_name", "مشتری", "text", False),
            ("receipts", "", "service_period", "دوره خدمت", "text", False),
            ("receipts", "", "project_code", "کد پروژه", "text", False),
            ("customers", "مشتریان", "name", "نام مشتری", "text", True),
            ("customers", "مشتریان", "phone", "تلفن", "text", False),
            ("customers", "مشتریان", "billing_address", "نشانی صورتحساب", "text", False),
            ("projects", "پروژه‌ها", "name", "نام پروژه", "text", True),
            ("projects", "پروژه‌ها", "customer", "مشتری", "text", True),
            ("projects", "پروژه‌ها", "start_date", "تاریخ شروع", "date", False),
            ("projects", "پروژه‌ها", "due_date", "موعد تحویل", "date", False),
            ("projects", "پروژه‌ها", "status", "وضعیت", "text", True),
            ("projects", "پروژه‌ها", "budget", "بودجه", "decimal", False),
            ("work_logs", "کارکرد و زمان", "project", "پروژه", "text", True),
            ("work_logs", "کارکرد و زمان", "work_date", "تاریخ کار", "date", True),
            ("work_logs", "کارکرد و زمان", "hours", "ساعت کار", "decimal", True),
            ("work_logs", "کارکرد و زمان", "hourly_rate", "نرخ ساعتی", "decimal", False),
            ("contracts", "قراردادها", "customer", "مشتری", "text", True),
            ("contracts", "قراردادها", "start_date", "شروع قرارداد", "date", True),
            ("contracts", "قراردادها", "end_date", "پایان قرارداد", "date", False),
            ("contracts", "قراردادها", "value", "ارزش قرارداد", "decimal", True),
        ],
    },
    "real_estate": {
        "label": "مدیریت املاک",
        "description": "ملک، مالک، مستأجر، اجاره‌نامه، ودیعه، اقساط و سررسید قرارداد",
        "rows": [
            ("properties", "املاک", "property_code", "کد ملک", "text", True),
            ("properties", "املاک", "address", "نشانی ملک", "text", True),
            ("properties", "املاک", "property_type", "نوع ملک", "text", True),
            ("properties", "املاک", "area_m2", "متراژ (متر مربع)", "decimal", False),
            ("properties", "املاک", "owner_name", "نام مالک", "text", True),
            ("properties", "املاک", "status", "وضعیت ملک", "text", True),
            ("owners", "مالکان", "name", "نام مالک", "text", True),
            ("owners", "مالکان", "phone", "تلفن", "text", False),
            ("owners", "مالکان", "national_id", "شناسه مالک", "text", False),
            ("tenants", "مستأجران", "name", "نام مستأجر", "text", True),
            ("tenants", "مستأجران", "phone", "تلفن", "text", True),
            ("tenants", "مستأجران", "identity_ref", "شناسه هویتی", "text", False),
            ("leases", "اجاره‌نامه‌ها", "property_code", "کد ملک", "text", True),
            ("leases", "اجاره‌نامه‌ها", "tenant", "مستأجر", "text", True),
            ("leases", "اجاره‌نامه‌ها", "start_date", "شروع قرارداد", "date", True),
            ("leases", "اجاره‌نامه‌ها", "end_date", "پایان قرارداد", "date", True),
            ("leases", "اجاره‌نامه‌ها", "deposit", "ودیعه", "decimal", True),
            ("leases", "اجاره‌نامه‌ها", "monthly_rent", "اجاره ماهانه", "decimal", True),
            ("leases", "اجاره‌نامه‌ها", "due_day", "روز سررسید ماهانه", "integer", True),
            ("rent_payments", "پرداخت اجاره", "lease_code", "کد اجاره‌نامه", "text", True),
            ("rent_payments", "پرداخت اجاره", "due_date", "تاریخ سررسید", "date", True),
            ("rent_payments", "پرداخت اجاره", "paid_date", "تاریخ پرداخت", "date", False),
            ("rent_payments", "پرداخت اجاره", "amount", "مبلغ", "decimal", True),
            ("rent_payments", "پرداخت اجاره", "status", "وضعیت", "text", True),
        ],
    },
}


def profile_options():
    return [
        {"key": key, "label": profile["label"], "description": profile["description"]}
        for key, profile in PROFILES.items()
    ]


def build_profile_rows(profile_key):
    profile_key = profile_key if profile_key in PROFILES else "general"
    rows = []
    for model_key, model_label, field_key, field_label, field_type, required in PROFILES[profile_key]["rows"]:
        rows.append({
            "model_key": model_key,
            "model_label": model_label,
            "field_key": field_key,
            "field_label": field_label,
            "field_type": field_type,
            "is_required": required,
        })
    return deepcopy(rows)


def profile_metadata(profile_key, company_name):
    key = profile_key if profile_key in PROFILES else "general"
    return {
        "company_name": str(company_name or "").strip()[:256],
        "business_profile": key,
        "business_profile_label": PROFILES[key]["label"],
    }
