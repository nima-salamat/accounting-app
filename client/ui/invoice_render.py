"""Shared physical invoice layout, WYSIWYG drawing and safe HTML rendering.""" 
from datetime import datetime
from html import escape
import math
import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPen

# Desktop POS sales and its receipts history share the admin-designed sales invoice.
# Thermal kiosk receipts remain a separate print workflow.
SALES_INVOICE_TEMPLATE_KIND = "invoice"

BLOCKS = ("company", "metadata", "items", "totals", "footer")
ELEMENT_TYPES = (
    "company", "invoice_number", "invoice_date", "payment_status",
    "seat_number", "items_table", "totals", "footer", "text",
)
PAPER_DIMENSIONS_MM = {
    "A4": (210.0, 297.0), "A5": (148.0, 210.0), "A6": (105.0, 148.0),
    "receipt80": (80.0, 220.0), "receipt58": (58.0, 180.0),
}
ALIGNMENTS = {"left", "center", "right"}
COLUMNS = {"full", "left", "right"}
MAX_THERMAL_ROLL_HEIGHT_MM = 4000.0


def default_elements_for_paper(paper_size="A4", orientation="portrait", margin_mm=12):
    """Build a usable visual layout for the selected physical sheet, using millimetres."""
    paper = "receipt80" if paper_size == "receipt" else paper_size
    paper = paper if paper in PAPER_DIMENSIONS_MM else "A4"
    width, height = PAPER_DIMENSIONS_MM[paper]
    if orientation == "landscape" and paper not in ("receipt80", "receipt58"):
        width, height = height, width
    try:
        margin = max(2.0, min(30.0, float(margin_mm)))
    except (TypeError, ValueError):
        margin = 12.0
    usable_w = max(20.0, width - 2 * margin)
    left = margin
    is_receipt = paper.startswith("receipt")
    if is_receipt:
        header_h = 15.0
        row_h = 7.0
        table_y = margin + header_h + 2 * row_h + 5
        total_y = height - margin - 20
        table_h = max(30.0, total_y - table_y - 4)
        elements = [
            {"id": "company", "type": "company", "label": "نام مجموعه", "x_mm": left, "y_mm": margin, "w_mm": usable_w, "h_mm": header_h, "font_size": 12, "align": "center", "bold": True, "visible": True, "text": ""},
            {"id": "invoice_number", "type": "invoice_number", "label": "شماره فاکتور", "x_mm": left, "y_mm": margin + 16, "w_mm": usable_w, "h_mm": row_h, "font_size": 8, "align": "right", "bold": True, "visible": True, "text": ""},
            {"id": "invoice_date", "type": "invoice_date", "label": "تاریخ", "x_mm": left, "y_mm": margin + 23, "w_mm": usable_w, "h_mm": row_h, "font_size": 8, "align": "right", "bold": False, "visible": True, "text": ""},
            {"id": "payment_status", "type": "payment_status", "label": "وضعیت پرداخت", "x_mm": left, "y_mm": margin + 30, "w_mm": usable_w, "h_mm": row_h, "font_size": 8, "align": "right", "bold": False, "visible": True, "text": ""},
            {"id": "items_table", "type": "items_table", "label": "جدول کالاها", "x_mm": left, "y_mm": table_y, "w_mm": usable_w, "h_mm": table_h, "font_size": 7, "align": "right", "bold": False, "visible": True, "text": ""},
            {"id": "totals", "type": "totals", "label": "مبلغ نهایی", "x_mm": left, "y_mm": total_y, "w_mm": usable_w, "h_mm": 11, "font_size": 10, "align": "right", "bold": True, "visible": True, "text": ""},
            {"id": "footer", "type": "footer", "label": "متن پایانی", "x_mm": left, "y_mm": height - margin - 8, "w_mm": usable_w, "h_mm": 7, "font_size": 7, "align": "center", "bold": False, "visible": True, "text": ""},
        ]
        if usable_w >= 65:
            elements.insert(4, {"id": "seat_number", "type": "seat_number", "label": "شماره میز / صندلی", "x_mm": left, "y_mm": margin + 37, "w_mm": usable_w, "h_mm": row_h, "font_size": 8, "align": "right", "bold": False, "visible": True, "text": ""})
            elements[4]["y_mm"] = table_y - 7
        return elements

    top = margin
    table_y = top + 47
    totals_y = height - margin - 37
    table_h = max(35.0, totals_y - table_y - 6)
    right_col_w = usable_w * 0.40
    left_col_w = usable_w * 0.36
    elements = [
        {"id": "invoice_date", "type": "invoice_date", "label": "تاریخ", "x_mm": left, "y_mm": top, "w_mm": left_col_w, "h_mm": 9, "font_size": 9, "align": "left", "bold": False, "visible": True, "text": ""},
        {"id": "invoice_number", "type": "invoice_number", "label": "شماره فاکتور", "x_mm": left + usable_w - right_col_w, "y_mm": top, "w_mm": right_col_w, "h_mm": 9, "font_size": 9, "align": "right", "bold": True, "visible": True, "text": ""},
        {"id": "company", "type": "company", "label": "نام مجموعه", "x_mm": left, "y_mm": top + 11, "w_mm": usable_w * 0.62, "h_mm": 24, "font_size": 14, "align": "right", "bold": True, "visible": True, "text": ""},
        {"id": "payment_status", "type": "payment_status", "label": "وضعیت پرداخت", "x_mm": left, "y_mm": top + 36, "w_mm": usable_w * 0.42, "h_mm": 8, "font_size": 9, "align": "left", "bold": False, "visible": True, "text": ""},
        {"id": "seat_number", "type": "seat_number", "label": "شماره میز / صندلی", "x_mm": left + usable_w * 0.50, "y_mm": top + 36, "w_mm": usable_w * 0.50, "h_mm": 8, "font_size": 9, "align": "right", "bold": False, "visible": True, "text": ""},
        {"id": "items_table", "type": "items_table", "label": "جدول کالاها", "x_mm": left, "y_mm": table_y, "w_mm": usable_w, "h_mm": table_h, "font_size": 9, "align": "right", "bold": False, "visible": True, "text": ""},
        {"id": "totals", "type": "totals", "label": "مبلغ نهایی", "x_mm": left + usable_w * 0.53, "y_mm": totals_y, "w_mm": usable_w * 0.47, "h_mm": 18, "font_size": 11, "align": "right", "bold": True, "visible": True, "text": ""},
        {"id": "footer", "type": "footer", "label": "متن پایانی", "x_mm": left, "y_mm": height - margin - 15, "w_mm": usable_w, "h_mm": 12, "font_size": 8, "align": "center", "bold": False, "visible": True, "text": ""},
    ]
    return elements


