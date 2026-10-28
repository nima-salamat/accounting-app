"""Safe, dependency-light HTML rendering for printed invoices."""
from datetime import datetime
from html import escape
import re

DEFAULT_TEMPLATE = {
    "company_name": "نام کسب‌وکار",
    "legal_id": "",
    "address": "",
    "phone": "",
    "footer": "از خرید شما سپاسگزاریم.",
    "paper_size": "A4",
    "accent_color": "#3157A4",
}


def _text(value):
    return escape("" if value is None else str(value))


def _money(value):
    try:
        return "{:,.2f}".format(float(value or 0))
    except (TypeError, ValueError):
        return "0.00"


def render_invoice_html(receipt, template=None):
    """Render receipt data with escaped values; template settings are not HTML."""
    config = dict(DEFAULT_TEMPLATE)
    if isinstance(template, dict):
        config.update({key: value for key, value in template.items() if key in config})
    accent = str(config.get("accent_color") or DEFAULT_TEMPLATE["accent_color"])
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", accent):
        accent = DEFAULT_TEMPLATE["accent_color"]
    receipt_number = receipt.get("day_receipt_id") or str(receipt.get("id", ""))[:8]
    created_at = str(receipt.get("created_at") or "")
    try:
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        created_at = created_at[:32] or "—"
    items = receipt.get("items") or []
    rows = []
    for index, item in enumerate(items, 1):
        name = item.get("product_name") or item.get("name") or "کالای حذف‌شده"
        quantity = item.get("quantity", 0)
        price = item.get("sell_price", item.get("price", 0))
        try:
            line_total = float(quantity or 0) * float(price or 0)
        except (TypeError, ValueError):
            line_total = 0
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                index, _text(name), _text(quantity), _money(price)
            ) + "<td class='sum'>{}</td>".format(_money(line_total))
        )
    if not rows:
        rows.append("<tr><td colspan='5' class='empty'>جزئیات ردیف‌های فاکتور در دسترس نیست.</td></tr>")
    payment = "پرداخت‌شده" if receipt.get("payed") else "پرداخت‌نشده"
    paper_width = "78mm" if config.get("paper_size") == "receipt" else "100%"
    body_width = "74mm" if config.get("paper_size") == "receipt" else "100%"
    return """<!doctype html>
<html lang="fa" dir="rtl">
<head><meta charset="utf-8"><style>
@page { margin: 14mm; }
* { box-sizing: border-box; }
body { margin: 0; color: #182235; font-family: "Vazirmatn","Segoe UI","Noto Sans Arabic",sans-serif; background: #fff; }
.invoice { width: %s; max-width: 100%%; margin: 0 auto; padding: 24px; }
.brand { border-bottom: 3px solid %s; padding-bottom: 16px; margin-bottom: 20px; }
h1 { margin: 0 0 6px; color: %s; font-size: 24px; }
h2 { font-size: 17px; margin: 0 0 14px; }
.meta { color: #5f6d80; font-size: 12px; line-height: 1.9; }
.summary { display: flex; justify-content: space-between; gap: 16px; margin: 18px 0; padding: 12px 14px; background: #f4f7fb; border-radius: 8px; }
table { width: 100%%; border-collapse: collapse; font-size: 12px; }
th { background: %s; color: white; text-align: right; padding: 10px 8px; }
td { padding: 10px 8px; border-bottom: 1px solid #e2e8f0; }
.sum { direction: ltr; text-align: left; white-space: nowrap; }
tfoot td { font-weight: bold; }
.total { font-size: 19px; color: %s; text-align: left; }
.footer { margin-top: 28px; border-top: 1px solid #e2e8f0; padding-top: 12px; color: #5f6d80; font-size: 12px; text-align: center; }
.empty { text-align: center; color: #64748b; padding: 24px; }
@media print { body { background: white; } .invoice { padding: 0; } }
</style></head>
<body><main class="invoice">
<header class="brand"><h1>%s</h1>
<div class="meta">%s</div><div class="meta">%s</div><div class="meta">%s</div></header>
<h2>فاکتور فروش شمارهٔ %s</h2>
<div class="summary"><div><strong>تاریخ</strong><br>%s</div><div><strong>وضعیت پرداخت</strong><br>%s</div></div>
<table><thead><tr><th>#</th><th>شرح کالا</th><th>تعداد</th><th>فی واحد</th><th>جمع</th></tr></thead>
<tbody>%s</tbody>
<tfoot><tr><td colspan="4">مبلغ نهایی</td><td class="total sum">%s</td></tr></tfoot></table>
<footer class="footer">%s</footer>
</main></body></html>""" % (
        body_width, accent, accent, accent, accent,
        _text(config.get("company_name")), _text(config.get("legal_id")),
        _text(config.get("address")), _text(config.get("phone")),
        _text(receipt_number), _text(created_at), _text(payment),
        "".join(rows), _money(receipt.get("total_price")), _text(config.get("footer")),
    )
