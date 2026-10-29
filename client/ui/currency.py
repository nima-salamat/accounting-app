"""Shared currency display preferences and safe display-unit conversion.

Amounts already stored by the application use toman as the internal base unit.
The selected currency affects presentation only: rials are displayed at 10:1,
and converting input values back to the base unit is explicit.
"""
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QObject, Signal


_VALID_UNITS = {"toman", "rial"}
_UNIT_LABELS = {"toman": "تومان", "rial": "ریال"}


class _CurrencyContext(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.unit = "toman"


_context = _CurrencyContext()


def get_currency_unit():
    return _context.unit


def currency_label(unit=None):
    chosen = str(unit or get_currency_unit()).strip().lower()
    return _UNIT_LABELS.get(chosen, _UNIT_LABELS["toman"])


def set_currency_unit(unit):
    chosen = str(unit or "toman").strip().lower()
    if chosen not in _VALID_UNITS:
        chosen = "toman"
    if chosen != _context.unit:
        _context.unit = chosen
        _context.changed.emit(chosen)
    return chosen


def to_display_amount(value, unit=None):
    """Convert an internal toman amount into the selected display unit."""
    try:
        amount = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    chosen = str(unit or get_currency_unit()).strip().lower()
    return amount * 10 if chosen == "rial" else amount


def to_base_amount(value, unit=None):
    """Convert an input amount in the selected display unit back to internal toman."""
    try:
        amount = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    chosen = str(unit or get_currency_unit()).strip().lower()
    return amount / 10 if chosen == "rial" else amount


def format_display_amount(value, *, include_unit=True, signed=False):
    """Format a value that is already expressed in the selected display unit."""
    try:
        amount = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    text = format(abs(amount), ",.2f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if amount < 0:
        text = "-" + text
    elif signed:
        text = "+" + text
    return "{} {}".format(text, currency_label()) if include_unit else text


def format_currency(value, *, include_unit=True, signed=False):
    """Format an internal toman amount in the current shared display currency."""
    return format_display_amount(
        to_display_amount(value),
        include_unit=include_unit,
        signed=signed,
    )
