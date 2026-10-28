"""Safe HTML rendering for printable invoices with configurable paper, borders and block layout."""
from datetime import datetime
from html import escape
import re

BLOCKS = ("company", "metadata", "items", "totals", "footer")
PAPER_DIMENSIONS_MM = {"A4": (210, 297), "A5": (148, 210), "A6": (105, 148),
                       "receipt80": (80, 220), "receipt58": (58, 180)}
ALIGNMENTS = {"left", "center", "right"}
COLUMNS = {"full", "left", "right"}
DEFAULT_TEMPLATE = {
    "company_name": "نام کسب‌وکار", "legal_id": "", "address": "", "phone": "",
    "footer": "از خرید شما سپاسگزاریم.", "paper_size": "A4", "orientation": "portrait",
    "margin_mm": 12, "accent_color": "#3157A4", "show_border": True,
    "frame_border_color": "#CBD5E1",
    "layout_order": ["company", "metadata", "items", "totals", "footer"],
    "block_settings": {
        "company": {"column": "full", "align": "right"},
        "metadata": {"column": "right", "align": "right"},
        "items": {"column": "full", "align": "right"},
        "totals": {"column": "left", "align": "left"},
        "footer": {"column": "full", "align": "center"},
    },
    "table_alignment": {"index": "center", "name": "right", "quantity": "center",
                        "unit_price": "left", "line_total": "left"},
}


def _text(value):
    return escape("" if value is None else str(value))


def _money(value):
    try:
        return "{:,.2f}".format(float(value or 0))
    except (TypeError, ValueError):
        return "0.00"


def _valid_color(value, fallback):
    value = str(value or "")
    return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback


def _template_config(template):
    config = dict(DEFAULT_TEMPLATE)
    if isinstance(template, dict):
        for key, value in template.items():
            if key in config:
                config[key] = value
    config["paper_size"] = config["paper_size"] if config["paper_size"] in PAPER_DIMENSIONS_MM else "A4"
    config["orientation"] = config["orientation"] if config["orientation"] in ("portrait", "landscape") else "portrait"
    try:
        config["margin_mm"] = max(3, min(30, int(config["margin_mm"])))
    except (TypeError, ValueError):
        config["margin_mm"] = DEFAULT_TEMPLATE["margin_mm"]
    config["accent_color"] = _valid_color(config["accent_color"], DEFAULT_TEMPLATE["accent_color"])
    config["frame_border_color"] = _valid_color(config["frame_border_color"], DEFAULT_TEMPLATE["frame_border_color"])
    order = config.get("layout_order")
    if not isinstance(order, list):
        order = list(BLOCKS)
    clean = []
    for block in order:
        if block in BLOCKS and block not in clean:
            clean.append(block)
    config["layout_order"] = clean + [block for block in BLOCKS if block not in clean]
    block_settings = dict(DEFAULT_TEMPLATE["block_settings"])
    if isinstance(config.get("block_settings"), dict):
        for block in BLOCKS:
            value = config["block_settings"].get(block)
            if isinstance(value, dict):
                block_settings[block] = {
                    "column": value.get("column") if value.get("column") in COLUMNS else block_settings[block]["column"],
                    "align": value.get("align") if value.get("align") in ALIGNMENTS else block_settings[block]["align"],
                }
    config["block_settings"] = block_settings
    table_alignment = dict(DEFAULT_TEMPLATE["table_alignment"])
    if isinstance(config.get("table_alignment"), dict):
        for key in table_alignment:
            if config["table_alignment"].get(key) in ALIGNMENTS:
                table_alignment[key] = config["table_alignment"][key]
    config["table_alignment"] = table_alignment
    config["show_border"] = bool(config.get("show_border", True))
    return config