DEFAULT_TEMPLATE = {
    "company_name": "نام کسب‌وکار", "legal_id": "", "address": "", "phone": "",
    "seat_number_label": "شماره صندلی / میز",
    "footer": "از خرید شما سپاسگزاریم.", "paper_size": "A4", "orientation": "portrait",
    "font_family": "Vazirmatn", "font_size": 11, "header_font_size": 23,
    "line_height": 1.8, "text_direction": "rtl",
    "margin_mm": 12, "accent_color": "#3157A4", "show_border": True,
    "frame_border_color": "#CBD5E1", "roll_height_mm": None,
    "layout_order": ["company", "metadata", "items", "totals", "footer"],
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
DEFAULT_TEMPLATE["elements"] = default_elements_for_paper()


def _text(value):
    return escape("" if value is None else str(value))


def _fa_digits(value):
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _money(value):
    try:
        number = float(value or 0)
        formatted = "{:,.0f}".format(number) if number.is_integer() else "{:,.2f}".format(number).rstrip("0").rstrip(".")
        return _fa_digits(formatted)
    except (TypeError, ValueError):
        return "۰"


def _valid_color(value, fallback):
    value = str(value or "")
    return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback


def page_dimensions(template=None):
    config = template or {}
    paper = str(config.get("paper_size") or "A4")
    if paper == "receipt":
        paper = "receipt80"
    if paper not in PAPER_DIMENSIONS_MM:
        paper = "A4"
    width, height = PAPER_DIMENSIONS_MM[paper]
    if config.get("orientation") == "landscape" and paper not in ("receipt80", "receipt58"):
        width, height = height, width
    if paper in ("receipt80", "receipt58") and config.get("roll_height_mm"):
        try:
            height = max(height, min(MAX_THERMAL_ROLL_HEIGHT_MM, float(config["roll_height_mm"])))
        except (TypeError, ValueError):
            pass
    return float(width), float(height)


def normalize_elements(elements, template=None):
    """Sanitize persisted element geometry before drawing or printing it."""
    if not isinstance(elements, list):
        elements = default_elements_for_paper(
            (template or {}).get("paper_size", "A4"),
            (template or {}).get("orientation", "portrait"),
            (template or {}).get("margin_mm", 12),
        )
    # Continuous thermal receipts need taller element bounds than fixed-size sheets.
    # Keep the roll bound finite so malformed persisted templates cannot create huge painter geometry.
    is_thermal_roll = str((template or {}).get("paper_size") or "") in ("receipt", "receipt80", "receipt58")
    vertical_limit = MAX_THERMAL_ROLL_HEIGHT_MM if is_thermal_roll else 600.0
    normalized = []
    seen = set()
    for index, source in enumerate(elements[:80]):
        if not isinstance(source, dict):
            continue
        element_type = source.get("type")
        if element_type not in ELEMENT_TYPES:
            continue
        element_id = str(source.get("id") or "{}-{}".format(element_type, index + 1))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", element_id) or element_id in seen:
            element_id = "{}-{}".format(element_type, index + 1)
        seen.add(element_id)
        element = {
            "id": element_id,
            "type": element_type,
            "label": str(source.get("label") or element_type.replace("_", " "))[:80],
            "text": str(source.get("text") or "")[:500],
            "align": source.get("align") if source.get("align") in ALIGNMENTS else "right",
            "visible": bool(source.get("visible", True)),
            "bold": bool(source.get("bold", False)),
        }
        for key, default, low, high in (
            ("x_mm", 10, 0, 600), ("y_mm", 10, 0, vertical_limit),
            ("w_mm", 40, 3, 600), ("h_mm", 10, 3, vertical_limit),
            ("font_size", 9, 6, 32),
        ):
            try:
                value = float(source.get(key, default))
                if not math.isfinite(value):
                    raise ValueError
                element[key] = max(low, min(high, value))
            except (TypeError, ValueError):
                element[key] = default
        normalized.append(element)
    return normalized


def _template_config(template=None):
    config = dict(DEFAULT_TEMPLATE)
    if isinstance(template, dict):
        for key, value in template.items():
            if key in config:
                config[key] = value
    if config["paper_size"] == "receipt":
        config["paper_size"] = "receipt80"
    if config["paper_size"] not in PAPER_DIMENSIONS_MM:
        config["paper_size"] = "A4"
    if config["orientation"] not in ("portrait", "landscape"):
        config["orientation"] = "portrait"
    try:
        config["margin_mm"] = max(2, min(30, int(config["margin_mm"])))
    except (TypeError, ValueError):
        config["margin_mm"] = DEFAULT_TEMPLATE["margin_mm"]
    font_family = str(config.get("font_family") or DEFAULT_TEMPLATE["font_family"]).strip()
    if not re.fullmatch(r"[\w .()\-]{1,80}", font_family, flags=re.UNICODE):
        font_family = DEFAULT_TEMPLATE["font_family"]
    config["font_family"] = font_family
    for key, fallback, minimum, maximum in (
        ("font_size", 8, 6, 32), ("header_font_size", 23, 10, 48)
    ):
        try:
            config[key] = max(minimum, min(maximum, int(config.get(key, fallback))))
        except (TypeError, ValueError):
            config[key] = fallback
    try:
        config["line_height"] = max(1.0, min(2.5, float(config.get("line_height", 1.8))))
    except (TypeError, ValueError):
        config["line_height"] = 1.8
    config["text_direction"] = config.get("text_direction") if config.get("text_direction") in ("rtl", "ltr") else "rtl"
    config["accent_color"] = _valid_color(config.get("accent_color"), DEFAULT_TEMPLATE["accent_color"])
    config["frame_border_color"] = _valid_color(config.get("frame_border_color"), DEFAULT_TEMPLATE["frame_border_color"])
    config["show_border"] = bool(config.get("show_border", True))
    if config.get("roll_height_mm") is not None:
        try:
            config["roll_height_mm"] = max(1.0, min(MAX_THERMAL_ROLL_HEIGHT_MM, float(config["roll_height_mm"])))
        except (TypeError, ValueError):
            config["roll_height_mm"] = None
    config["elements"] = normalize_elements(config.get("elements"), config)
    config["block_settings"] = dict(DEFAULT_TEMPLATE["block_settings"])
    config["block_settings"].update(config.get("block_settings") or {})
    config["table_alignment"] = dict(DEFAULT_TEMPLATE["table_alignment"])
    config["table_alignment"].update(config.get("table_alignment") or {})
    return config


def _receipt_number(receipt):
    return str(receipt.get("day_receipt_id") or str(receipt.get("id", ""))[:8] or "—")


def _receipt_date(receipt):
    value = str(receipt.get("created_at") or "")
    try:
        formatted = datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        return _fa_digits(formatted)
    except (ValueError, TypeError):
        return _fa_digits(value[:32] or "—")


def _payment_label(receipt):
    return "پرداخت‌شده" if receipt.get("payed") else "پرداخت‌نشده"


def _effective_font_size(element, config):
    """Scale per-element point sizes with the shared base size; retain explicit headline sizing."""
    try:
        requested = float(element.get("font_size", config.get("font_size", 11)))
    except (TypeError, ValueError):
        requested = 11.0
    try:
        base = float(config.get("font_size", 11))
    except (TypeError, ValueError):
        base = 11.0
    effective = requested * base / float(DEFAULT_TEMPLATE["font_size"])
    if element.get("type") == "company":
        try:
            effective = max(effective, float(config.get("header_font_size", 23)))
        except (TypeError, ValueError):
            effective = max(effective, 23.0)
    return round(max(6.0, min(48.0, effective)), 2)


def _text_for_element(element, receipt, config):
    kind = element["type"]
    label = element.get("label") or ""
    if kind == "invoice_number":
        return "{}: {}".format(label or "شماره فاکتور", _fa_digits(_receipt_number(receipt)))
    if kind == "invoice_date":
        return "{}: {}".format(label or "تاریخ", _receipt_date(receipt))
    if kind == "payment_status":
        return "{}: {}".format(label or "وضعیت پرداخت", _payment_label(receipt))
    if kind == "seat_number":
        return "{}: {}".format(label or config.get("seat_number_label") or "میز / صندلی", receipt.get("seat_number") or "—")
    if kind == "totals":
        return "{}: {}".format(label or "مبلغ نهایی", _money(receipt.get("total_price")))
    if kind == "footer":
        return config.get("footer") or element.get("text") or label
    if kind == "text":
        text = element.get("text") or label
        try:
            page_number = max(1, int(receipt.get("_page_index", 0) or 0) + 1)
        except (TypeError, ValueError):
            page_number = 1
        try:
            page_count = max(page_number, int(receipt.get("_page_count", 1) or 1))
        except (TypeError, ValueError):
            page_count = page_number
        replacements = {
            "{{page_number}}": _fa_digits(page_number),
            "{{page_count}}": _fa_digits(page_count),
            "{{invoice_number}}": _fa_digits(_receipt_number(receipt)),
            "{{date}}": _receipt_date(receipt),
            "{{total}}": _money(receipt.get("total_price")),
            "{{payment_status}}": _payment_label(receipt),
            "{{seat_number}}": _fa_digits(receipt.get("seat_number") or "—"),
            "{{company_name}}": str(config.get("company_name") or ""),
        }
        for token, value in replacements.items():
            text = text.replace(token, value)
        return text
    return ""


def _font(font_family, points, *, bold=False):
    font = QFont(font_family or "Vazirmatn")
    # The painter coordinate system is millimetres, so pixels here mean scene/mm units.
    font.setPixelSize(max(1, int(round(float(points) * 25.4 / 72.0))))
    font.setBold(bool(bold))
    return font


def _text_flags(align, direction="rtl", word_wrap=True):
    flags = int(Qt.AlignmentFlag.AlignVCenter)
    flags |= int({"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
                  "right": Qt.AlignmentFlag.AlignRight}.get(align, Qt.AlignmentFlag.AlignRight))
    flags |= int(Qt.TextFlag.TextWordWrap if word_wrap else Qt.TextFlag.TextSingleLine)
    flags |= int(Qt.TextFlag.TextForceRightToLeft if direction == "rtl" else Qt.TextFlag.TextForceLeftToRight)
    return flags


def _draw_text(painter, rect, text, *, font, color="#172337", align="right", direction="rtl"):
    painter.save()
    painter.setFont(font)
    painter.setPen(QPen(QColor(color)))
    painter.setClipRect(rect)
    painter.drawText(rect, _text_flags(align, direction), str(text))
    painter.restore()


def draw_invoice_element(painter, rect, element, receipt=None, template=None, *, editor=False, selected=False):
    """Draw one invoice element in millimetre coordinates for both canvas and printer."""
    receipt = receipt or {}
    config = _template_config(template)
    if not element.get("visible", True):
        return
    rect = QRectF(rect)
    kind = element.get("type")
    if not editor and not receipt.get("_is_final_page", True) and kind in ("totals", "footer"):
        return
    font_family = config["font_family"]
    accent = config["accent_color"]
    frame_color = config["frame_border_color"]
    font_size = _effective_font_size(element, config)
    bold = bool(element.get("bold", False))
    align = element.get("align") if element.get("align") in ALIGNMENTS else "right"
    direction = config["text_direction"]
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if editor:
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        pen = QPen(QColor("#2563EB" if selected else "#94A3B8"))
        pen.setStyle(Qt.PenStyle.SolidLine if selected else Qt.PenStyle.DashLine)
        pen.setWidthF(0.45 if selected else 0.28)
        painter.setPen(pen)
        painter.drawRect(rect.adjusted(0.12, 0.12, -0.12, -0.12))
        if rect.height() >= 8:
            tag_rect = QRectF(rect.left() + 0.5, rect.top() + 0.35, min(rect.width() - 1, 32), min(4.2, rect.height() - 0.6))
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(QColor("#2563EB" if selected else "#E2E8F0")))
            painter.drawRoundedRect(tag_rect, 0.6, 0.6)
            _draw_text(painter, tag_rect, element.get("label") or kind, font=_font(font_family, 6.5, bold=True),
                       color="#FFFFFF" if selected else "#334155", align="center", direction=direction)
    content_rect = rect.adjusted(1.0, 5.0 if editor and rect.height() >= 8 else 0.8, -1.0, -0.6)
    if content_rect.width() < 2 or content_rect.height() < 2:
        painter.restore()
        return

    if kind == "company":
        company = str(config.get("company_name") or "نام کسب‌وکار")
        painter.setPen(QPen(QColor(accent)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(content_rect.topLeft(), content_rect.topRight())
        title_rect = QRectF(content_rect.x(), content_rect.y() + 0.7, content_rect.width(), min(content_rect.height() * 0.48, 7.5))
        _draw_text(painter, title_rect, company, font=_font(font_family, max(font_size, config["header_font_size"]), bold=True),
                   color=accent, align=align, direction=direction)
        detail = "  ·  ".join(str(v) for v in (config.get("legal_id"), config.get("phone"), config.get("address")) if v)
        if detail:
            details_rect = QRectF(content_rect.x(), title_rect.bottom(), content_rect.width(), max(0, content_rect.bottom() - title_rect.bottom()))
            _draw_text(painter, details_rect, detail, font=_font(font_family, max(6, min(config["font_size"], font_size) - 2)),
                       color="#58677C", align=align, direction=direction)
    elif kind == "items_table":
        items = list(receipt.get("items") or [])
        row_h = min(8.0, max(4.2, content_rect.height() / max(2, len(items) + 1)))
        capacity = max(1, int(content_rect.height() / row_h) - 1)
        selected_items = items[:capacity]
        has_more = len(items) > len(selected_items)
        headers = ["#", "شرح کالا", "تعداد", "قیمت واحد", "جمع"]
        ratios = [0.08, 0.39, 0.14, 0.19, 0.20]
        header_rect = QRectF(content_rect.x(), content_rect.y(), content_rect.width(), row_h)
        painter.setPen(QPen(QColor(frame_color), 0.25))
        painter.setBrush(QBrush(QColor(accent)))
        painter.drawRect(header_rect)
        cursor = header_rect.right()
        for col, (header, ratio) in enumerate(zip(headers, ratios)):
            cell_width = content_rect.width() * ratio
            cell_x = cursor - cell_width
            cell = QRectF(cell_x, header_rect.y(), cell_width, row_h)
            if col:
                painter.setPen(QPen(QColor(frame_color), 0.2))
                painter.drawLine(cell.topLeft(), cell.bottomLeft())
            _draw_text(painter, cell.adjusted(0.6, 0, -0.4, 0), header,
                       font=_font(font_family, min(font_size, 8), bold=True),
                       color="#FFFFFF", align="center" if col in (0, 2, 3, 4) else "right", direction=direction)
            cursor = cell_x
        row_h = min(row_h, max(0.1, (content_rect.height() - header_rect.height()) / max(1, len(selected_items) + int(has_more))))
        row_start = int(receipt.get("_row_start", 0) or 0)
        for row_index, item in enumerate(selected_items):
            y = header_rect.bottom() + row_index * row_h
            cursor = content_rect.right()
            name = item.get("product_name") or item.get("name") or "کالای حذف‌شده"
            quantity = item.get("quantity", 0)
            price = item.get("sell_price", item.get("price", 0))
            try:
                line_total = float(quantity or 0) * float(price or 0)
            except (TypeError, ValueError):
                line_total = 0
            values = [
                _fa_digits(row_start + row_index + 1), str(name), _fa_digits(quantity),
                _money(price), _money(line_total),
            ]
            painter.setPen(QPen(QColor(frame_color), 0.2))
            painter.setBrush(QBrush(QColor("#FFFFFF" if row_index % 2 == 0 else "#F8FAFC")))
            painter.drawRect(QRectF(content_rect.x(), y, content_rect.width(), row_h))
            for col, (value, ratio) in enumerate(zip(values, ratios)):
                cell_width = content_rect.width() * ratio
                cell_x = cursor - cell_width
                cell = QRectF(cell_x, y, cell_width, row_h)
                if col:
                    painter.setPen(QPen(QColor(frame_color), 0.2))
                    painter.drawLine(cell.topLeft(), cell.bottomLeft())
                _draw_text(painter, cell.adjusted(0.7, 0, -0.5, 0), value,
                           font=_font(font_family, min(font_size, 8)),
                           color="#172337", align="right" if col == 1 else "center", direction=direction)
                cursor = cell_x
        if has_more:
            y = header_rect.bottom() + len(selected_items) * row_h
            _draw_text(painter, QRectF(content_rect.x(), y, content_rect.width(), row_h),
                       "… ادامه اقلام در صفحه بعد", font=_font(font_family, 7),
                       color="#64748B", align="center", direction=direction)
        painter.setPen(QPen(QColor(frame_color), 0.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(content_rect)
    elif kind == "totals":
        painter.setPen(QPen(QColor(accent), 0.65))
        painter.setBrush(QBrush(QColor("#F8FAFC") if not editor else QColor("#EFF6FF")))
        painter.drawRoundedRect(content_rect, 1, 1)
        display = _text_for_element(element, receipt, config)
        _draw_text(painter, content_rect.adjusted(1.5, 0.5, -1.5, -0.5), display,
                   font=_font(font_family, max(font_size, 10), bold=True),
                   color=accent, align=align, direction=direction)
    else:
        display = _text_for_element(element, receipt, config)
        if kind in ("invoice_number", "invoice_date"):
            painter.setPen(QPen(QColor(frame_color), 0.3))
            if not editor:
                painter.drawLine(content_rect.bottomLeft(), content_rect.bottomRight())
        color = accent if kind == "invoice_number" or bold else "#27364A"
        _draw_text(painter, content_rect, display, font=_font(font_family, font_size, bold=bold),
                   color=color, align=align, direction=direction)
    painter.restore()


def prepare_print_template(template=None, receipt=None):
    """Expand thermal-roll layouts for all items without converting the roll to multiple pages."""
    config = _template_config(template)
    if config["paper_size"] not in ("receipt80", "receipt58"):
        return config
    receipt = receipt or {}
    elements = config["elements"]
    table = next((item for item in elements if item["type"] == "items_table" and item.get("visible", True)), None)
    if table is not None:
        old_height = float(table["h_mm"])
        item_count = len(receipt.get("items") or [])
        wanted_height = max(old_height, (item_count + 1) * 4.7)
        extra = wanted_height - old_height
        old_bottom = float(table["y_mm"]) + old_height
        table["h_mm"] = wanted_height
        if extra > 0:
            for element in elements:
                if element is table:
                    continue
                if element["type"] in ("totals", "footer") and float(element["y_mm"]) >= old_bottom - 0.5:
                    element["y_mm"] = float(element["y_mm"]) + extra
    width, base_height = PAPER_DIMENSIONS_MM[config["paper_size"]]
    bottom = max((float(item["y_mm"]) + float(item["h_mm"]) for item in elements if item.get("visible", True)), default=base_height)
    try:
        margin = max(3.0, min(20.0, float(config.get("margin_mm", 4))))
    except (TypeError, ValueError):
        margin = 4.0
    config["roll_height_mm"] = max(float(base_height), bottom + margin)
    return config


def prepare_invoice_pages(receipt, template=None):
    """Return (receipt slice, template) pairs for each physical print page."""
    source = dict(receipt or {})
    config = _template_config(template)
    if config["paper_size"] in ("receipt80", "receipt58"):
        prepared = prepare_print_template(config, source)
        source["_row_start"] = 0
        source["_is_final_page"] = True
        return [(source, prepared)]

    items = list(source.get("items") or [])
    table = next((item for item in config["elements"] if item["type"] == "items_table" and item.get("visible", True)), None)
    if table is None or len(items) < 2:
        source["_row_start"] = 0
        source["_is_final_page"] = True
        return [(source, config)]
    # Match the renderer's minimum row height so a page never silently drops trailing items.
    capacity = max(1, int(float(table["h_mm"]) / 4.2) - 1)
    chunks = [items[index:index + capacity] for index in range(0, len(items), capacity)] or [[]]
    pages = []
    for page_index, chunk in enumerate(chunks):
        current = dict(source)
        current["items"] = chunk
        current["_row_start"] = page_index * capacity
        current["_is_final_page"] = page_index == len(chunks) - 1
        current["_page_index"] = page_index
        current["_page_count"] = len(chunks)
        pages.append((current, config))
    return pages


def draw_invoice_page(painter, target_rect, receipt=None, template=None, *, editor=False, selected_id=None):
    """Draw an exact-sized physical invoice sheet; target_rect uses painter-coordinate units."""
    config = _template_config(template)
    width, height = page_dimensions(config)
    target = QRectF(target_rect)
    painter.save()
    painter.translate(target.left(), target.top())
    painter.scale(target.width() / width, target.height() / height)
    page = QRectF(0, 0, width, height)
    painter.fillRect(page, QColor("#FFFFFF"))
    if config["show_border"]:
        pen = QPen(QColor(config["frame_border_color"]), 0.65)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(page.adjusted(0.35, 0.35, -0.35, -0.35))
    if editor:
        margin = float(config.get("margin_mm", 12))
        safe = page.adjusted(margin, margin, -margin, -margin)
        pen = QPen(QColor("#CBD5E1"), 0.25, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(safe)
    for element in config["elements"]:
        draw_invoice_element(
            painter,
            QRectF(element["x_mm"], element["y_mm"], element["w_mm"], element["h_mm"]),
            element, receipt, config, editor=editor,
            selected=selected_id == element.get("id"),
        )
    painter.restore()


def _element_html(element, receipt, config):
    kind = element["type"]
    if not receipt.get("_is_final_page", True) and kind in ("totals", "footer"):
        return ""
    if not element.get("visible", True):
        return ""
    x, y, w, h = (element["x_mm"], element["y_mm"], element["w_mm"], element["h_mm"])
    align = element.get("align", "right")
    font_size = _effective_font_size(element, config)
    style = (
        "position:absolute;left:{:.2f}mm;top:{:.2f}mm;width:{:.2f}mm;height:{:.2f}mm;"
        "overflow:hidden;box-sizing:border-box;font-family:'{}';font-size:{}pt;text-align:{};"
        "font-weight:{};direction:{};line-height:{};".format(
            x, y, w, h, _text(config["font_family"]), font_size, align,
            "700" if element.get("bold") else "400", config["text_direction"], config["line_height"],
        )
    )
    if kind == "items_table":
        rows = []
        for index, item in enumerate(receipt.get("items") or [], 1):
            quantity, price = item.get("quantity", 0), item.get("sell_price", item.get("price", 0))
            try:
                total = float(quantity or 0) * float(price or 0)
            except (TypeError, ValueError):
                total = 0
            rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                _fa_digits(index), _text(item.get("product_name") or item.get("name") or "کالای حذف‌شده"),
                _fa_digits(quantity), _money(price), _money(total),
            ))
        return "<div style='{}'><table class='items'><thead><tr><th>#</th><th>شرح کالا</th><th>تعداد</th><th>قیمت واحد</th><th>جمع</th></tr></thead><tbody>{}</tbody></table></div>".format(style, "".join(rows))
    if kind == "company":
        detail = " · ".join(_text(v) for v in (config.get("legal_id"), config.get("phone"), config.get("address")) if v)
        detail_size = max(6, float(config["font_size"]) - 2)
        text = "<strong style='font-size:{}pt'>{}</strong><br><span style='font-size:{}pt'>{}</span>".format(
            config["header_font_size"], _text(config.get("company_name")), detail_size, detail
        )
    else:
        text = _text(_text_for_element(element, receipt, config))
    return "<div style='{}'>{}</div>".format(style, text)


def render_invoice_html(receipt, template=None):
    """Safe browser HTML representation of the same element positions used by canvas/printing."""
    receipt = receipt or {}
    config = prepare_print_template(template, receipt) if str((template or {}).get("paper_size", "A4")) in ("receipt", "receipt80", "receipt58") else _template_config(template)
    width, height = page_dimensions(config)
    border = "1px solid {}".format(config["frame_border_color"]) if config["show_border"] else "none"
    elements_html = "".join(_element_html(element, receipt, config) for element in config["elements"])
    receipt_width = "width: 74mm;" if config["paper_size"] == "receipt80" else ""
    return """<!doctype html><html lang="fa" dir="{direction}"><head><meta charset="utf-8"><style>
@page {{ size: {width}mm {height}mm; margin: 0; }}
* {{ box-sizing: border-box; }}
html,body {{ padding:0; margin:0; background:#fff; color:#172337; font-family:"{font}","Vazirmatn","Segoe UI","Noto Sans Arabic",sans-serif; }}
.paper {{ position:relative; overflow:hidden; width:{width}mm; height:{height}mm; border:{border}; background:#fff; font-size:{font_size}pt; }}
.items {{ width:100%; border-collapse:collapse; table-layout:fixed; font-size:{font_size}pt; direction:{direction}; }}
.items th {{ color:#fff; background:{accent}; border:1px solid {frame}; padding:1mm; }}
.items td {{ border:1px solid {frame}; padding:0.7mm; overflow-wrap:anywhere; }}
.receipt-content {{ {receipt_width} }}
</style></head><body><main class="paper">{elements}</main></body></html>""".format(
        direction=config["text_direction"], width=width, height=height,
        font=_text(config["font_family"]), border=border, font_size=config["font_size"],
        accent=config["accent_color"], frame=config["frame_border_color"],
        receipt_width=receipt_width, elements=elements_html,
    )
