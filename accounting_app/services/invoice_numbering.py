"""Shared invoice-number formatting and validation for persisted sales documents."""
from datetime import date, datetime
import re

DEFAULT_INVOICE_NUMBER_FORMAT = "{DATE}-{NUM}"
DEFAULT_INVOICE_NUMBER_PADDING = 5
_ALLOWED_TOKENS = {"YYYY", "YY", "MM", "M", "DD", "D", "DATE", "NUM", "SEQ"}
_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def validate_invoice_number_format(value):
    """Validate a safe token language and require a sequence guaranteeing unique numbers."""
    if not isinstance(value, str):
        raise ValueError("فرمت شماره فاکتور باید متن باشد.")
    template = value.strip()
    if not template or len(template) > 120:
        raise ValueError("فرمت شماره فاکتور باید بین ۱ تا ۱۲۰ نویسه باشد.")
    matches = re.findall(r"\{([^{}]*)\}", template)
    stripped = re.sub(r"\{[^{}]*\}", "", template)
    if "{" in stripped or "}" in stripped:
        raise ValueError("آکولادهای فرمت شماره فاکتور کامل نیستند.")
    unsupported = [token for token in matches if token not in _ALLOWED_TOKENS]
    if unsupported:
        raise ValueError(
            "متغیر نامعتبر در فرمت شماره فاکتور: {}. متغیرهای مجاز: {}".format(
                ", ".join(sorted(set(unsupported))),
                "{YYYY}، {YY}، {MM}، {M}، {DD}، {D}، {DATE}، {NUM} و {SEQ}",
            )
        )
    tokens = set(matches)
    has_full_date = "DATE" in tokens or (
        "YYYY" in tokens and "MM" in tokens and bool({"DD", "D"} & tokens)
    )
    if "SEQ" not in tokens and not ("NUM" in tokens and has_full_date):
        raise ValueError(
            "برای یکتا ماندن شماره‌ها، از {SEQ} یا از {DATE}-{NUM} "
            "(یا ترکیب کامل سال، ماه، روز و {NUM}) استفاده کنید."
        )
    return template


def _number(value):
    if value is None or value == "":
        return "0"
    raw = str(value).translate(_DIGIT_TRANSLATION)
    try:
        return str(max(0, int(raw)))
    except (TypeError, ValueError):
        return raw


def _padded(value, width):
    raw = _number(value)
    return raw.zfill(width) if width > 0 and raw.isdigit() else raw


def _receipt_datetime(receipt):
    value = receipt.get("created_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now()


def format_invoice_number(receipt, format_string=DEFAULT_INVOICE_NUMBER_FORMAT, padding=DEFAULT_INVOICE_NUMBER_PADDING):
    """Format date/daily/global counters; padding is a minimum digit width, not a maximum."""
    template = validate_invoice_number_format(format_string)
    try:
        width = max(0, min(12, int(padding)))
    except (TypeError, ValueError):
        width = DEFAULT_INVOICE_NUMBER_PADDING
    source = receipt or {}
    moment = _receipt_datetime(source)
    tokens = {
        "YYYY": moment.strftime("%Y"), "YY": moment.strftime("%y"),
        "MM": moment.strftime("%m"), "M": str(moment.month),
        "DD": moment.strftime("%d"), "D": str(moment.day),
        "DATE": moment.strftime("%Y-%m-%d"),
        "NUM": _padded(source.get("day_receipt_id"), width),
        "SEQ": _padded(source.get("invoice_sequence"), width),
    }
    return re.sub(r"\{([A-Z]+)\}", lambda match: tokens[match.group(1)], template)