def render_invoice_html(receipt, template=None):
    """Render a safe invoice document that follows selected paper and editable layout options."""
    config = _template_config(template)
    accent, frame_color = config["accent_color"], config["frame_border_color"]
    paper_size = config["paper_size"]
    paper_width, paper_height = PAPER_DIMENSIONS_MM[paper_size]
    if config["orientation"] == "landscape" and paper_size not in ("receipt80", "receipt58"):
        paper_width, paper_height = paper_height, paper_width
    margin = config["margin_mm"]
    page_size_css = (f"{paper_width}mm {paper_height}mm" if paper_size.startswith("receipt")
                     else f"{paper_size} {config['orientation']}")
    min_height = max(70, paper_height - 2 * margin)
    receipt_number = receipt.get("day_receipt_id") or str(receipt.get("id", ""))[:8]
    created_at = str(receipt.get("created_at") or "")
    try:
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        created_at = created_at[:32] or "—"
    payment = "پرداخت‌شده" if receipt.get("payed") else "پرداخت‌نشده"
    table_align = config["table_alignment"]
    rows = []
    for index, item in enumerate(receipt.get("items") or [], 1):
        name = item.get("product_name") or item.get("name") or "کالای حذف‌شده"
        quantity = item.get("quantity", 0)
        price = item.get("sell_price", item.get("price", 0))
        try:
            line_total = float(quantity or 0) * float(price or 0)
        except (TypeError, ValueError):
            line_total = 0
        rows.append(
            "<tr><td class='al-{0}'>{1}</td><td class='al-{2}'>{3}</td>"
            "<td class='al-{4}'>{5}</td><td class='al-{6} money'>{7}</td>"
            "<td class='al-{8} money'>{9}</td></tr>".format(
                table_align["index"], index, table_align["name"], _text(name),
                table_align["quantity"], _text(quantity), table_align["unit_price"], _money(price),
                table_align["line_total"], _money(line_total),
            )
        )
    if not rows:
        rows.append("<tr><td colspan='5' class='empty'>جزئیات ردیف‌های فاکتور در دسترس نیست.</td></tr>")
    blocks = {
        "company": ("<header class='brand'><h1>{}</h1><div class='meta'>{}</div>"
                    "<div class='meta'>{}</div><div class='meta'>{}</div></header>").format(
            _text(config.get("company_name")), _text(config.get("legal_id")),
            _text(config.get("address")), _text(config.get("phone"))),
        "metadata": ("<section class='meta-box'><h2>فاکتور فروش شمارهٔ {}</h2>"
                     "<div class='meta-grid'><div><strong>تاریخ</strong><br>{}</div>"
                     "<div><strong>وضعیت پرداخت</strong><br>{}</div></div></section>").format(
            _text(receipt_number), _text(created_at), _text(payment)),
        "items": ("<section class='items'><table><thead><tr><th class='al-{}'>#</th>"
                  "<th class='al-{}'>شرح کالا</th><th class='al-{}'>تعداد</th>"
                  "<th class='al-{}'>فی واحد</th><th class='al-{}'>جمع</th></tr></thead>"
                  "<tbody>{}</tbody></table></section>").format(
            table_align["index"], table_align["name"], table_align["quantity"],
            table_align["unit_price"], table_align["line_total"], "".join(rows)),
        "totals": "<section class='totals'><div>مبلغ نهایی</div><strong>{}</strong></section>".format(
            _money(receipt.get("total_price"))),
        "footer": "<footer class='footer'>{}</footer>".format(_text(config.get("footer"))),
    }
    rendered_blocks = []
    for block in config["layout_order"]:
        settings = config["block_settings"][block]
        rendered_blocks.append(
            "<div class='layout-block block-{} col-{} align-{}'>{}</div>".format(
                block, settings["column"], settings["align"], blocks[block])
        )
    border = "2px solid {}".format(frame_color) if config["show_border"] else "none"
    radius = "3px" if config["show_border"] else "0"
    return """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>
@page { size: %s; margin: %smm; }
* { box-sizing: border-box; }
html, body { margin:0; padding:0; color:#182235; font-family:"Vazirmatn","Segoe UI","Noto Sans Arabic",sans-serif; background:#fff; }
.invoice { width:100%%; min-height:%smm; border:%s; border-radius:%s; padding:8mm; display:flex; flex-direction:column; }
.layout-grid { direction:ltr; flex:1; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); align-content:space-between; column-gap:8mm; row-gap:7mm; }
.layout-block { min-width:0; direction:rtl; break-inside:avoid; }
.col-full { grid-column:1 / -1; } .col-left { grid-column:1; } .col-right { grid-column:2; }
.align-left { text-align:left; } .align-center { text-align:center; } .align-right { text-align:right; }
.brand { border:1px solid #D9E1EC; border-top:3px solid %s; padding:6mm; border-radius:3px; }
h1 { margin:0 0 3mm; color:%s; font-size:23px; } h2 { font-size:16px; margin:0 0 3mm; color:#22334A; }
.meta { color:#5F6D80; font-size:10px; line-height:1.8; overflow-wrap:anywhere; }
.meta-box { border:1px solid #E0E6EF; padding:4mm; border-radius:3px; }
.meta-grid { display:grid; grid-template-columns:1fr 1fr; gap:4mm; font-size:11px; line-height:1.8; }
table { width:100%%; border-collapse:collapse; table-layout:fixed; font-size:11px; border:1px solid #CAD4E2; }
th { background:%s; color:white; padding:3mm 2mm; border:1px solid %s; overflow-wrap:anywhere; }
td { padding:2.7mm 2mm; border:1px solid #D7DFEA; overflow-wrap:anywhere; vertical-align:top; }
.al-left { text-align:left; } .al-center { text-align:center; } .al-right { text-align:right; } .money { direction:ltr; white-space:nowrap; }
.totals { margin-top:8mm; padding:5mm; border:1px solid %s; border-top:2px solid %s; display:flex; justify-content:space-between; gap:8mm; align-items:center; font-size:14px; }
.totals strong { direction:ltr; text-align:left; font-size:21px; color:%s; white-space:nowrap; }
.footer { margin-top:7mm; padding:4mm 2mm 0; border-top:1px solid #CBD5E1; color:#5F6D80; font-size:10px; text-align:center; white-space:pre-wrap; }
.empty { text-align:center; color:#64748B; padding:8mm; }
@media print { html,body { background:white; } }
</style></head><body><main class="invoice"><div class="layout-grid">%s</div></main></body></html>""" % (
        page_size_css, margin, min_height, border, radius, accent, accent, accent,
        accent, frame_color, accent, accent, "".join(rendered_blocks),
    )
